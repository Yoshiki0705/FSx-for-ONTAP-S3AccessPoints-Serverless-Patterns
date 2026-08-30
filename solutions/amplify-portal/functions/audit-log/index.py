"""Audit log Lambda — file access trail from CloudTrail S3 data events via Athena.

Security note on query construction
-----------------------------------
Every value that reaches the SQL text is either

  1. a constant defined in this module (the event-name lists), or
  2. validated against a strict pattern and rejected if it does not match, or
  3. emitted through `_sql_literal()`, which doubles single quotes.

The `fileKeyPrefix` value additionally goes through `_like_operand()`, which
escapes the LIKE metacharacters `%` and `_` so that a prefix matches literally
instead of acting as a wildcard, and the comparison declares `ESCAPE '\\'`.

Athena engine v3 also supports `ExecutionParameters` with `?` placeholders,
which would remove the need to build literals at all. It is not used here
because it fails outright on a v2 workgroup, and this function has to work
against whichever workgroup the deployment already has. If you know your
workgroup is v3, switching is a strict improvement.
"""

import logging
import os
import re
import time
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "cloudtrail_logs")
ATHENA_TABLE = os.environ.get("ATHENA_TABLE", "cloudtrail_s3_events")
ATHENA_OUTPUT = os.environ.get("ATHENA_OUTPUT_LOCATION", "")
# The per-user portal activity ledger. A different source answering a different
# question, which is why it is a separate section rather than more rows in the same
# table: CloudTrail attributes every portal read to the access point's IAM role, so it
# says a file was read without saying who asked.
ACTIVITY_LEDGER_TABLE = os.environ.get("URL_AUDIT_TABLE_NAME", "")
S3AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Athena identifiers come from the deployment, not from a caller, but validating
# them keeps a misconfiguration from turning into malformed SQL.
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,255}$")

# Accepts a date, or a date with a time, in the shape CloudTrail writes.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?Z?)?$")

# A file key prefix is a path fragment. Anything outside this set is rejected
# rather than escaped, because there is no legitimate key prefix that needs it.
_KEY_PREFIX = re.compile(r"^[A-Za-z0-9 ._/\-]{1,1024}$")

MAX_RESULTS_CAP = 200
DEFAULT_MAX_RESULTS = 50

EVENT_NAMES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "ALL": (
        "GetObject",
        "PutObject",
        "DeleteObject",
        "ListBucket",
        "PutObjectLockConfiguration",
        "PutBucketObjectLockConfiguration",
        "PutObjectRetention",
    ),
    "READ": ("GetObject", "ListBucket"),
    "WRITE": ("PutObject", "DeleteObject"),
    "LOCK": (
        "PutObjectLockConfiguration",
        "PutBucketObjectLockConfiguration",
        "PutObjectRetention",
        "PutObjectLegalHold",
    ),
}


class AuditQueryError(ValueError):
    """Raised when a request cannot be turned into a safe query."""


def _sql_literal(value: str) -> str:
    """Render a Python string as a single-quoted SQL literal.

    Duplicates `shared/sql.py` on purpose: this Lambda has no `SharedPythonLayer`,
    and attaching one to import three lines would add a deployment dependency whose
    content `ampx sandbox` does not reliably refresh. **If the rendering rule
    changes there, change it here too.** Both copies have their own tests.
    """
    return "'" + value.replace("'", "''") + "'"


