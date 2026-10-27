#!/usr/bin/env python3
# Real-environment run: recorded [V1][V2][V4]; not recorded [V3][V5][V6][V7][E13] (status source: docs/verification-record.md)
"""Pure helpers for the shared-vault lab scripts (standard library only).

Runs on Python 3.9 and later: macOS ships /usr/bin/python3 at 3.9, and the lab
scripts must not depend on a newer interpreter. ``datetime.fromisoformat`` before
3.11 does not understand a trailing ``Z`` (SSO cache files use one), so every
timestamp goes through :func:`parse_iso`.

Usage: ``python3 lab_helpers.py <command> [options]``. Commands:

* ``code-digest``      sha256[:12] over the lab scripts, templates and UI spec
* ``portal-ref``       sha256[:12] over the git object ids of four portal paths
* ``record-row``       candidate verification-record rows from lab-run.local.jsonl
* ``add-days``         ISO 8601 timestamp plus N days (month ends, leap days)
* ``sso-minutes``      minutes left on the SSO token of an AWS CLI profile
* ``svm-limit``        SVM-per-file-system limit for a throughput and network type
* ``restore-metadata`` ``--metadata`` value for a restore into an FSx for ONTAP volume
* ``cost-dates``       Start/End dates for a Cost Explorer request
* ``valid-date``       exit 0 when the argument is a real YYYY-MM-DD date
* ``age-minutes``      whole minutes between two timestamps (invitation age)
* ``node-min-major``   minimum Node.js major version for the portal tooling
* ``text-digest``      sha256[:32] of the arguments joined with "|" (idempotency tokens)
* ``provision-password`` read the output of ``make portal-demo-user`` on stdin: print
                       the password (exit 0), or exit 3 when the account already existed

Nothing here calls AWS. Whether the shapes produced here are accepted by the
services is not yet run on real environment.
"""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Lines that state the real-environment status are excluded from the digest.
# Rewriting one (for example after a run is recorded) must not invalidate the
# record it points at.
STATUS_PREFIXES = (b"# Real-environment run:", b"// Real-environment run:")

# File kinds that may live in the digest scope. A tracked file of any other kind
# in scope is refused, so a new kind of input cannot silently fall outside the
# digest.
ALLOWED_SUFFIXES = (".sh", ".py", ".json", ".yaml", ".ts")

# Digest scope, relative to the lab root: scripts/*, scripts/lib/* and
# cloudformation/* (one level each, no recursion). Documentation, tests and
# parameter examples are out of scope on purpose.
DIGEST_DIRS = ("scripts", "scripts/lib", "cloudformation")

# The UI spec lives in the portal package, relative to the repository root.
PORTAL_SPEC_REL = "solutions/amplify-portal/tests/e2e/shared-vault-lab.spec.ts"

# Portal sources whose git object ids make up portal-ref (repository-root paths).
PORTAL_REF_PATHS = (
    "solutions/amplify-portal/functions/recovery-points",
    "solutions/amplify-portal/functions/restore",
    "solutions/amplify-portal/src/components/RecoveryPoints.tsx",
    "solutions/amplify-portal/amplify/backend.ts",
)

# Verification items whose rows must also carry portal-ref.
PORTAL_ITEMS = frozenset({"V3", "V5", "V6", "V7"})

# SVMs per file system, by throughput capacity (MBps) for one HA pair.
# Source: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-svms.html
# Retrieved 2026-10-11 (read in full). Values are (IPv4-only, dual-stack).
# Two or more HA pairs: 11 in both network types, for any throughput.
SVM_LIMITS_ONE_HA_PAIR = {
    128: (6, 6),
    256: (6, 6),
    384: (6, 6),
    512: (14, 11),
    768: (6, 6),
    1024: (14, 11),
    1536: (14, 11),
    2048: (24, 11),
    3072: (14, 11),
    4096: (24, 11),
    6144: (24, 11),
}
SVM_LIMIT_MULTI_HA_PAIR = 11
# Minimum Node.js major version for the portal tooling (07 --ui, sandbox.sh).
# Source: the prerequisites table in solutions/amplify-portal/docs/GETTING-STARTED.md
# ("20.x or later"). The portal README says 18.17+; the stricter value is used.
# A test keeps this constant equal to the table.
NODE_MIN_MAJOR = 20

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$", re.ASCII)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------


