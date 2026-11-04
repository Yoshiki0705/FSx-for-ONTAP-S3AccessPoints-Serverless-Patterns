"""ONTAP command and REST API catalog snapshot for Amazon FSx for NetApp ONTAP.

Reads, as the ONTAP administrator in the given secret, what this ONTAP version offers:

* ``security login role show``            the role definitions (what each role may run)
* ``security login role show-user-capability``  the CLI commands the logged-in user may run
* ``security login role show-rest``       every REST endpoint of the version, whatever the privilege
* ``security login role show-ontapi``     the legacy ONTAPI (ZAPI) to CLI mapping
* one GET per REST endpoint that has no path parameter (HTTP code only, bodies are discarded)

The result is written to S3 under ``<prefix>/<file-system>/<ontap-version>/<timestamp>/`` together
with a diff against the previous snapshot. Only GET requests are sent.

Design rules that matter for an ONTAP administrator account:

* The credential is used for many requests. The run stops at the FIRST authentication failure
  (ONTAP code 6691623) and never retries it, because repeated failures lock the account.
* A 401 or 403 that is an authorization answer (another ONTAP code) is data, not a reason to stop.
* The password is never logged. Response bodies are never stored.

Standard library plus boto3 only, so the file can be copied into any environment.
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
import os
import re
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
# botocore logs request and response bodies at DEBUG, and the response to GetSecretValue holds the
# password. Keep the SDK loggers at WARNING whatever LOG_LEVEL says.
for _name in ("boto3", "botocore", "urllib3", "s3transfer"):
    logging.getLogger(_name).setLevel(logging.WARNING)

SCHEMA_VERSION = 1
# ONTAP answers a failed login with this code. The same message covers a wrong password and a
# locked account, so the run must stop on the first one (docs: "do not retry the same credential").
AUTH_FAILURE_CODES = frozenset({"6691623"})
ROLE_PATH = "/api/private/cli/security/login/role"
SAFE_ENDPOINT = re.compile(r"^/[A-Za-z0-9/_.-]+$")
VERSION_RE = re.compile(r"NetApp Release (\d+\.\d+(?:\.\d+)?(?:[A-Z]\d+[A-Z]?\d*)*)")
CLUSTER_NAME_RE = re.compile(r"FsxId[0-9a-f]{17}(-0[12])?")
MIN_REMAINING_MS = 90_000
PROBE_PAUSE_S = 0.03  # pause between probe requests; tests set it to 0


class SnapshotError(Exception):
    """A condition that ends the run. ``reason`` is safe to log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthenticationAbort(SnapshotError):
    """The credential was refused. The run stops and nothing is retried."""


@dataclass(frozen=True)
class Reply:
    status: int
    body: Any  # parsed JSON, or None
    error_code: str
    error_message: str


class Transport(Protocol):
    def get(self, path: str) -> Reply: ...


@dataclass
class Config:
    management_endpoint: str
    secret_arn: str
    bucket: str
    prefix: str = "ontap-catalog"
    file_system_id: str = ""
    probe_rest_get: bool = True
    probe_max_endpoints: int = 400
    verify_ssl: bool = False
    notification_topic_arn: str = ""

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            management_endpoint=os.environ["ONTAP_MANAGEMENT_ENDPOINT"],
            secret_arn=os.environ["ONTAP_SECRET_ARN"],
            bucket=os.environ["OUTPUT_BUCKET"],
            prefix=os.environ.get("OUTPUT_PREFIX", "ontap-catalog").strip("/"),
            file_system_id=os.environ.get("FILE_SYSTEM_ID", ""),
            probe_rest_get=os.environ.get("PROBE_REST_GET", "true").lower() == "true",
            probe_max_endpoints=int(os.environ.get("PROBE_MAX_ENDPOINTS", "400")),
            verify_ssl=os.environ.get("VERIFY_SSL", "false").lower() == "true",
            notification_topic_arn=os.environ.get("NOTIFICATION_TOPIC_ARN", ""),
        )


@dataclass
class Result:
    manifest: dict[str, Any]
    files: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ONTAP transport
# ---------------------------------------------------------------------------


