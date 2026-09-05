#!/usr/bin/env python3
"""Stop a claim that a vendor cannot do something from becoming a premise unasked.

## This is the canonical copy, shared by every project

It lives in `~/.kiro/hooks/scripts/` and resolves the repository from the caller's
working directory, so one file serves every project. A project that wires this into CI
needs a tracked copy of its own, because `~/.kiro/` is not in anyone's checkout -- the
installer places one and records the canonical version it came from, so the two cannot
drift apart silently.

## The failures being closed

Five of them, all observed in one session while designing the Harvest/Prometheus
metrics path:

1. **A claim was made on a weak reading.** "FSx for ONTAP S3 Access Points have no
   CloudWatch metrics" rested on a two-character selective search of two pages
   returning *no matches*. That is not evidence of absence.
2. **The weak claim was written into a document** as though it were settled.
3. **It was about to be committed** to a public repository, where git history is
   permanent and the document is search-indexed.
4. **A vendor limitation blocked the design and the vendor's documentation was not
   read.** Reading it later produced the opposite answer twice: the metrics pages
   enumerate their dimensions (so the absence *is* documented), and a claimed
   contradiction between two pages was a search-result snippet quoted without
   opening the page -- which contained a worked example doing exactly the thing
   said to be impossible.
5. **"AWS cannot do this" was asserted without asking AWS,** and no feature request
   was raised, even though this repository already keeps `docs/aws-feature-requests/`
   for exactly that.

A note asking a future reader to be more careful does not survive contact with the
next deadline. This does: a claim of absence has to be in
`docs/agent/evidence-ledger.json`, and a ledger entry the design relies on has to
have been put to the vendor unless a vendor document already answers it.

## Why a baseline

539 lines in 281 tracked documents already read as claims of absence. Failing on
all of them would make the gate something people switch off. The baseline records
what was there when the gate was added; anything new has to comply. Stale baseline
entries fail too, so the ratchet cannot be loosened by editing a line and leaving
its old hash behind.

## What it does not do

It cannot tell a careful claim from a careless one. What it can do is make the
careless one impossible to leave unattributed, and make a premise that nobody
checked with the vendor fail out loud.
"""