def parse_iso(value: str) -> dt.datetime:
    """Parse an ISO 8601 timestamp into an aware UTC datetime.

    ``Z`` is replaced by ``+00:00`` first because ``fromisoformat`` rejects it
    before Python 3.11. A timestamp without an offset is read as UTC.

    Args:
        value: ISO 8601 text.

    Returns:
        Timezone-aware datetime in UTC.

    Raises:
        ValueError: When the text is not an ISO 8601 timestamp.
    """
    text = value.strip()
    if not ISO_RE.match(text):
        raise ValueError(f"not an ISO 8601 timestamp: {value!r}")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def format_iso(value: dt.datetime) -> str:
    """Format a datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, whole seconds).

    Args:
        value: Aware or naive (read as UTC) datetime.

    Returns:
        UTC timestamp with a ``Z`` suffix.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_days(start: str, days: int) -> str:
    """Add whole days to an ISO 8601 timestamp.

    Args:
        start: ISO 8601 timestamp.
        days: Days to add; may be negative.

    Returns:
        The shifted timestamp as ``YYYY-MM-DDTHH:MM:SSZ``.
    """
    return format_iso(parse_iso(start) + dt.timedelta(days=days))


def age_minutes(start: str, now: str) -> int:
    """Whole minutes from ``start`` to ``now`` (never negative).

    Args:
        start: ISO 8601 timestamp of the event.
        now: ISO 8601 timestamp of the present.

    Returns:
        Elapsed whole minutes, 0 when ``start`` is in the future.
    """
    seconds = (parse_iso(now) - parse_iso(start)).total_seconds()
    return max(int(seconds // 60), 0)


def text_digest(parts: list[str]) -> str:
    """Hash text parts into a stable 32-hex-digit token.

    Used for idempotency tokens that must be the same on every run for the same
    inputs (a retry must not start a second irreversible copy).

    Args:
        parts: Values that identify the operation; joined with ``|``.

    Returns:
        First 32 hex digits of the SHA-256 of the joined text.
    """
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def valid_date(value: str) -> bool:
    """Tell whether a string is a real calendar date in ``YYYY-MM-DD`` form.

    Args:
        value: Candidate text.

    Returns:
        True for a real date (2024-02-29 yes, 2023-02-29 no).
    """
    if not DATE_RE.match(value):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# code-digest
# --------------------------------------------------------------------------


def _is_hidden(parts: tuple[str, ...]) -> bool:
    """True when any path component is a dotfile or a ``__pycache__`` directory."""
    return any(p.startswith(".") or p == "__pycache__" for p in parts)


def _git_lines(cwd: Path, *args: str) -> list[str] | None:
    """Run git and return NUL-separated output entries, or None when git fails.

    Args:
        cwd: Directory to run in.
        *args: git arguments (``-z`` is added by the caller).

    Returns:
        Output entries, or None when git is missing or the command fails.
    """
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [e.decode("utf-8", "surrogateescape") for e in proc.stdout.split(b"\0") if e]


def _in_git_work_tree(root: Path) -> bool:
    """True when ``root`` is inside a git work tree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _in_digest_scope(rel: str) -> bool:
    """True for a path directly inside one of :data:`DIGEST_DIRS`."""
    parent, _, name = rel.rpartition("/")
    return bool(name) and parent in DIGEST_DIRS


