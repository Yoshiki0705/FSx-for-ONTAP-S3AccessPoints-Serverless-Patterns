"""DynamoDB ledger: one item per (runId, key) with the state of that file.

Status values, in the order a file normally passes through them::

    SELECTED -> RECORDED -> COPIED -> VERIFIED -> DELETED -> RESTORED

Side exits: ``CHANGED`` (the source changed after it was recorded), ``MISMATCH``
(the archived copy did not match), ``FAILED`` (an unexpected error). Only
``VERIFIED`` items can become ``DELETED``; the transition is a conditional write,
so two concurrent runs cannot both claim the delete.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

SELECTED = "SELECTED"
RECORDED = "RECORDED"
COPIED = "COPIED"
VERIFIED = "VERIFIED"
DELETED = "DELETED"
RESTORED = "RESTORED"
CHANGED = "CHANGED"
MISMATCH = "MISMATCH"
FAILED = "FAILED"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain(value: Any) -> Any:
    """Convert DynamoDB ``Decimal`` back to int/float for JSON."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class Ledger:
    """Thin wrapper over the ledger table."""

    def __init__(self, table_name: str, session: boto3.Session | None = None):
        self._table = (session or boto3.Session()).resource("dynamodb").Table(table_name)

    def put(self, run_id: str, key: str, status: str, **attrs: Any) -> None:
        """Create or replace the item for ``(run_id, key)``."""
        item = {"runId": run_id, "key": key, "status": status, "updatedAt": now_iso(), **attrs}
        self._table.put_item(Item={k: v for k, v in item.items() if v is not None})

    def get(self, run_id: str, key: str) -> dict | None:
        resp = self._table.get_item(Key={"runId": run_id, "key": key}, ConsistentRead=True)
        item = resp.get("Item")
        return _plain(item) if item else None

    def update(
        self,
        run_id: str,
        key: str,
        status: str,
        *,
        only_if_status: str | tuple[str, ...] | None = None,
        **attrs: Any,
    ) -> bool:
        """Set ``status`` and attributes. Returns False if ``only_if_status`` did not hold."""
        values = {k: v for k, v in {"status": status, "updatedAt": now_iso(), **attrs}.items() if v is not None}
        names = {f"#a{i}": k for i, k in enumerate(values)}
        expr = "SET " + ", ".join(f"#a{i} = :v{i}" for i in range(len(values)))
        expr_values = {f":v{i}": v for i, v in enumerate(values.values())}
        kwargs: dict[str, Any] = {
            "Key": {"runId": run_id, "key": key},
            "UpdateExpression": expr,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": expr_values,
        }
        if only_if_status is not None:
            allowed = (only_if_status,) if isinstance(only_if_status, str) else only_if_status
            names["#cond"] = "status"
            conds = []
            for i, s in enumerate(allowed):
                expr_values[f":s{i}"] = s
                conds.append(f"#cond = :s{i}")
            kwargs["ConditionExpression"] = " OR ".join(conds)
        else:
            kwargs["ConditionExpression"] = "attribute_exists(runId)"
        try:
            self._table.update_item(**kwargs)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def query_run(self, run_id: str, *, status: str | None = None, key_prefix: str = "") -> list[dict]:
        """All items of a run, optionally filtered by status and key prefix."""
        cond = Key("runId").eq(run_id)
        if key_prefix:
            cond = cond & Key("key").begins_with(key_prefix)
        kwargs: dict[str, Any] = {"KeyConditionExpression": cond, "ConsistentRead": True}
        items: list[dict] = []
        while True:
            resp = self._table.query(**kwargs)
            items.extend(_plain(i) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        if status:
            items = [i for i in items if i.get("status") == status]
        return items
