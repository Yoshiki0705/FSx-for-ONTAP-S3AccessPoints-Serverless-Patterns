"""Input validation and pure helpers for the archive and restore workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from shared.exceptions import InvalidConfiguration, InvalidInput

STORAGE_CLASSES = ("GLACIER_IR", "GLACIER", "DEEP_ARCHIVE")
SELECTIONS = ("MTIME", "ATIME")
RESTORE_TIERS = ("Expedited", "Standard", "Bulk")
CAPTURE_MODES = ("NONE", "ONTAP_REST")
DEFAULT_THRESHOLD_BYTES = 5 * 1024**3
MAX_FILES_CEILING = 100_000

_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class ArchivePlan:
    run_id: str
    prefix: str
    storage_class: str
    older_than_days: int
    selection: str
    max_files: int
    dry_run: bool
    capture_attributes: str


def valid_run_id(run_id: str) -> str:
    """Return ``run_id`` if it is safe in a key, a log line and a shell command."""
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id):
        raise InvalidInput("runId must match [A-Za-z0-9._-]{1,64}")
    return run_id


def parse_dry_run(value) -> bool:
    """Anything except an explicit boolean ``False`` is a dry run.

    The default is the safe side. A string such as ``"false"`` is rejected rather
    than interpreted: an input that is merely mistyped must not become permission to
    delete.
    """
    if value is None or value is True:
        return True
    if value is False:
        return False
    raise InvalidInput("dryRun must be a JSON boolean (true or false)")


def normalize_archive_input(event: dict, *, execution_name: str, ontap_enabled: bool) -> ArchivePlan:
    """Validate the start input of the archive state machine."""
    run_id = valid_run_id(event.get("runId") or execution_name)
    storage_class = event.get("storageClass", "DEEP_ARCHIVE")
    if storage_class not in STORAGE_CLASSES:
        raise InvalidInput(f"storageClass must be one of {STORAGE_CLASSES}")
    selection = event.get("selection", "MTIME")
    if selection not in SELECTIONS:
        raise InvalidInput(f"selection must be one of {SELECTIONS}")
    older = event.get("olderThanDays")
    if not isinstance(older, int) or isinstance(older, bool) or older < 0:
        raise InvalidInput("olderThanDays must be a non-negative integer")
    max_files = event.get("maxFiles", 1000)
    if not isinstance(max_files, int) or isinstance(max_files, bool) or not 1 <= max_files <= MAX_FILES_CEILING:
        raise InvalidInput(f"maxFiles must be an integer between 1 and {MAX_FILES_CEILING}")
    capture = event.get("captureAttributes", "ONTAP_REST" if selection == "ATIME" else "NONE")
    if capture not in CAPTURE_MODES:
        raise InvalidInput(f"captureAttributes must be one of {CAPTURE_MODES}")
    prefix = event.get("prefix", "")
    if not isinstance(prefix, str) or ".." in prefix.split("/") or prefix.startswith("/"):
        raise InvalidInput("prefix must be a relative key prefix without '..' segments")
    if (selection == "ATIME" or capture == "ONTAP_REST") and not ontap_enabled:
        raise InvalidConfiguration(
            "selection=ATIME and captureAttributes=ONTAP_REST need the ONTAP REST function; "
            "deploy the stack with VpcId, SubnetIds, OntapSecretArn, OntapManagementIp and VolumeUuid"
        )
    return ArchivePlan(
        run_id=run_id,
        prefix=prefix,
        storage_class=storage_class,
        older_than_days=older,
        selection=selection,
        max_files=max_files,
        dry_run=parse_dry_run(event.get("dryRun")),
        capture_attributes=capture,
    )


def is_older_than(last_modified: str | datetime, days: int, now: datetime | None = None) -> bool:
    """True when ``last_modified`` is strictly older than ``days`` days before ``now``."""
    now = now or datetime.now(timezone.utc)
    if isinstance(last_modified, str):
        last_modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    return last_modified < now - timedelta(days=days)


def etag_equal(a: str | None, b: str | None) -> bool:
    """Compare ETags ignoring the surrounding quotes S3 adds."""
    if not a or not b:
        return False
    return a.strip('"') == b.strip('"')


def copy_source(bucket: str, key: str) -> str:
    """``CopySource`` value: ``bucket/key`` with the key percent-encoded."""
    return f"{bucket}/{quote(key, safe='/')}"


def archive_key(prefix: str, key: str) -> str:
    """Key under which a source file is stored in the archive bucket."""
    return f"{prefix}{key}"


def build_metadata(key: str, etag: str, last_modified: str, attrs: dict | None) -> dict[str, str]:
    """User metadata written with the archived object (``x-amz-meta-source-*``).

    Values are ASCII: the key is percent-encoded because S3 user metadata cannot carry
    arbitrary UTF-8. The ledger holds the authoritative values; this copy is for a
    reader who has only the bucket.
    """
    meta = {
        "source-key": quote(key, safe="/"),
        "source-etag": etag.strip('"'),
        "source-last-modified": last_modified,
    }
    for name in ("uid", "gid", "mode", "mtime", "atime"):
        if attrs and attrs.get(name) is not None:
            meta[f"source-{name}"] = str(attrs[name])
    return meta


def guess_content_type(key: str) -> str:
    """Content-Type for ``MetadataDirective=REPLACE`` (REPLACE drops the source's)."""
    import mimetypes

    return mimetypes.guess_type(key)[0] or "application/octet-stream"