def digest_entries(root: Path) -> list[tuple[str, Path]]:
    """List the (label, path) pairs that feed the digest.

    Inside a git work tree the list is ``git ls-files -co --exclude-standard``
    (tracked plus untracked-but-not-ignored), so the value does not change when
    a file is staged. Outside git it is a directory walk. Both apply the same
    filters: dotfiles and ``__pycache__`` are skipped, and only the allowed file
    kinds are kept. A tracked file of an unknown kind in scope is an error.

    Args:
        root: Lab root (the directory that contains ``scripts/``).

    Returns:
        Sorted (label, path) pairs; the label is the lab-relative path, or the
        repository-relative path for the UI spec.

    Raises:
        ValueError: When a tracked file of an unknown kind is in scope.
    """
    root = root.resolve()
    repo_root = (root / ".." / "..").resolve()
    candidates: list[tuple[str, Path]] = []
    if _in_git_work_tree(root):
        tracked = _git_lines(root, "ls-files", "-z", "--", *DIGEST_DIRS) or []
        others = _git_lines(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *DIGEST_DIRS) or []
        tracked_set = set(tracked)
        for rel in sorted(tracked_set | set(others)):
            if not _in_digest_scope(rel) or _is_hidden(tuple(rel.split("/"))):
                continue
            if not rel.endswith(ALLOWED_SUFFIXES):
                if rel in tracked_set:
                    raise ValueError(f"unknown tracked file kind in digest scope: {rel}")
                continue
            candidates.append((rel, root / rel))
        spec = _git_lines(
            repo_root,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            PORTAL_SPEC_REL,
        )
        if spec and (repo_root / PORTAL_SPEC_REL).is_file():
            candidates.append((PORTAL_SPEC_REL, repo_root / PORTAL_SPEC_REL))
    else:
        for directory in DIGEST_DIRS:
            base = root / directory
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                rel = f"{directory}/{entry.name}"
                if not entry.is_file() or _is_hidden(tuple(rel.split("/"))):
                    continue
                if entry.suffix not in ALLOWED_SUFFIXES:
                    continue
                candidates.append((rel, entry))
        spec_path = repo_root / PORTAL_SPEC_REL
        if spec_path.is_file():
            candidates.append((PORTAL_SPEC_REL, spec_path))
    return sorted(candidates, key=lambda pair: pair[0])


def normalize_for_digest(data: bytes) -> bytes:
    """Normalize one file for hashing: LF line endings, no status-line lines.

    Args:
        data: Raw file content.

    Returns:
        Content with CRLF folded to LF and lines that start with a status prefix
        removed.
    """
    lines = data.replace(b"\r\n", b"\n").split(b"\n")
    return b"\n".join(line for line in lines if not line.startswith(STATUS_PREFIXES))


def code_digest(root: Path) -> str:
    """Compute the 12-hex-digit digest of the lab code.

    Args:
        root: Lab root.

    Returns:
        First 12 hex digits of a sha256 over ``label NUL content NUL`` records in
        ascending label order.
    """
    h = hashlib.sha256()
    for label, path in digest_entries(root):
        h.update(label.encode("utf-8"))
        h.update(b"\0")
        h.update(normalize_for_digest(path.read_bytes()))
        h.update(b"\0")
    return h.hexdigest()[:12]


# --------------------------------------------------------------------------
# portal-ref
# --------------------------------------------------------------------------


def _git_top(path: Path) -> Path | None:
    """Return the git work-tree top for ``path``, or None."""
    lines = _git_lines(path, "rev-parse", "--show-toplevel")
    if not lines:
        return None
    return Path(lines[0].strip()).resolve()


