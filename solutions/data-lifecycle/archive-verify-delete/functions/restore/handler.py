"""Restore helpers for ``restore.asl.json``.

Actions:

* ``select``    choose DELETED files of an archive run (``keys`` or ``prefix``) and write the item list
* ``prepare``   per file: does the Access Point already have it (``EXISTS``), and does it need a restore request
* ``check``     read the ``Restore`` header from a ``HeadObject`` response: READY, WAITING or TIMEOUT
* ``finalize``  set the ledger to ``RESTORED``
* ``reapply``   write ``manifests/<runId>-reapply.sh`` that puts owner, group, mode and mtime back

The Access Point creates restored files as the file system user of the Access Point
(owner 0:1, mode 644, mtime = time of the restore in the one environment measured), so
the original attributes are not restored by ``CopyObject``. They are put back from the
ledger by running the generated script on a host that mounts the volume over NFS.
Restoring them through the ONTAP REST API is not implemented: whether the API can set
owner, group, mode and mtime has not been verified.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from datetime import datetime

import boto3

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import RESTORE_TIERS, copy_source, valid_run_id
from shared.archive_verify.runtime import MANIFEST_PREFIX, RuntimeConfig, put_json
from shared.exceptions import InvalidInput, S3ApHelperError, lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

_MODE = re.compile(r"^[0-7]{3,4}$")
_ID = re.compile(r"^[0-9]{1,10}$")
_NEEDS_RESTORE = ("GLACIER", "DEEP_ARCHIVE")


def validate_restore_input(event: dict, execution_name: str) -> dict:
    run_id = valid_run_id(event.get("runId", ""))
    tier = event.get("tier", "Bulk")
    if tier not in RESTORE_TIERS:
        raise InvalidInput(f"tier must be one of {RESTORE_TIERS}")
    days = event.get("days", 7)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        raise InvalidInput("days must be an integer between 1 and 365")
    keys, prefix = event.get("keys"), event.get("prefix")
    if bool(keys) == bool(prefix):
        raise InvalidInput("give exactly one of keys or prefix")
    if keys is not None and (not isinstance(keys, list) or not all(isinstance(k, str) for k in keys)):
        raise InvalidInput("keys must be a list of strings")
    return {
        "runId": run_id,
        "restoreRunId": valid_run_id(event.get("restoreRunId") or execution_name),
        "tier": tier,
        "days": days,
        "keys": keys or [],
        "prefix": prefix or "",
    }


def select_items(ledger: Ledger, req: dict) -> list[dict]:
    items = ledger.query_run(req["runId"], status=L.DELETED, key_prefix=req["prefix"])
    if req["keys"]:
        wanted = set(req["keys"])
        items = [i for i in items if i["key"] in wanted]
    return [
        {
            "key": i["key"],
            "size": int(i["size"]),
            "isLarge": bool(i.get("isLarge")),
            "storageClass": i.get("storageClass", "DEEP_ARCHIVE"),
            "archiveBucket": i["archiveBucket"],
            "archiveKey": i["archiveKey"],
        }
        for i in items
    ]


def restore_state(head: dict, storage_class: str) -> str:
    """READY, WAITING or NOT_REQUESTED, from the ``Restore`` header of ``HeadObject``."""
    header = head.get("Restore")
    if storage_class not in _NEEDS_RESTORE:
        return "READY"
    if not header:
        return "NOT_REQUESTED"
    return "WAITING" if 'ongoing-request="true"' in header else "READY"


def _comment_key(key: str) -> str:
    """A key as it may appear in a ``#`` comment: one line, control characters escaped.

    A key can contain a newline. ``shlex.quote`` is correct inside a command but a comment
    ends at the newline, so whatever follows would run as a command.
    """
    return json.dumps(key)


def reapply_script(run_id: str, items: list[dict]) -> str:
    """Shell script that restores uid, gid, mode and mtime from the ledger.

    Every value interpolated into the script is validated against a strict pattern or
    shell-quoted; a ledger value that fails validation becomes a comment, not a command.
    """
    lines = [
        "#!/bin/sh",
        f"# Reapply file attributes after restore. Run id: {run_id}",
        "# Run as root on a host that mounts the volume over NFS.",
        "set -eu",
        ': "${MOUNT_ROOT:?set MOUNT_ROOT to the NFS mount point that corresponds to the Access Point root}"',
    ]
    for item in sorted(items, key=lambda i: i["key"]):
        key = item["key"]
        if ".." in key.split("/") or key.startswith("/"):
            lines.append(f"# skipped (unsafe key): {_comment_key(key)}")
            continue
        target = f'"$MOUNT_ROOT"/{shlex.quote(key)}'
        attrs = item.get("attrs") or {}
        uid, gid, mode, mtime = (attrs.get(n) for n in ("uid", "gid", "mode", "mtime"))
        if uid is None and gid is None and mode is None and mtime is None:
            lines.append(f"# no attributes recorded: {_comment_key(key)}")
            continue
        if _ID.match(str(uid)) and _ID.match(str(gid)):
            lines.append(f"chown {int(uid)}:{int(gid)} -- {target}")
        if mode is not None and _MODE.match(str(mode)):
            lines.append(f"chmod {mode} -- {target}")
        if mtime:
            try:
                datetime.fromisoformat(str(mtime).replace("Z", "+00:00"))
                lines.append(f"touch -d {shlex.quote(str(mtime))} -- {target}")
            except ValueError:
                lines.append(f"# unreadable mtime for {_comment_key(key)}")
    return "\n".join(lines) + "\n"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    ledger = Ledger(cfg.ledger_table)
    action = event.get("action")

    if action == "select":
        req = validate_restore_input(event.get("input") or {}, event.get("executionName", ""))
        items = select_items(ledger, req)
        key = f"{MANIFEST_PREFIX}{req['runId']}-restore-{req['restoreRunId']}-items.json"
        put_json(cfg.archive_bucket, key, items)
        return {
            **req,
            "count": len(items),
            "bucket": cfg.archive_bucket,
            "itemsKey": key,
            "pollSeconds": cfg.restore_poll_minutes * 60,
            "maxAttempts": max(1, cfg.restore_max_wait_hours * 60 // cfg.restore_poll_minutes),
            "config": cfg.public(),
        }

    if action == "prepare":
        item = event["item"]
        try:
            S3ApHelper(cfg.access_point).head_object(item["key"])
            return {"exists": True}
        except S3ApHelperError as e:
            if e.error_code not in ("404", "NoSuchKey", "NotFound"):
                raise
        return {
            "exists": False,
            "needsRestore": item["storageClass"] in _NEEDS_RESTORE,
            "attempt": 0,
            "copy": {
                "bucket": cfg.access_point,
                "key": item["key"],
                "copySource": copy_source(item["archiveBucket"], item["archiveKey"]),
            },
        }

    if action == "check":
        state = restore_state(event["head"], event["storageClass"])
        attempt = int(event.get("attempt", 0)) + 1
        if state != "READY" and attempt > int(event["maxAttempts"]):
            state = "TIMEOUT"
        return {"state": state, "attempt": attempt}

    if action == "finalize":
        ledger.update(
            event["runId"],
            event["key"],
            L.RESTORED,
            only_if_status=L.DELETED,
            restoredAt=L.now_iso(),
            restoreRunId=event["restoreRunId"],
        )
        return {"key": event["key"], "status": L.RESTORED}

    if action == "reapply":
        items = [
            i
            for i in ledger.query_run(event["runId"], status=L.RESTORED)
            if i.get("restoreRunId") == event["restoreRunId"]
        ]
        key = f"{MANIFEST_PREFIX}{event['runId']}-reapply.sh"
        boto3.client("s3").put_object(
            Bucket=cfg.archive_bucket,
            Key=key,
            Body=reapply_script(event["runId"], items).encode("utf-8"),
            ContentType="text/x-shellscript",
        )
        return {"scriptKey": key, "bucket": cfg.archive_bucket, "files": len(items), "outcome": "COMPLETED"}

    raise InvalidInput(f"unknown action {action!r}")