def _like_operand(value: str) -> str:
    r"""Escape LIKE metacharacters so the value matches literally.

    With `ESCAPE '\'` on the comparison, `\%` and `\_` match a literal percent
    and underscore, and `\\` matches a literal backslash.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validated_max_results(raw) -> int:
    """Coerce maxResults to an int within 1..MAX_RESULTS_CAP.

    Previously this was `min(event.get("maxResults", 50), 200)`, which raised an
    unhandled TypeError on a string and produced `LIMIT -1` on a negative number.
    """
    if raw is None:
        return DEFAULT_MAX_RESULTS
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise AuditQueryError("maxResults must be a number")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise AuditQueryError("maxResults must be a number") from None
    if value < 1:
        raise AuditQueryError("maxResults must be at least 1")
    return min(value, MAX_RESULTS_CAP)


def _validated_timestamp(raw, field: str) -> str:
    if not raw:
        return ""
    if not isinstance(raw, str) or not _TIMESTAMP.match(raw):
        raise AuditQueryError(f"{field} must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
    return raw


def _validated_key_prefix(raw) -> str:
    if not raw:
        return ""
    if not isinstance(raw, str) or not _KEY_PREFIX.match(raw):
        raise AuditQueryError("fileKeyPrefix may contain letters, digits, spaces and . _ / - only")
    return raw


def _build_query(event) -> tuple[str, int]:
    """Build the Athena SQL for this request. Raises AuditQueryError on bad input."""
    if not _IDENTIFIER.match(ATHENA_DATABASE) or not _IDENTIFIER.match(ATHENA_TABLE):
        raise AuditQueryError("Athena database and table names are not valid identifiers")

    event_type = event.get("eventType", "ALL")
    if event_type not in EVENT_NAMES_BY_TYPE:
        raise AuditQueryError(f"eventType must be one of {', '.join(sorted(EVENT_NAMES_BY_TYPE))}")

    max_results = _validated_max_results(event.get("maxResults"))
    start_date = _validated_timestamp(event.get("startDate"), "startDate")
    end_date = _validated_timestamp(event.get("endDate"), "endDate")
    file_key_prefix = _validated_key_prefix(event.get("fileKeyPrefix"))

    names = ", ".join(_sql_literal(name) for name in EVENT_NAMES_BY_TYPE[event_type])
    conditions = [
        "eventsource = 's3.amazonaws.com'",
        f"eventname IN ({names})",
    ]

    # The alias is operator-supplied, but it lands in the same SQL text, so it
    # gets the same treatment as caller input.
    if S3AP_ALIAS:
        pattern = _sql_literal(f"%{_like_operand(S3AP_ALIAS)}%")
        conditions.append(f"requestparameters LIKE {pattern} ESCAPE '\\'")

    if file_key_prefix:
        pattern = _sql_literal(f"%{_like_operand(file_key_prefix)}%")
        conditions.append(f"requestparameters LIKE {pattern} ESCAPE '\\'")

    if start_date:
        conditions.append(f"eventtime >= {_sql_literal(start_date)}")
    if end_date:
        conditions.append(f"eventtime <= {_sql_literal(end_date)}")

    where_clause = " AND ".join(conditions)

    sql = f"""
    SELECT
        eventtime,
        eventname,
        useridentity.arn AS user_arn,
        useridentity.principalid AS principal_id,
        sourceipaddress,
        json_extract_scalar(requestparameters, '$.key') AS file_key,
        json_extract_scalar(requestparameters, '$.bucketName') AS bucket_name,
        errorcode,
        errormessage
    FROM "{ATHENA_DATABASE}"."{ATHENA_TABLE}"
    WHERE {where_clause}
    ORDER BY eventtime DESC
    LIMIT {max_results}
    """  # nosec B608 - operands rendered by _sql_literal()/_like_operand(); see below
    return sql, max_results


def _query_activity_ledger(event: dict[str, Any]) -> dict[str, Any]:
    """Read the per-user portal activity ledger.

    A scan with a filter rather than a query: the table is keyed by an opaque row id
    because rows are appended by several handlers that share no natural key, and the
    volume is one row per portal action rather than one per object access. If it outgrows
    that, the fix is an index on the actor and not a different filter here.

    Args:
        event: `fileKeyPrefix`, `startDate`, `endDate`, `eventType`, `maxResults`. The
            same argument names the CloudTrail path uses, so the audit tab's filters
            apply to both sections without the caller translating them.

    Returns:
        `events` in the shape the audit tab renders, with `queryExecutionId` empty --
        there is no query execution to name -- or `error`.
    """
    if not ACTIVITY_LEDGER_TABLE:
        return {
            "events": [],
            "queryExecutionId": "",
            "error": (
                "Portal activity ledger is not configured. Deploy the stack so "
                "PortalActivityLedgerTable exists, or set URL_AUDIT_TABLE_NAME."
            ),
        }

    try:
        max_results = _validated_max_results(event.get("maxResults"))
    except AuditQueryError as e:
        return {"events": [], "queryExecutionId": "", "error": str(e)}

    prefix = event.get("fileKeyPrefix") or ""
    start_date = event.get("startDate") or ""
    end_date = event.get("endDate") or ""
    action_filter = (event.get("eventType") or "ALL").upper()

    try:
        table = boto3.resource("dynamodb", region_name=REGION).Table(ACTIVITY_LEDGER_TABLE)
        rows: list[dict[str, Any]] = []
        scan_args: dict[str, Any] = {}
        while True:
            page = table.scan(**scan_args)
            rows.extend(page.get("Items", []))
            token = page.get("LastEvaluatedKey")
            # Stopped once enough rows are in hand to fill the page after filtering. The
            # bound is on rows read, not rows returned, so a filter that matches nothing
            # cannot walk the whole table.
            if not token or len(rows) >= max_results * 20:
                break
            scan_args["ExclusiveStartKey"] = token
    except (BotoCoreError, ClientError) as e:
        logger.warning("Activity ledger read failed", exc_info=True)
        return {"events": [], "queryExecutionId": "", "error": str(e)}

    events = []
    for row in rows:
        key = str(row.get("file_key", ""))
        when = str(row.get("generated_at", ""))
        action = str(row.get("action", ""))
        if prefix and not key.startswith(prefix):
            continue
        if action_filter != "ALL" and action != action_filter:
            continue
        # Lexicographic comparison on ISO 8601 in UTC, which orders correctly. The dates
        # arrive as YYYY-MM-DD, so the end date is compared against the date part only --
        # otherwise an end date would exclude everything that happened on it.
        if start_date and when[:10] < start_date:
            continue
        if end_date and when[:10] > end_date:
            continue
        events.append(
            {
                "timestamp": when,
                "action": action,
                # The Cognito user, which is what this source adds over CloudTrail.
                "userArn": str(row.get("generated_by", "")),
                "principalId": ",".join(row.get("groups") or []),
                # A portal request has no source IP here: the call reached AppSync, and
                # the address it came from is CloudTrail's to report, not this table's.
                "sourceIp": "",
                "fileKey": key,
                "bucketName": str(row.get("access_point", "")),
                "errorCode": "",
                "errorMessage": "",
            }
        )

    events.sort(key=lambda row: row["timestamp"], reverse=True)
    return {"events": events[:max_results], "queryExecutionId": "", "error": None}


def handler(event, context):
    """Query the file access audit trail.

    Two sources, selected by `source`:

    `CLOUDTRAIL` (the default) reads S3 data events through Athena. `PORTAL` reads the
    per-user activity ledger this portal writes. Neither substitutes for the other --
    CloudTrail sees every object access and attributes it to the access point's IAM
    role; the ledger knows the Cognito user and records actions that never reach S3 as a
    distinguishable event, such as minting a presigned URL.

    Defaulting to `CLOUDTRAIL` keeps a caller that does not pass `source` on the path it
    was already using.

    Pre-requisites for `CLOUDTRAIL`:
    - CloudTrail trail with S3 data events enabled for the S3 Access Point ARN
    - Athena table over the CloudTrail S3 logs (CREATE TABLE or a Glue crawler)
    - Athena output S3 bucket configured
    """
    if (event.get("source") or "CLOUDTRAIL").upper() == "PORTAL":
        return _query_activity_ledger(event)

    if not ATHENA_OUTPUT:
        return {
            "events": [],
            "queryExecutionId": "",
            "error": "Audit log not configured (set ATHENA_DATABASE, ATHENA_TABLE, ATHENA_OUTPUT_LOCATION)",
        }

    try:
        sql, max_results = _build_query(event)
    except AuditQueryError as e:
        return {"events": [], "queryExecutionId": "", "error": str(e)}

    try:
        athena = boto3.client("athena", region_name=REGION)

        start_resp = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
        )
        query_id = start_resp["QueryExecutionId"]

        # Poll for completion (max 30s)
        state = "QUEUED"
        status_resp = None
        for _ in range(30):
            status_resp = athena.get_query_execution(QueryExecutionId=query_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)

        if state != "SUCCEEDED":
            reason = state
            if status_resp:
                reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", state)
            return {
                "events": [],
                "queryExecutionId": query_id,
                "error": f"Query {state}: {reason}",
            }

        results_resp = athena.get_query_results(QueryExecutionId=query_id, MaxResults=max_results + 1)

        rows = results_resp["ResultSet"]["Rows"]
        if len(rows) <= 1:
            return {"events": [], "queryExecutionId": query_id, "error": None}

        headers = [col["VarCharValue"] for col in rows[0]["Data"]]
        events = []
        for row in rows[1:]:
            values = [col.get("VarCharValue", "") for col in row["Data"]]
            event_dict = dict(zip(headers, values))
            events.append(
                {
                    "timestamp": event_dict.get("eventtime", ""),
                    "action": event_dict.get("eventname", ""),
                    "userArn": event_dict.get("user_arn", ""),
                    "principalId": event_dict.get("principal_id", ""),
                    "sourceIp": event_dict.get("sourceipaddress", ""),
                    "fileKey": event_dict.get("file_key", ""),
                    "bucketName": event_dict.get("bucket_name", ""),
                    "errorCode": event_dict.get("errorcode", ""),
                    "errorMessage": event_dict.get("errormessage", ""),
                }
            )

        return {
            "events": events,
            "queryExecutionId": query_id,
            "error": None,
        }

    except Exception as e:
        print(f"Audit log query error: {e}")
        return {
            "events": [],
            "queryExecutionId": "",
            "error": str(e),
        }