def dirty_paths(root: Path) -> list[str]:
    """List uncommitted changes in the portal sources and the digest inputs.

    Args:
        root: Lab root.

    Returns:
        ``git status --porcelain`` entries for the four portal paths, the lab's
        scripts and templates, and the UI spec (empty when clean).

    Raises:
        RuntimeError: When git is not available for this tree.
    """
    root = root.resolve()
    top = _git_top(root)
    if top is None:
        raise RuntimeError("portal-ref needs a git work tree (git is unavailable here)")
    lab_rel = os.path.relpath(root, top).replace(os.sep, "/")
    paths = list(PORTAL_REF_PATHS)
    paths += [f"{lab_rel}/scripts", f"{lab_rel}/cloudformation", PORTAL_SPEC_REL]
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
            cwd=str(top),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"git status failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError("git status failed")
    return [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def portal_ref(root: Path) -> str:
    """Compute the 12-hex-digit reference of the portal sources at HEAD.

    Args:
        root: Lab root.

    Returns:
        First 12 hex digits of a sha256 over the ``git rev-parse HEAD:<path>``
        object ids of :data:`PORTAL_REF_PATHS`, one per line.

    Raises:
        RuntimeError: When git is unavailable, a path is missing at HEAD, or
            the portal sources or the digest inputs have uncommitted changes.
    """
    root = root.resolve()
    dirty = dirty_paths(root)
    if dirty:
        raise RuntimeError("refusing portal-ref: uncommitted changes in " + ", ".join(entry[3:] for entry in dirty[:5]))
    top = _git_top(root)
    assert top is not None  # dirty_paths already required it
    ids = []
    for rel in PORTAL_REF_PATHS:
        out = _git_lines(top, "rev-parse", f"HEAD:{rel}")
        if not out:
            raise RuntimeError(f"portal path not found at HEAD: {rel}")
        ids.append(out[0].strip())
    return hashlib.sha256(("\n".join(ids) + "\n").encode("ascii")).hexdigest()[:12]


# --------------------------------------------------------------------------
# record-row
# --------------------------------------------------------------------------


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read lab-run.local.jsonl, skipping lines that are not JSON objects.

    Args:
        path: Record file.

    Returns:
        Parsed records in file order (empty when the file is missing).
    """
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def record_rows(records: list[dict[str, Any]], aws_cli: str, portal_ref_value: str) -> list[dict[str, str]]:
    """Aggregate check results of apply-mode runs into verification-record rows.

    Plan runs (mode ``plan``, or an exit code of 10) never produce a row: they
    changed nothing and prove nothing. A run without an ``end`` event (killed)
    produces no row either.

    Args:
        records: Parsed lab-run.local.jsonl records.
        aws_cli: AWS CLI version text for the row (or a fill-in marker).
        portal_ref_value: portal-ref for portal items.

    Returns:
        Row dictionaries in run, then item order.
    """
    runs: dict[str, dict[str, Any]] = {}
    for rec in records:
        run = str(rec.get("run", ""))
        if not run:
            continue
        info = runs.setdefault(run, {"first": rec.get("ts"), "end": None, "items": {}, "script": ""})
        event = rec.get("event")
        if event == "end":
            info["end"] = rec
            continue
        if rec.get("mode") != "apply":
            continue
        item = str(rec.get("item", "-"))
        if event in ("check_pass", "check_fail", "check_warn") and item != "-":
            counts = info["items"].setdefault(item, {"pass": 0, "fail": 0, "warn": 0})
            counts[event.split("_", 1)[1]] += 1
            info["script"] = str(rec.get("script", ""))
            info["region"] = str(rec.get("region", ""))
    rows: list[dict[str, str]] = []
    for run in sorted(runs):
        info = runs[run]
        end = info["end"]
        if end is None or end.get("mode") != "apply":
            continue
        try:
            detail = json.loads(str(end.get("detail", "{}")))
        except ValueError:
            continue
        if detail.get("exit") == 10:
            continue
        try:
            seconds = int((parse_iso(str(end["ts"])) - parse_iso(str(info["first"]))).total_seconds())
        except (KeyError, ValueError, TypeError):
            seconds = 0
        for item in sorted(info["items"]):
            c = info["items"][item]
            rows.append(
                {
                    "date": str(end["ts"])[:10],
                    "region": info.get("region", ""),
                    "config": "<fill>",
                    "aws_cli": aws_cli,
                    "digest": str(detail.get("digest", "")),
                    "portal_ref": portal_ref_value if item in PORTAL_ITEMS else "-",
                    "item": item,
                    "result": f"{c['pass']}✅ {c['fail']}❌ {c['warn']}⚠",
                    "duration": f"{max(seconds, 0)}s",
                    "notes": f"script {info['script']}",
                }
            )
    return rows


def _aws_cli_version() -> str:
    """Return ``aws-cli/x.y.z`` from ``aws --version``, or a fill-in marker."""
    try:
        proc = subprocess.run(["aws", "--version"], capture_output=True, check=False)
    except OSError:
        return "<fill>"
    m = re.search(r"aws-cli/\d+\.\d+\.\d+", proc.stdout.decode("utf-8", "replace"))
    return m.group(0) if m else "<fill>"


# --------------------------------------------------------------------------
# sso-minutes
# --------------------------------------------------------------------------


def sso_minutes(profile: str, config: Path, cache_dir: Path, now: str) -> str:
    """Report the minutes left on the SSO token behind an AWS CLI profile.

    The cache file name is the SHA-1 of the ``sso_session`` name (current
    format) or, for the legacy format, of ``sso_start_url``; the file holds the
    access token's ``expiresAt``. Only that access-token expiry is read.

    Args:
        profile: Profile name.
        config: Path of the AWS CLI config file.
        cache_dir: SSO token cache directory.
        now: Current time, ISO 8601.

    Returns:
        A whole number of minutes (never negative), ``n/a`` when the profile is
        not an SSO profile, or ``unknown:<reason>`` when it cannot be read.
    """
    parser = configparser.RawConfigParser()
    try:
        read = parser.read(config, encoding="utf-8")
    except (configparser.Error, OSError) as exc:
        return f"unknown:config unreadable ({exc.__class__.__name__})"
    if not read:
        return "unknown:config file not found"
    section = "default" if profile == "default" else f"profile {profile}"
    if not parser.has_section(section):
        return "unknown:profile not found"
    session = parser.get(section, "sso_session", fallback="").strip()
    start_url = parser.get(section, "sso_start_url", fallback="").strip()
    if not session and not start_url:
        return "n/a"
    key = session or start_url
    cache_file = cache_dir / (hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest() + ".json")
    if not cache_file.is_file():
        return "unknown:token cache not found"
    try:
        expires = parse_iso(str(json.loads(cache_file.read_text(encoding="utf-8"))["expiresAt"]))
    except (ValueError, KeyError, TypeError, OSError):
        return "unknown:expiresAt not readable"
    remaining = (expires - parse_iso(now)).total_seconds() / 60.0
    return str(max(int(remaining // 1), 0))


# --------------------------------------------------------------------------
# svm-limit
# --------------------------------------------------------------------------


def svm_limit(throughput: int, network_type: str, ha_pairs: int) -> int | None:
    """Look up the SVM-per-file-system limit.

    Args:
        throughput: Throughput capacity in MBps (per file system, one HA pair).
        network_type: ``IPV4`` or ``DUAL``.
        ha_pairs: Number of HA pairs.

    Returns:
        The limit, or None when the combination is not in the documented table.
    """
    if ha_pairs >= 2:
        return SVM_LIMIT_MULTI_HA_PAIR
    limits = SVM_LIMITS_ONE_HA_PAIR.get(throughput)
    if limits is None:
        return None
    return limits[1] if network_type == "DUAL" else limits[0]


# --------------------------------------------------------------------------
# restore-metadata
# --------------------------------------------------------------------------

_ONTAP_KEYS = (
    "junctionPath",
    "sizeInMegabytes",
    "storageEfficiencyEnabled",
    "storageVirtualMachineId",
)


def _lower_first(name: str) -> str:
    """Lowercase the first character of a key (JunctionPath -> junctionPath)."""
    return name[:1].lower() + name[1:]


def build_restore_metadata(
    source: dict[str, Any],
    svm_id: str | None,
    name: str | None,
    junction_path: str | None,
) -> dict[str, str]:
    """Build the ``--metadata`` map for an FSx for ONTAP volume restore.

    Keys of the source are read case-insensitively. The result carries only
    ``Name`` and ``OntapConfiguration`` (a JSON string whose keys start with a
    lowercase letter: junctionPath, sizeInMegabytes, storageEfficiencyEnabled,
    storageVirtualMachineId). FileSystemId, VolumeId, Lifecycle and VolumeType
    are never copied, and tieringPolicy is not sent (the documentation shows no
    value shape for it).

    Args:
        source: ``RestoreMetadata`` map from get-recovery-point-restore-metadata.
        svm_id: Target SVM id; replaces the source value when given.
        name: Target volume name; replaces the source value when given.
        junction_path: Target junction path; replaces the source value when given.

    Returns:
        Map of string to string, ready for ``--metadata`` (as JSON).

    Raises:
        ValueError: When the volume name or the ONTAP configuration is missing.
    """
    lowered = {str(k).lower(): v for k, v in source.items()}
    volume_name = name or lowered.get("name")
    if not volume_name:
        raise ValueError("restore metadata has no volume name; pass --name")
    raw = lowered.get("ontapconfiguration")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise ValueError("OntapConfiguration is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("restore metadata has no OntapConfiguration")
    ontap_in = {_lower_first(str(k)): v for k, v in raw.items()}
    ontap_out: dict[str, Any] = {k: ontap_in[k] for k in _ONTAP_KEYS if k in ontap_in}
    if svm_id:
        ontap_out["storageVirtualMachineId"] = svm_id
    if junction_path:
        ontap_out["junctionPath"] = junction_path
    if "storageVirtualMachineId" not in ontap_out:
        raise ValueError("no storageVirtualMachineId; pass --svm-id")
    return {
        "Name": str(volume_name),
        "OntapConfiguration": json.dumps(ontap_out, sort_keys=True, separators=(",", ":")),
    }


# --------------------------------------------------------------------------
# cost-dates
# --------------------------------------------------------------------------


def cost_dates(since: str | None, record_file: Path | None, now: str) -> dict[str, str]:
    """Compute the Cost Explorer ``Start`` and ``End`` dates.

    ``End`` is exclusive, so it is tomorrow (UTC). ``Start`` is ``since`` or, when
    omitted, the date of the first record in the run file.

    Args:
        since: Optional ``YYYY-MM-DD`` start date.
        record_file: lab-run.local.jsonl used when ``since`` is omitted.
        now: Current time, ISO 8601.

    Returns:
        Dictionary with ``start`` and ``end`` dates.

    Raises:
        ValueError: When no start date can be determined or it is invalid.
    """
    today = parse_iso(now).date()
    if since:
        if not valid_date(since):
            raise ValueError(f"--since is not a real YYYY-MM-DD date: {since!r}")
        start = since
    else:
        records = read_records(record_file) if record_file else []
        stamps = [str(r["ts"])[:10] for r in records if "ts" in r]
        if not stamps:
            raise ValueError("no start date: pass --since or run a script first")
        start = stamps[0]
    end = (today + dt.timedelta(days=1)).isoformat()
    if start >= end:
        raise ValueError("start date is not before the end date")
    return {"start": start, "end": end}


# --------------------------------------------------------------------------
# Command-line interface
# --------------------------------------------------------------------------


# The print format of scripts/portal_provision_demo_user.py that 07 depends on. A
# contract test reads that script and checks both strings, so a format change is
# caught before this parser silently reads nothing.
PROVISION_PASSWORD_LINE = re.compile(r"^  password  (\S+)\s*$")
PROVISION_EXISTS_TEXT = "already exists; password unchanged"


def parse_provision_output(text: str) -> tuple[str, str]:
    """Read the result of ``make portal-demo-user``.

    Args:
        text: Standard output of the provisioning script.

    Returns:
        ``("password", value)`` when exactly one password line is present,
        ``("exists", "")`` when the account already existed (its password is
        unchanged and unknown).

    Raises:
        ValueError: When the output holds neither (or several password lines). The
            message never contains output text, so no secret can reach a log.
    """
    found = [m.group(1) for m in (PROVISION_PASSWORD_LINE.match(line) for line in text.splitlines()) if m]
    if len(found) == 1:
        return "password", found[0]
    if not found and PROVISION_EXISTS_TEXT in text:
        return "exists", ""
    raise ValueError(f"expected exactly one password line or the '{PROVISION_EXISTS_TEXT}' notice (found {len(found)})")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Parser with one sub-command per helper.
    """
    parser = argparse.ArgumentParser(description="Shared-vault lab helpers (stdlib only).")
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))

    root_arg(sub.add_parser("code-digest"))
    root_arg(sub.add_parser("portal-ref"))

    rec = sub.add_parser("record-row")
    root_arg(rec)
    rec.add_argument("--log", default=None)
    rec.add_argument("--aws-cli", default=None)

    add = sub.add_parser("add-days")
    add.add_argument("--from", dest="start", required=True)
    add.add_argument("--days", type=int, required=True)

    sso = sub.add_parser("sso-minutes")
    sso.add_argument("--profile", required=True)
    sso.add_argument("--config", default=str(Path.home() / ".aws" / "config"))
    sso.add_argument("--cache-dir", default=str(Path.home() / ".aws" / "sso" / "cache"))
    sso.add_argument("--now", required=True)

    svm = sub.add_parser("svm-limit")
    svm.add_argument("--throughput", type=int, required=True)
    svm.add_argument("--network-type", choices=("IPV4", "DUAL"), default="IPV4")
    svm.add_argument("--ha-pairs", type=int, default=1)

    rm = sub.add_parser("restore-metadata")
    rm.add_argument("--input", default="-")
    rm.add_argument("--svm-id", default=None)
    rm.add_argument("--name", default=None)
    rm.add_argument("--junction-path", default=None)

    cd = sub.add_parser("cost-dates")
    cd.add_argument("--since", default=None)
    cd.add_argument("--record", default=None)
    cd.add_argument("--now", required=True)

    vd = sub.add_parser("valid-date")
    vd.add_argument("value")
    am = sub.add_parser("age-minutes")
    am.add_argument("--from", dest="start", required=True)
    am.add_argument("--now", required=True)
    sub.add_parser("node-min-major")
    td = sub.add_parser("text-digest")
    td.add_argument("parts", nargs="+")
    sub.add_parser("provision-password")
    return parser