class OntapTransport:
    """GET-only client for the ONTAP management endpoint. One connection, Basic auth, no retries."""

    def __init__(self, host: str, username: str, password: str, verify_ssl: bool) -> None:
        if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
            raise SnapshotError("management endpoint is not a plain host name or address")
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._host = host
        self._ctx = ctx
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        self._conn: http.client.HTTPSConnection | None = None

    def _connect(self) -> http.client.HTTPSConnection:
        if self._conn is None:
            self._conn = http.client.HTTPSConnection(self._host, 443, context=self._ctx, timeout=60)
        return self._conn

    def get(self, path: str) -> Reply:
        # A dropped connection is retried once with a fresh connection. An HTTP error never is.
        for attempt in (1, 2):
            try:
                conn = self._connect()
                conn.request("GET", path, headers=self._headers)
                resp = conn.getresponse()
                raw = resp.read()
                break
            except (OSError, http.client.HTTPException) as exc:
                self._conn = None
                if attempt == 2:
                    raise SnapshotError(f"management endpoint unreachable ({type(exc).__name__})") from exc
        body: Any = None
        code = message = ""
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
        if resp.status >= 400 and isinstance(body, dict):
            err = body.get("error") or {}
            code = str(err.get("code", ""))
            message = str(err.get("message", ""))
        return Reply(resp.status, body if resp.status < 400 else None, code, message)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def parse_version(version_full: str) -> str:
    m = VERSION_RE.search(version_full or "")
    return m.group(1) if m else "unknown"


def mask(text: str) -> str:
    return CLUSTER_NAME_RE.sub("<cluster>", text)[:160]


def check_reply(reply: Reply, what: str) -> None:
    """Stop on a refused credential. Everything else is an answer to record."""
    if reply.status == 401 and (not reply.error_code or reply.error_code in AUTH_FAILURE_CODES):
        raise AuthenticationAbort(f"credential refused on {what} (HTTP 401, code {reply.error_code or 'none'})")


def get_records(transport: Transport, path: str, fields: str, what: str) -> tuple[list[dict[str, Any]] | None, int]:
    """Read a collection, following ``_links.next``. Returns (records or None, HTTP status)."""
    url = f"{path}?fields={fields}&max_records=20000"
    records: list[dict[str, Any]] = []
    for _ in range(20):  # page cap
        reply = transport.get(url)
        check_reply(reply, what)
        if reply.status != 200 or not isinstance(reply.body, dict):
            return (None, reply.status) if not records else (records, reply.status)
        records.extend(reply.body.get("records", []))
        nxt = ((reply.body.get("_links") or {}).get("next") or {}).get("href")
        if not nxt:
            return records, 200
        if not nxt.startswith("/api/private/cli/") or ".." in nxt or "\r" in nxt or "\n" in nxt:
            return records, 200  # an unexpected link is not followed
        url = nxt
    return records, 200