# Copied from the canonical checker shared by every project.
# canonical: ~/.kiro/hooks/scripts/evidence_claims.py  sha256:7550d98f5393fe56
# Edit the canonical copy, then re-run the installer. Editing this copy alone
# means one project's gate quietly differs from the rest.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    """The repository the caller is working in, not the one this file lives in.

    This copy is the canonical one and is shared by every project, so it must not
    resolve paths relative to itself. `EVIDENCE_ROOT` wins so a caller can point it at
    a fixture; otherwise git decides, and the current directory is the fallback for a
    directory that is not a repository at all.

    Returns:
        The directory to treat as the repository root.
    """
    override = os.environ.get("EVIDENCE_ROOT")
    if override:
        return Path(override).resolve()
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607 - git from PATH by design
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


ROOT = _repo_root()

#: Both locations are accepted so a project that keeps agent documentation elsewhere
#: is not forced to move it. The first that exists wins; the installer creates the
#: first one.
#: `docs/` and `doc/` both occur across these repositories, so both are accepted rather
#: than one of them being imposed -- a ledger in a directory the project does not use is
#: a file nobody opens.
LEDGER_CANDIDATES = (
    Path("docs/agent/evidence-ledger.json"),
    Path("doc/agent/evidence-ledger.json"),
    Path("docs/evidence-ledger.json"),
    Path("doc/evidence-ledger.json"),
    Path(".evidence-ledger.json"),
)
LEDGER = next((ROOT / c for c in LEDGER_CANDIDATES if (ROOT / c).is_file()), ROOT / LEDGER_CANDIDATES[0])
BASELINE = ROOT / os.environ.get("EVIDENCE_BASELINE", "scripts/evidence_claims_baseline.json")

TIERS = ("documented", "verified", "hypothesis", "open")
WEAK_TIERS = ("hypothesis", "open")
INQUIRY_STATES = ("required", "filed", "answered", "not-needed")
REQUEST_STATES = ("not-yet", "filed", "answered", "declined", "not-applicable")
REQUIRED_FIELDS = ("id", "claim", "subject", "tier", "premise", "sources", "support_inquiry", "appears_in")

#: Phrasings that assert a capability is absent, limited or impossible.
#
#: Both voices for each verb, because the first version of this pattern had only the
#: passive `提供されていない` and went quiet on `提供していない` -- a detector is as
#: narrow as its list, and the gap was found by a test rather than by rereading it.
#: The verb list is the part that keeps going quiet, so it is a named set with a corpus
#: test behind it. Three gaps were found this way rather than by rereading: the passive
#: `提供されていない` without the active `提供していない`, and `does not expose` after
#: `does not support` was already there.
_JA_VERBS = "対応|サポート|提供|公開|実装|出力|返却|露出"
_JA_ABLE = "取得|使用|利用|指定|変更|設定|参照|監視|計測|確認"
_EN_VERBS = "support|expose|provide|publish|offer|emit|return|include|surface|report"

ABSENCE = re.compile(
    rf"((?:{_JA_VERBS})(?:していない|していません|されていない|されていません|しておらず|されておらず)"
    rf"|未対応|未サポート|未実装"
    rf"|(?:{_JA_ABLE})(?:できない|できません)"
    r"|存在しない|存在しません|できません|できない|不可能|持たない|持っていない|返さない"
    rf"|(?:does not|doesn't|do not|don't|cannot|can't|will not|won't)\s+(?:{_EN_VERBS})"
    r"|not supported|no support for|unsupported"
    r"|cannot |can't |unavailable|not available|does not exist|no way to|impossible)"
)

#: A vendor or service name, so ordinary prose about the portal's own behaviour is
#: not swept in. "This panel cannot be opened twice" is not a claim about AWS.
VENDOR = re.compile(
    r"AWS|Amazon|FSx|ONTAP|NetApp|CloudWatch|Bedrock|Harvest|Prometheus|Grafana"
    r"|Cognito|AppSync|SnapLock|FlexCache|FlexGroup|SnapMirror|S3|Athena|Glue"
    r"|EventBridge|Secrets Manager|Transfer Family|Textract|Comprehend|Rekognition"
    r"|SageMaker|DataSync|Fargate|Lambda|DynamoDB|Step Functions"
)

#: Markers that attach evidence to a line, on the line itself or the one before it.
LEDGER_REF = re.compile(r"\[E-\d{3}\]")

#: What counts as a reason after a marker's colon.
#:
#: `\S` alone is not enough: these markers are written inside HTML comments, so
#: `<!-- allow:unverified: -->` ends in `-->` and the `-` satisfied `\S`. The empty
#: form therefore passed as an explanation, which is the form to expect from somebody
#: silencing a finding rather than explaining it. Requires a character that is not part
#: of the comment terminator.
_REASON = r"\s*[^\s\->][^\n]*"

ALLOW = re.compile(rf"allow:unverified:{_REASON}")

#: Prose that quotes or illustrates a claim of absence without making one.
#:
#: Distinct from `allow:unverified` because the two say different things, and one of
#: them would be a lie here: `unverified` means the claim is deliberately speculative,
#: while this means the line is not a claim at all. Any document that discusses claims
#: trips the detector on its own examples -- `evidence-discipline.md` did, on the
#: template sentence it exists to quote -- and rewording the example to dodge the
#: pattern would damage the document to suit the tool. Still requires a reason, so the
#: reader can tell an example from an evasion.
ALLOW_NOT_A_CLAIM = re.compile(rf"allow:not-a-claim:{_REASON}")

#: Directories whose contents are drafts rather than published claims.
SKIP_PREFIXES = ("drafts/",)


def _rel(path: Path) -> str:
    """Repository-relative form of a path, or the path itself when outside.

    Args:
        path: Path to render.

    Returns:
        A string suitable for a message.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _gitignored(rel_path: str) -> bool:
    """Whether git would ignore the given repository-relative path.

    Args:
        rel_path: Path relative to the repository root.

    Returns:
        True when the path is ignored.
    """
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "check-ignore", "-q", rel_path],  # noqa: S607 - git from PATH by design
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _tracked_markdown() -> list[str]:
    """Every tracked markdown file, minus the draft directories.

    Returns:
        Repository-relative paths.
    """
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "*.md"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return [p for p in out if not p.startswith(SKIP_PREFIXES)]