def _cmd_record_row(args: argparse.Namespace) -> int:
    """Print candidate verification-record rows (a Markdown table body)."""
    root = Path(args.root)
    try:
        dirty = dirty_paths(root)
    except RuntimeError as exc:
        print(f"warning: no row produced: {exc}", file=sys.stderr)
        return 1
    if dirty:
        print(
            "warning: no row produced: uncommitted changes in the portal sources or "
            "the lab code (" + ", ".join(entry[3:] for entry in dirty[:5]) + ")",
            file=sys.stderr,
        )
        return 1
    log = Path(args.log) if args.log else root / "lab-run.local.jsonl"
    ref = portal_ref(root)
    rows = record_rows(read_records(log), args.aws_cli or _aws_cli_version(), ref)
    current = code_digest(root)
    for row in rows:
        if row["digest"] != current:
            print(
                f"note: row for {row['item']} was recorded with digest {row['digest']}; current code is {current}",
                file=sys.stderr,
            )
        print(
            "| {date} | {region} | {config} | {aws_cli} | {digest} | {portal_ref} | "
            "{item} | {result} | {duration} | {notes} |".format(**row)
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 success, 1 refused or failed, 2 usage error,
        3 value not in a documented table.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "code-digest":
            print(code_digest(Path(args.root)))
        elif args.command == "portal-ref":
            print(portal_ref(Path(args.root)))
        elif args.command == "record-row":
            return _cmd_record_row(args)
        elif args.command == "add-days":
            print(add_days(args.start, args.days))
        elif args.command == "sso-minutes":
            print(sso_minutes(args.profile, Path(args.config), Path(args.cache_dir), args.now))
        elif args.command == "svm-limit":
            limit = svm_limit(args.throughput, args.network_type, args.ha_pairs)
            if limit is None:
                print(
                    f"throughput {args.throughput} MBps is not in the documented table; set LAB_RECIPIENT_SVM_LIMIT",
                    file=sys.stderr,
                )
                return 3
            print(limit)
        elif args.command == "restore-metadata":
            text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("RestoreMetadata"), dict):
                data = data["RestoreMetadata"]
            print(
                json.dumps(
                    build_restore_metadata(data, args.svm_id, args.name, args.junction_path),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        elif args.command == "cost-dates":
            record = Path(args.record) if args.record else None
            print(json.dumps(cost_dates(args.since, record, args.now), sort_keys=True))
        elif args.command == "valid-date":
            return 0 if valid_date(args.value) else 1
        elif args.command == "age-minutes":
            print(age_minutes(args.start, args.now))
        elif args.command == "node-min-major":
            print(NODE_MIN_MAJOR)
        elif args.command == "text-digest":
            print(text_digest(args.parts))
        elif args.command == "provision-password":
            kind, value = parse_provision_output(sys.stdin.read())
            if kind == "exists":
                return 3
            print(value)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