def collect(cfg: Config, transport: Transport, remaining_ms: Callable[[], int]) -> Result:
    cluster = transport.get("/api/cluster?fields=name,version")
    check_reply(cluster, "/api/cluster")
    if cluster.status != 200 or not isinstance(cluster.body, dict):
        raise SnapshotError(f"/api/cluster returned HTTP {cluster.status}")
    version_full = str((cluster.body.get("version") or {}).get("full", ""))
    version = parse_version(version_full)

    files: dict[str, Any] = {}
    unavailable: dict[str, int] = {}

    def fetch(name: str, path: str, fields: str) -> list[dict[str, Any]]:
        records, status = get_records(transport, path, fields, name)
        if records is None:
            unavailable[name] = status
            return []
        files[name] = records
        return records

    fetch("roles", ROLE_PATH, "vserver,role,cmddirname,access,query")
    fetch("cli-user-capability", ROLE_PATH + "/show-user-capability", "object_name,operation_name")
    rest = fetch("show-rest", ROLE_PATH + "/show-rest", "endpoint,commands,supported-operations")
    fetch("show-ontapi", ROLE_PATH + "/show-ontapi", "ontapi,command")

    probe: dict[str, dict[str, Any]] = {}
    truncated = False
    if cfg.probe_rest_get:
        targets = [
            x for x in rest
            if "GET" in x.get("supported_operations", [])
            and SAFE_ENDPOINT.match(x.get("endpoint", ""))
            and ".." not in x["endpoint"]
        ][: cfg.probe_max_endpoints]
        for x in targets:
            if remaining_ms() < MIN_REMAINING_MS:
                truncated = True
                break
            reply = transport.get(f"/api{x['endpoint']}?max_records=1")
            check_reply(reply, "GET probe")
            probe[x["endpoint"]] = {"http": reply.status, "code": reply.error_code, "message": mask(reply.error_message)}
            time.sleep(PROBE_PAUSE_S)

    endpoints = []
    for x in sorted(rest, key=lambda r: r.get("endpoint", "")):
        p = probe.get(x.get("endpoint", ""))
        endpoints.append(
            {
                "endpoint": x.get("endpoint"),
                "operations": x.get("supported_operations", []),
                "cli_commands": x.get("commands", []),
                "get_http": p["http"] if p else None,
                "get_code": p["code"] if p else None,
                "get_note": p["message"] if p else None,
            }
        )
    files["rest-endpoints"] = endpoints
    files.pop("show-rest", None)

    capability = sorted(
        {
            (r.get("object_name", "").replace(".", " ") + " " + r.get("operation_name", "")).strip()
            for r in files.get("cli-user-capability", [])
        }
    )
    files["cli-user-capability"] = capability

    codes: dict[str, int] = {}
    for p in probe.values():
        codes[str(p["http"])] = codes.get(str(p["http"]), 0) + 1
    manifest = {
        "schema": SCHEMA_VERSION,
        "ontap_version": version,
        "ontap_release": mask(version_full),
        "cluster_name": mask(str((cluster.body or {}).get("name", ""))),
        "file_system_id": cfg.file_system_id,
        "ran_as": "",  # filled in by run()
        "counts": {
            "cli_commands_available": len(capability),
            "rest_endpoints": len(endpoints),
            "role_entries": len(files.get("roles", [])),
            "ontapi_mappings": len(files.get("show-ontapi", [])),
            "rest_get_probed": len(probe),
            "rest_get_http": codes,
        },
        "unavailable": unavailable,
        "probe_truncated": truncated,
        "get_only": True,
        "bodies_stored": False,
    }
    return Result(manifest=manifest, files=files)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _set(items: list[Any]) -> set[Any]:
    return set(items)


def diff_snapshots(prev: dict[str, Any] | None, cur: Result) -> dict[str, Any]:
    if prev is None:
        return {"previous": None, "changed": False, "note": "first snapshot"}
    cli_prev, cli_cur = _set(prev.get("cli-user-capability", [])), _set(cur.files.get("cli-user-capability", []))
    rest_prev = {e["endpoint"]: e for e in prev.get("rest-endpoints", [])}
    rest_cur = {e["endpoint"]: e for e in cur.files.get("rest-endpoints", [])}
    changed_probe = sorted(
        ep
        for ep in rest_cur.keys() & rest_prev.keys()
        if rest_cur[ep].get("get_http") != rest_prev[ep].get("get_http")
    )
    out = {
        "previous_version": prev.get("ontap_version"),
        "cli_commands_added": sorted(cli_cur - cli_prev),
        "cli_commands_removed": sorted(cli_prev - cli_cur),
        "rest_endpoints_added": sorted(rest_cur.keys() - rest_prev.keys()),
        "rest_endpoints_removed": sorted(rest_prev.keys() - rest_cur.keys()),
        "rest_get_http_changed": changed_probe,
    }
    out["changed"] = any(bool(v) for k, v in out.items() if k.endswith(("added", "removed", "changed")) and k != "changed")
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class SecretProblem(SnapshotError):
    pass


def load_credentials(secrets: Any, cfg: Config) -> tuple[str, str]:
    """Read the secret and refuse a secret that is tagged for another file system."""
    if cfg.file_system_id:
        desc = secrets.describe_secret(SecretId=cfg.secret_arn)
        tags = {t["Key"]: t["Value"] for t in desc.get("Tags", [])}
        tagged = tags.get("FileSystemId")
        if tagged and tagged != cfg.file_system_id:
            raise SecretProblem("the secret is tagged for a different file system; nothing was sent to ONTAP")
        if not tagged:
            logger.warning("secret has no FileSystemId tag; the file system cannot be cross-checked")
    value = secrets.get_secret_value(SecretId=cfg.secret_arn)["SecretString"]
    data = json.loads(value)
    username = data.get("username") or data.get("Username")
    password = data.get("password") or data.get("Password")
    if not username or not password:
        raise SecretProblem("the secret must be JSON with 'username' and 'password'")
    return username, password