def _fingerprint(line: str) -> str:
    """A stable identity for a line of prose, insensitive to whitespace.

    Args:
        line: The raw line.

    Returns:
        Ten hex characters, enough to distinguish lines within one file.
    """
    # `usedforsecurity=False` rather than a suppression comment: it states the intent
    # in the call itself, which is what both a reader and bandit are asking for. The
    # digest is unchanged by the flag, so the baseline's fingerprints stay valid.
    normalised = " ".join(line.split()).encode("utf-8")
    return hashlib.sha1(normalised, usedforsecurity=False).hexdigest()[:10]


def scan(paths: list[str]) -> dict[str, list[tuple[int, str, str]]]:
    """Find unattributed claims of absence.

    Code fences are skipped: a shell comment or a JSON string is not prose, and
    treating it as prose is how a detector starts reporting the thing it is written
    inside of.

    Args:
        paths: Repository-relative markdown paths.

    Returns:
        Mapping of path to a list of (line number, fingerprint, line text).
    """
    found: dict[str, list[tuple[int, str, str]]] = {}
    for rel in paths:
        target = ROOT / rel
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        in_fence = False
        previous = ""
        hits: list[tuple[int, str, str]] = []
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                previous = line
                continue
            if in_fence:
                previous = line
                continue
            if ABSENCE.search(line) and VENDOR.search(line):
                context = line + "\n" + previous
                if not (LEDGER_REF.search(context) or ALLOW.search(context) or ALLOW_NOT_A_CLAIM.search(context)):
                    hits.append((number, _fingerprint(line), line.strip()))
            previous = line
        if hits:
            found[rel] = hits
    return found


def load_ledger() -> list[dict]:
    """Read the ledger, failing loudly rather than reporting a clean tree.

    Returns:
        The claim entries.

    Raises:
        SystemExit: when the ledger is missing, unparseable or empty.
    """
    if not LEDGER.is_file():
        raise SystemExit(
            f"FAIL: {_rel(LEDGER)} is missing. A ledger that cannot be read reports "
            "no claims, which is indistinguishable from having none."
        )
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {_rel(LEDGER)} is not valid JSON: {exc}") from exc
    claims = data.get("claims")
    if not isinstance(claims, list):
        raise SystemExit(f"FAIL: {_rel(LEDGER)} has no `claims` list")
    # An empty list is allowed, and a freshly installed project starts that way. The
    # earlier version failed on it, reasoning that a ledger with nothing in it passes
    # forever -- which was true of the repository this began in and false of a new one:
    # the document scan is the other half of the gate and stays live, so a new
    # unattributed claim fails whether or not any claim has been recorded yet. Failing
    # here meant every commit in a just-adopted project was blocked, which is exactly
    # the shape that gets a gate uninstalled.
    return claims


