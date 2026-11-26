"""Input validation and pure helpers for the archive and restore workflows."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from shared.exceptions import InvalidConfiguration, InvalidInput

STORAGE_CLASSES = ("GLACIER_IR", "GLACIER", "DEEP_ARCHIVE")
SELECTIONS = ("MTIME", "ATIME")
RESTORE_TIERS = ("Expedited", "Standard", "Bulk")
CAPTURE_MODES = ("NONE", "ONTAP_REST")
DEFAULT_THRESHOLD_BYTES = 5 * 1024**3
MAX_FILES_CEILING = 100_000

# Largest object the FSx for ONTAP S3 Access Point accepts as an upload. A restore writes the
# object back through the Access Point, so a larger file could be archived and deleted but not
# restored there. Source: FSx for ONTAP User Guide, "Access point compatibility", limitations:
# "Maximum object size is 50 GiB for uploads, but you can download objects larger than that".
ACCESS_POINT_UPLOAD_LIMIT_BYTES = 50 * 1024**3

# Files below this size are left out by default. S3 Standard-IA, One Zone-IA and Glacier
# Instant Retrieval bill at least 128 KB per object, and Glacier Flexible Retrieval and Deep
# Archive add 40 KB of metadata per object (32 KB at the archive rate, 8 KB at the Standard
# rate). Source: Amazon S3 User Guide, "Comparing the Amazon S3 storage classes".
DEFAULT_MIN_FILE_BYTES = 128 * 1024

MAX_FILTER_ITEMS = 50

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
    filters: "SelectionFilters"
    requested_by: str | None = None
    resume: bool = False


@dataclass(frozen=True)
class SelectionFilters:
    """What is left out of the selection, besides files that are too new."""

    min_size_bytes: int = DEFAULT_MIN_FILE_BYTES
    max_file_bytes: int = ACCESS_POINT_UPLOAD_LIMIT_BYTES
    allow_oversize: bool = False
    exclude_patterns: tuple[str, ...] = field(default_factory=tuple)
    exclude_prefixes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "minSizeBytes": self.min_size_bytes,
            "maxFileBytes": self.max_file_bytes,
            "allowOversize": self.allow_oversize,
            "excludePatterns": list(self.exclude_patterns),
            "excludePrefixes": list(self.exclude_prefixes),
        }

    @classmethod
    def from_dict(cls, d: dict | None, defaults: "SelectionFilters | None" = None) -> "SelectionFilters":
        base = defaults or cls()
        d = d or {}
        return cls(
            min_size_bytes=int(d.get("minSizeBytes", base.min_size_bytes)),
            max_file_bytes=int(d.get("maxFileBytes", base.max_file_bytes)),
            allow_oversize=bool(d.get("allowOversize", base.allow_oversize)),
            exclude_patterns=tuple(d.get("excludePatterns", base.exclude_patterns)),
            exclude_prefixes=tuple(d.get("excludePrefixes", base.exclude_prefixes)),
        )

    def key_exclusion(self, key: str) -> str | None:
        """``"prefix"`` or ``"pattern"`` when the key is excluded by name, else None.

        Patterns are shell globs (``fnmatch``) matched against the whole key, so ``*.vmdk``
        matches ``vm/disk.vmdk`` because ``*`` also matches ``/``.
        """
        if any(key.startswith(p) for p in self.exclude_prefixes):
            return "prefix"
        if any(fnmatch.fnmatchcase(key, pat) for pat in self.exclude_patterns):
            return "pattern"
        return None

    def size_exclusion(self, size: int) -> str | None:
        """``"tooLarge"`` or ``"tooSmall"`` when the size rules the file out, else None."""
        if size > self.max_file_bytes and not self.allow_oversize:
            return "tooLarge"
        if size < self.min_size_bytes:
            return "tooSmall"
        return None


def _string_list(value, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if (
        not isinstance(value, list)
        or len(value) > MAX_FILTER_ITEMS
        or not all(isinstance(v, str) and v and len(v) <= 512 for v in value)
    ):
        raise InvalidInput(f"{name} must be a list of up to {MAX_FILTER_ITEMS} non-empty strings")
    return tuple(value)


def _principal_parts(arn: str) -> tuple[str, str, str | None]:
    """``(account, role-or-user name, session)`` of an IAM or STS ARN; free text maps to itself."""
    a = arn.strip().lower()
    m = re.match(r"^arn:[^:]*:sts::(\d*):assumed-role/([^/]+)/(.+)$", a)
    if m:
        return m.group(1), "role/" + m.group(2), m.group(3)
    m = re.match(r"^arn:[^:]*:iam::(\d*):(role|user)/(?:.*/)?([^/]+)$", a)
    if m:
        return m.group(1), f"{m.group(2)}/{m.group(3)}", None
    return "", a, None


def same_principal(a: str, b: str) -> bool:
    """True when two declared identities may be the same actor.

    An assumed-role session ARN equals its role ARN (the role cannot be told apart from one of
    its sessions), and two sessions of one role are equal only if the session names are equal.
    Free text is compared case-insensitively. This is a comparison of what the two callers
    *declared*; the real principals are in CloudTrail (StartExecution, SendTaskSuccess).
    """
    pa, pb = _principal_parts(a), _principal_parts(b)
    if pa[:2] != pb[:2]:
        return False
    if pa[2] is None or pb[2] is None:
        return True
    return pa[2] == pb[2]


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


def normalize_archive_input(
    event: dict,
    *,
    execution_name: str,
    ontap_enabled: bool,
    default_filters: SelectionFilters | None = None,
    require_separate_approver: bool = True,
) -> ArchivePlan:
    """Validate the start input of the archive state machine.

    ``default_filters`` carries the stack-level defaults (minimum size, exclusions). Patterns
    and prefixes in the input are added to them, never substituted: a stack-level exclusion
    such as a legal-hold prefix cannot be dropped by a start input.
    """
    defaults = default_filters or SelectionFilters()
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
    min_size = event.get("minSizeBytes", defaults.min_size_bytes)
    if not isinstance(min_size, int) or isinstance(min_size, bool) or min_size < 0:
        raise InvalidInput("minSizeBytes must be a non-negative integer")
    allow_oversize = event.get("allowOversize", False)
    if not isinstance(allow_oversize, bool):
        raise InvalidInput("allowOversize must be a JSON boolean")
    resume = event.get("resume", False)
    if not isinstance(resume, bool):
        raise InvalidInput("resume must be a JSON boolean")
    filters = SelectionFilters(
        min_size_bytes=min_size,
        max_file_bytes=ACCESS_POINT_UPLOAD_LIMIT_BYTES,
        allow_oversize=allow_oversize,
        exclude_patterns=tuple(
            dict.fromkeys(defaults.exclude_patterns + _string_list(event.get("excludePatterns"), "excludePatterns"))
        ),
        exclude_prefixes=tuple(
            dict.fromkeys(defaults.exclude_prefixes + _string_list(event.get("excludePrefixes"), "excludePrefixes"))
        ),
    )
    dry_run = parse_dry_run(event.get("dryRun"))
    requested_by = event.get("requestedBy")
    if requested_by is not None and (
        not isinstance(requested_by, str) or not requested_by.strip() or len(requested_by) > 2048
    ):
        raise InvalidInput("requestedBy must be a non-empty string (the IAM principal ARN that starts the run)")
    if not dry_run and require_separate_approver and not requested_by:
        raise InvalidInput(
            "requestedBy is required when dryRun is false and RequireSeparateApprover is true: "
            "name the IAM principal that starts this run, so the approver can be checked against it"
        )
    return ArchivePlan(
        run_id=run_id,
        prefix=prefix,
        storage_class=storage_class,
        older_than_days=older,
        selection=selection,
        max_files=max_files,
        dry_run=dry_run,
        capture_attributes=capture,
        filters=filters,
        requested_by=requested_by.strip() if requested_by else None,
        resume=resume,
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


def archive_key(prefix: str, run_id: str, key: str) -> str:
    """Key under which a source file is stored in the archive bucket.

    Layout: ``<prefix><runId>/<original key>``. The run id keeps a dry run, a later real run and
    a re-archive of a rewritten file from overwriting one another: with versioning off an
    overwrite deletes the earlier object (a possible early-deletion charge on classes with a
    minimum storage duration), and the ledger of the earlier run would point at a different
    object than the one it recorded.
    """
    return f"{prefix}{run_id}/{key}"


def build_metadata(
    key: str, etag: str, last_modified: str, attrs: dict | None, run_id: str | None = None
) -> dict[str, str]:
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
    if run_id:
        meta["source-run-id"] = run_id
    for name in ("uid", "gid", "mode", "mtime", "atime"):
        if attrs and attrs.get(name) is not None:
            meta[f"source-{name}"] = str(attrs[name])
    return meta


def guess_content_type(key: str) -> str:
    """Content-Type for ``MetadataDirective=REPLACE`` (REPLACE drops the source's)."""
    import mimetypes

    return mimetypes.guess_type(key)[0] or "application/octet-stream"