def _error_code(exc: Exception) -> str:
    return str(getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__))


def load_previous(s3: Any, bucket: str, base: str) -> dict[str, Any] | None:
    """Read the previous snapshot, or None on the first run.

    A missing pointer is the normal first run (NoSuchKey, which S3 reports only when the role may
    list the bucket). Any other failure means the diff would silently be skipped for good, so it is
    logged as a warning that names the error code.
    """
    try:
        pointer = json.loads(s3.get_object(Bucket=bucket, Key=f"{base}/latest.json")["Body"].read())
        prev: dict[str, Any] = {}
        for name in ("cli-user-capability", "rest-endpoints"):
            prev[name] = json.loads(s3.get_object(Bucket=bucket, Key=f"{pointer['prefix']}/{name}.json")["Body"].read())
        prev["ontap_version"] = pointer.get("ontap_version")
        return prev
    except Exception as exc:
        code = _error_code(exc)
        if code in ("NoSuchKey", "404"):
            logger.info("first snapshot: there is nothing to compare with")
        else:
            logger.warning("the previous snapshot could not be read (%s); this run has no diff", code)
        return None


def run(
    cfg: Config,
    transport: Transport,
    s3: Any,
    username: str,
    now: datetime,
    remaining_ms: Callable[[], int],
) -> Result:
    result = collect(cfg, transport, remaining_ms)
    result.manifest["ran_as"] = username
    result.manifest["timestamp"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    fs_key = cfg.file_system_id or result.manifest["cluster_name"] or "unknown"
    base = f"{cfg.prefix}/{fs_key}"
    run_prefix = f"{base}/{result.manifest['ontap_version']}/{now.strftime('%Y%m%dT%H%M%SZ')}"

    prev = load_previous(s3, cfg.bucket, base)

    result.diff = diff_snapshots(prev, result)

    def put(key: str, obj: Any) -> None:
        s3.put_object(
            Bucket=cfg.bucket,
            Key=key,
            Body=json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(),
            ContentType="application/json",
        )

    for name, obj in result.files.items():
        put(f"{run_prefix}/{name}.json", obj)
    put(f"{run_prefix}/diff.json", result.diff)
    put(f"{run_prefix}/manifest.json", result.manifest)
    put(f"{base}/latest.json", {"prefix": run_prefix, "ontap_version": result.manifest["ontap_version"]})
    result.manifest["output_prefix"] = run_prefix
    return result


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    import boto3  # imported here so the module can be tested without AWS

    cfg = Config.from_env()
    secrets = boto3.client("secretsmanager")
    try:
        username, password = load_credentials(secrets, cfg)
        transport = OntapTransport(cfg.management_endpoint, username, password, cfg.verify_ssl)
        result = run(
            cfg,
            transport,
            boto3.client("s3"),
            username,
            datetime.now(timezone.utc),
            context.get_remaining_time_in_millis,
        )
    except AuthenticationAbort as exc:
        logger.error("STOPPED: %s. The credential was used once or a few times; do not re-run until it is fixed.", exc.reason)
        raise
    except SnapshotError as exc:
        logger.error("STOPPED: %s", exc.reason)
        raise

    summary = {"ontap_version": result.manifest["ontap_version"], "counts": result.manifest["counts"], "changed": result.diff.get("changed")}
    logger.info("snapshot written: %s", json.dumps(summary))
    if cfg.notification_topic_arn and result.diff.get("changed"):
        boto3.client("sns").publish(
            TopicArn=cfg.notification_topic_arn,
            Subject="ONTAP command/API catalog changed",
            Message=json.dumps(
                {
                    "ontap_version": result.manifest["ontap_version"],
                    "previous_version": result.diff.get("previous_version"),
                    "cli_commands_added": len(result.diff["cli_commands_added"]),
                    "cli_commands_removed": len(result.diff["cli_commands_removed"]),
                    "rest_endpoints_added": len(result.diff["rest_endpoints_added"]),
                    "rest_endpoints_removed": len(result.diff["rest_endpoints_removed"]),
                    "output_prefix": result.manifest["output_prefix"],
                }
            ),
        )
    return {"statusCode": 200, **summary, "output_prefix": result.manifest["output_prefix"]}