def check_ledger(claims: list[dict], *, policy: bool = True) -> list[str]:
    """Validate every ledger entry.

    Two kinds of rule live here and the difference matters. **Structural** rules are
    invariants: an entry without a source, a source read from a snippet, a
    `private_ref` git does not ignore. Those must hold at all times, so the tests
    assert them against the committed ledger.

    **Policy** rules are the work: a premise resting on an inference that nobody put
    to the vendor. Those are expected to be red while the asking is outstanding, and
    a red gate there is the gate doing its job rather than a broken build. They are
    separated so that a test can pin the invariants without freezing the outstanding
    work into an assertion that has to be edited when it is done.

    Args:
        claims: Entries from the ledger.
        policy: Include the rules about whether the vendor has been asked.

    Returns:
        Human-readable problems. Empty means the ledger is sound.
    """
    problems: list[str] = []
    seen: set[str] = set()

    for index, entry in enumerate(claims):
        label = entry.get("id") or f"entry #{index}"

        missing = [f for f in REQUIRED_FIELDS if f not in entry or entry[f] in (None, "")]
        if missing:
            problems.append(f"{label}: missing required field(s): {', '.join(missing)}")
            continue

        if not re.fullmatch(r"E-\d{3}", entry["id"]):
            problems.append(f"{label}: id must look like E-001")
        if entry["id"] in seen:
            problems.append(f"{label}: duplicate id; two entries would answer for each other")
        seen.add(entry["id"])

        tier = entry["tier"]
        if tier not in TIERS:
            problems.append(f"{label}: tier is {tier!r}; expected one of {', '.join(TIERS)}")
            continue

        sources = entry["sources"]
        if not isinstance(sources, list):
            problems.append(f"{label}: sources must be a list")
            continue

        for source in sources:
            if not isinstance(source, dict) or not source.get("url"):
                problems.append(f"{label}: every source needs a url")
                continue
            if not source.get("retrieved"):
                problems.append(f"{label}: source {source['url']} has no `retrieved` date")
            read = source.get("read")
            if read not in ("full", "selective"):
                problems.append(
                    f"{label}: source {source['url']} has read={read!r}. Use 'full' or "
                    "'selective'. A search-result snippet is not a source -- quoting one "
                    "without opening the page is how a contradiction that did not exist "
                    "got written down."
                )

        if tier == "documented":
            full = [s for s in sources if isinstance(s, dict) and s.get("read") == "full"]
            if not full:
                problems.append(
                    f"{label}: tier is 'documented' but no source was read in full. "
                    "A selective search returning no matches is not evidence of absence."
                )
        if tier == "verified" and not entry.get("observation"):
            problems.append(f"{label}: tier is 'verified' but there is no `observation`")

        inquiry = entry["support_inquiry"]
        if not isinstance(inquiry, dict) or inquiry.get("status") not in INQUIRY_STATES:
            problems.append(f"{label}: support_inquiry.status must be one of {', '.join(INQUIRY_STATES)}")
            continue
        if not inquiry.get("topic"):
            problems.append(f"{label}: support_inquiry needs a `topic` saying what is being asked")

        if inquiry["status"] in ("filed", "answered", "required"):
            private_ref = inquiry.get("private_ref")
            if not private_ref:
                problems.append(
                    f"{label}: support_inquiry needs `private_ref` -- the case number goes "
                    "in a gitignored file, never in this ledger"
                )
            elif not _gitignored(private_ref):
                problems.append(
                    f"{label}: support_inquiry.private_ref is {private_ref}, which git does "
                    "not ignore. That is where the case number goes and this repository is public."
                )

        request = entry.get("feature_request") or {}
        if request.get("status") not in REQUEST_STATES:
            problems.append(f"{label}: feature_request.status must be one of {', '.join(REQUEST_STATES)}")

        # The rule this check exists for.
        if policy and entry["premise"] and tier in WEAK_TIERS and inquiry["status"] == "required":
            problems.append(
                f"{label}: premise=true and tier={tier}, but the vendor has not been asked.\n"
                f"      Claim: {entry['claim']}\n"
                "      A design resting on an inference nobody put to the vendor is the "
                "failure this ledger exists to stop. Either ask (`make support-inquiry-file "
                f"ID={entry['id']}`), lower `premise` to false and stop relying on it, or "
                "raise the tier with a source read in full."
            )

        if policy and inquiry["status"] == "answered" and request.get("status") == "not-yet":
            problems.append(
                f"{label}: the vendor answered and no feature request was raised. If the "
                "answer was that it is unavailable, that belongs in "
                "docs/aws-feature-requests/. If the answer made the claim moot, set "
                "feature_request.status to 'not-applicable'."
            )

        for where in entry["appears_in"]:
            if not (ROOT / where).exists():
                problems.append(
                    f"{label}: appears_in names {where}, which does not exist. A pointer "
                    "that resolves to nothing leaves the claim unreadable."
                )

    return problems


def load_baseline() -> dict[str, list[str]]:
    """Read the baseline of pre-existing unattributed claims.

    Returns:
        Mapping of path to accepted fingerprints. Empty when the file is absent.
    """
    if not BASELINE.is_file():
        return {}
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return data.get("baseline", {})


