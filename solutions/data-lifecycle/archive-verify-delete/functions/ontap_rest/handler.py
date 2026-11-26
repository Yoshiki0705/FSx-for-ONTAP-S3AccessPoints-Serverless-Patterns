"""VPC-internal function: the only code that talks to the ONTAP management LIF.

Actions:

* ``candidates``  ``selection=ATIME``: walk the volume through the ONTAP REST API and write the
                  files whose ``accessed_time`` is older than the threshold to the manifests prefix
* ``attributes``  read uid, gid, mode, mtime and atime of one file

ONTAP, not the Access Point, is the source of ``accessed_time``: the S3 API's
``LastModified`` is the modification time and no last-read time is returned.

Not verified against a live cluster yet: the root-directory path encoding of
``GET /storage/volumes/{uuid}/files/{path}`` and the exact names and representation
of ``unix_permissions``. The end-to-end run is where those are confirmed.
"""

from __future__ import annotations

import logging
import os

from shared.archive_verify.plan import is_older_than
from shared.archive_verify.runtime import MANIFEST_PREFIX, put_json
from shared.exceptions import InvalidInput, lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.ontap_client import OntapClient, OntapClientConfig

logger = logging.getLogger(__name__)

SCAN_LIMIT = int(os.environ.get("ONTAP_SCAN_LIMIT", "200000"))


def _client() -> OntapClient:
    return OntapClient(
        OntapClientConfig(
            management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
            secret_name=os.environ["ONTAP_SECRET_ARN"],
            verify_ssl=os.environ.get("ONTAP_VERIFY_SSL", "true").lower() != "false",
        )
    )


def attrs_from_entry(entry: dict) -> dict:
    """Normalize one ONTAP file entry to the attribute names used in the ledger."""
    return {
        "uid": entry.get("owner_id"),
        "gid": entry.get("group_id"),
        "mode": entry.get("unix_permissions"),
        "mtime": entry.get("modified_time"),
        "atime": entry.get("accessed_time"),
    }


def _join(base: str, name: str) -> str:
    return f"{base}/{name}".lstrip("/") if base else name


def walk_candidates(
    client, volume_uuid: str, root: str, older_than_days: int, scan_limit: int
) -> tuple[list[dict], bool]:
    """Depth-first walk. Returns ``(candidates, truncated)``; ``truncated`` means the scan limit hit."""
    stack, found, scanned = [root], [], 0
    while stack:
        directory = stack.pop()
        for entry in client.list_directory(volume_uuid, directory):
            name = entry.get("name")
            if name in (None, ".", ".."):
                continue
            scanned += 1
            if scanned > scan_limit:
                return found, True
            path = _join(directory, name)
            if entry.get("type") == "directory":
                stack.append(path)
            elif entry.get("type") == "file" and entry.get("accessed_time"):
                if is_older_than(entry["accessed_time"], older_than_days):
                    found.append({"path": path, "atime": entry["accessed_time"], "attrs": attrs_from_entry(entry)})
    return found, False


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    action = event.get("action")
    volume_uuid = os.environ["ONTAP_VOLUME_UUID"]
    # The Access Point root may be a subdirectory of the volume.
    volume_root = os.environ.get("ONTAP_PATH_PREFIX", "").strip("/")
    client = _client()

    if action == "candidates":
        prefix = event.get("prefix", "").strip("/")
        root = _join(volume_root, prefix)
        found, truncated = walk_candidates(client, volume_uuid, root, int(event["olderThanDays"]), SCAN_LIMIT)
        found.sort(key=lambda c: c["atime"])
        strip = f"{volume_root}/" if volume_root else ""
        candidates = [
            {
                "key": c["path"][len(strip) :] if strip and c["path"].startswith(strip) else c["path"],
                "attrs": c["attrs"],
            }
            for c in found[: int(event["maxFiles"]) * 2]
        ]
        key = f"{MANIFEST_PREFIX}{event['runId']}-candidates.json"
        put_json(os.environ["ARCHIVE_BUCKET"], key, candidates)
        return {"count": len(candidates), "truncated": truncated, "bucket": os.environ["ARCHIVE_BUCKET"], "key": key}

    if action == "attributes":
        path = _join(volume_root, event["key"])
        parent, _, name = path.rpartition("/")
        entries = [e for e in client.list_directory(volume_uuid, parent) if e.get("name") == name]
        if not entries:
            raise InvalidInput(f"file not found through ONTAP REST: {event['key']}")
        return attrs_from_entry(entries[0])

    raise InvalidInput(f"unknown action {action!r}")