def write_baseline(found: dict[str, list[tuple[int, str, str]]]) -> None:
    """Record the current unattributed claims as accepted.

    Args:
        found: Output of :func:`scan`.
    """
    payload = {
        "$comment": [
            "Claims of vendor absence that predate scripts/check_evidence_claims.py.",
            "Not an approval. The gate ratchets: nothing new may be added without a",
            "ledger entry, and an entry here that no longer matches any line fails too,",
            "so a line cannot be edited while leaving its old fingerprint behind.",
            "Shrinking this file is the work. Regenerate with --update-baseline only",
            "after deciding that each newly added line genuinely predates the gate.",
        ],
        "baseline": {path: sorted(fp for _, fp, _ in hits) for path, hits in sorted(found.items())},
    }
    BASELINE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_scan(
    found: dict[str, list[tuple[int, str, str]]],
    baseline: dict[str, list[str]],
    scanned: set[str] | None = None,
) -> list[str]:
    """Compare what was found against the baseline, in both directions.

    Args:
        found: Output of :func:`scan`.
        baseline: Output of :func:`load_baseline`.
        scanned: Paths that were actually looked at. Staleness is only judged for
            those: a run limited to one file would otherwise report every baseline
            entry in every other file as stale, which made `check_evidence_claims.py
            <path>` fail every time it was used.

    Returns:
        Human-readable problems.
    """
    problems: list[str] = []
    for path, hits in sorted(found.items()):
        accepted = set(baseline.get(path, ()))
        for number, fingerprint, text in hits:
            if fingerprint in accepted:
                continue
            problems.append(
                f"{path}:{number}: claim of vendor absence with no evidence attached\n"
                f"      {text[:160]}\n"
                "      Add an entry to docs/agent/evidence-ledger.json and reference it as "
                "[E-nnn] on this line or the one above, or mark the line "
                "`allow:unverified: <reason>` when it is deliberately speculative, or "
                "`allow:not-a-claim: <reason>` when the line quotes or illustrates a "
                "claim without making one."
            )

    live = {path: {fp for _, fp, _ in hits} for path, hits in found.items()}
    for path, fingerprints in sorted(baseline.items()):
        if scanned is not None and path not in scanned:
            continue
        stale = sorted(set(fingerprints) - live.get(path, set()))
        if stale:
            problems.append(
                f"{path}: {len(stale)} baseline entr{'y' if len(stale) == 1 else 'ies'} no longer "
                "match any line. Remove them from scripts/evidence_claims_baseline.json -- a "
                "baseline that keeps fingerprints for text that has changed is a hole that "
                "reopens the next time the line comes back."
            )
    return problems


def main() -> int:
    """Entry point.

    Returns:
        0 when the ledger is sound and no new unattributed claim exists.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true", help="record current findings as accepted")
    parser.add_argument("--list", action="store_true", help="print the ledger and exit 0")
    parser.add_argument("--self-test", action="store_true", help="verify the detector fires on a known claim")
    parser.add_argument("paths", nargs="*", help="limit the scan to these paths")
    args = parser.parse_args()

    if args.list:
        for entry in load_ledger():
            inquiry = entry.get("support_inquiry", {}).get("status", "?")
            flag = "premise" if entry.get("premise") else "-"
            print(
                f"{entry.get('id')}  tier={entry.get('tier'):10s} {flag:8s} support={inquiry:10s} {entry.get('claim', '')[:80]}"
            )
        return 0

    if args.self_test:
        # A gate that passes without running is worse than no gate. This asserts the
        # detector fires, rather than trusting that it would.
        sample = "AWS does not support this, and Amazon CloudWatch has no such metric."
        ok = bool(ABSENCE.search(sample) and VENDOR.search(sample))
        marked = "AWS does not support this [E-001]"
        suppressed = LEDGER_REF.search(marked) is not None
        print(f"detector fires on an unmarked claim: {ok}")
        print(f"a ledger reference suppresses it:   {suppressed}")
        return 0 if (ok and suppressed) else 1

    paths = args.paths or _tracked_markdown()
    found = scan(paths)

    if args.update_baseline:
        write_baseline(found)
        total = sum(len(v) for v in found.values())
        print(f"baseline written: {total} line(s) across {len(found)} file(s) recorded as pre-existing")
        return 0

    problems = check_ledger(load_ledger())
    problems += check_scan(found, load_baseline(), scanned=set(paths))

    if problems:
        print("FAIL: evidence for claims of vendor absence\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    claims = load_ledger()
    weak = [c for c in claims if c["premise"] and c["tier"] in WEAK_TIERS]
    print(
        f"evidence OK: {len(claims)} claim(s) in the ledger, {len(weak)} premise(s) resting on "
        f"an inference (all with the vendor asked), {sum(len(v) for v in found.values())} "
        "pre-existing line(s) within the baseline"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
