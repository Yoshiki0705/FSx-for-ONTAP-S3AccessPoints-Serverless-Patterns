#!/usr/bin/env python3
"""Put a claim of vendor absence to AWS Support, from the ledger, without leaking.

## Why this is a script and not a browser tab

`docs/agent/evidence-ledger.json` can require that a claim was put to the vendor
before the design may rest on it (see `scripts/check_evidence_claims.py`). A
requirement that can only be satisfied by hand, in a console, is a requirement that
gets skipped -- which is what happened: "FSx for ONTAP S3 Access Points have no
CloudWatch metrics" became a design premise without anyone asking AWS whether that
was true or planned.

## The two rules this enforces

1. **The case body comes from the ledger.** Not from a fresh paragraph typed at the
   moment of asking. The ledger already carries the claim, the sources that were read
   in full, and what was observed by running something -- which is exactly what makes
   a support case answerable rather than a question AWS has to reverse-engineer.
2. **The case number never lands in a tracked file.** This repository is public and
   its git history is permanent. The identifier goes into the gitignored path named by
   `support_inquiry.private_ref`, and the ledger records only that it was filed and
   when. The check verifies that path is actually ignored; this script refuses to
   write if it is not.

## Filing is not free and not reversible

A case is visible to AWS, is attributed to the account, and cannot be unsent. So
`--file` refuses to act without `--confirm`, and prints the body first. `--draft` is
the default because reading what is about to be sent is the cheap step.
"""

# Copied from the canonical checker shared by every project.
# canonical: ~/.kiro/hooks/scripts/aws_support_inquiry.py  sha256:00b3e96fce7d3c35
# Edit the canonical copy, then re-run the installer. Editing this copy alone
# means one project's gate quietly differs from the rest.

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    """The repository the caller is working in, not the one this file lives in.

    This copy is shared by every project, so resolving relative to itself would make it
    read one project's ledger while filing for another.

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

#: The Support API is global and answers in this Region only.
SUPPORT_REGION = "us-east-1"

#: Prefix on every subject, so `--list` can find what this tool filed without
#: keeping a list of case identifiers anywhere.
SUBJECT_PREFIX = "[evidence-ledger]"

#: Used when a ledger entry names no `support_inquiry.service_code`. Most claims here
#: are about FSx for ONTAP; the ones that are not have to say so, or they land in the
#: wrong queue and are answered late.
DEFAULT_SERVICE_CODE = "amazon-fsx"


def _load() -> list[dict]:
    """Read the ledger.

    Returns:
        The claim entries.

    Raises:
        SystemExit: when the ledger cannot be read.
    """
    if not LEDGER.is_file():
        raise SystemExit(f"FAIL: {LEDGER} is missing")
    return json.loads(LEDGER.read_text(encoding="utf-8"))["claims"]


def _save(claims: list[dict]) -> None:
    """Write the claims back, preserving the file's comment block.

    Args:
        claims: The full list of entries to persist.
    """
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    data["claims"] = claims
    LEDGER.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _entry(claims: list[dict], claim_id: str) -> dict:
    """Find one entry by id.

    Args:
        claims: All entries.
        claim_id: The id to look for.

    Returns:
        The matching entry.

    Raises:
        SystemExit: when no entry has that id.
    """
    for entry in claims:
        if entry.get("id") == claim_id:
            return entry
    raise SystemExit(f"FAIL: no ledger entry with id {claim_id}")


def _gitignored(rel_path: str) -> bool:
    """Whether git would ignore the given repository-relative path.

    Args:
        rel_path: Path relative to the repository root.

    Returns:
        True when the path is ignored.
    """
    return (
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "check-ignore", "-q", rel_path],  # noqa: S607 - git from PATH by design
            cwd=ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def build_body(entry: dict) -> str:
    """Compose the case body from the ledger entry.

    Every part of this is already public: the claim, the documents read, and an
    observation with its environment. Nothing account-specific is added here -- when a
    resource identifier is needed, it comes from `--detail-file`, which has to be a
    gitignored path.

    Args:
        entry: A ledger entry.

    Returns:
        The case body.
    """
    lines = [
        "We are documenting a public reference architecture and need to state,",
        "accurately, whether the following is supported today.",
        "",
        f"CLAIM UNDER TEST ({entry['id']}):",
        f"  {entry['claim']}",
        "",
        f"OUR CONFIDENCE: {entry['tier']}",
        "",
        "QUESTION:",
        f"  {entry['support_inquiry']['topic']}",
        "",
        "DOCUMENTATION WE READ (in full unless noted):",
    ]
    for source in entry.get("sources", []):
        note = "" if source.get("read") == "full" else f" [{source.get('read')}]"
        lines.append(f"  - {source['url']} (retrieved {source.get('retrieved')}){note}")
        if source.get("says"):
            lines.append(f"      {source['says']}")
    if entry.get("observation"):
        lines += ["", "WHAT WE OBSERVED BY RUNNING IT:", f"  {entry['observation']}"]
    if entry.get("why_not_documented_is_not_absent"):
        lines += ["", "WHY WE ARE ASKING RATHER THAN CONCLUDING:", f"  {entry['why_not_documented_is_not_absent']}"]
    lines += [
        "",
        "WHAT WOULD HELP:",
        "  1. Confirmation of whether a documented mechanism exists today.",
        "  2. If it does not, whether it is on the roadmap, so we can describe the",
        "     current state without implying it will never exist.",
        "  3. If the documentation is ambiguous on this point, we would like to raise",
        "     that as documentation feedback.",
    ]
    return "\n".join(lines)


def _client() -> Any:
    """A Support API client, or a clear failure when the plan does not allow it.

    Returns:
        A boto3 ``support`` client. Typed as ``Any`` because botocore builds its
        clients at runtime and exports no type for them.

    Raises:
        SystemExit: when boto3 is missing or the account cannot use the Support API.
    """
    try:
        import boto3  # noqa: PLC0415 - imported lazily so --draft works without it
        from botocore.exceptions import ClientError  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit(f"FAIL: boto3 is required to reach the Support API: {exc}") from exc

    client = boto3.client("support", region_name=SUPPORT_REGION)
    try:
        client.describe_severity_levels()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("SubscriptionRequiredException", "AccessDeniedException"):
            raise SystemExit(
                "FAIL: this account cannot use the AWS Support API "
                f"({code}). The API needs Business, Enterprise On-Ramp or Enterprise "
                "support. Until then, set support_inquiry.status by hand after asking "
                "through the console, and keep the case number in the gitignored "
                "private_ref -- not in the ledger."
            ) from exc
        raise
    return client


def build_body_ja(entry: dict) -> str:
    """Compose the case body in Japanese, in the order a responder needs it.

    Ordered so the first screen answers "what is being asked and about which resource",
    because a case that opens with background gets a first reply asking for the basics.
    The sections are the ones this project can justify independently: the concrete user
    problem, the resource this was observed on with its region and date, the exact calls
    made and their output, what was already read and ruled out, the decision that is
    blocked, and what an answer would let us do.

    The AWS technical-inquiry guidelines page could not be read (its body does not render
    for a text fetch, and the English URL 404s), so this is not a claim of conformance to
    it -- only that each section here has a reason to exist.

    Args:
        entry: A ledger entry.

    Returns:
        The case body.
    """
    inquiry = entry["support_inquiry"]
    lines = [
        "【伺いたいこと】",
        f"  {inquiry['topic']}",
        "",
        "【解決したい利用者の課題】",
        f"  {entry.get('user_problem', '(未記入)')}",
        "",
        "【現時点の当方の理解（誤っていればご指摘ください）】",
        f"  {entry.get('claim_ja') or entry['claim']}",
        "",
        "【確認済みのドキュメント】",
    ]
    for source in entry.get("sources", []):
        note = "" if source.get("read") == "full" else f"（{source.get('read')}）"
        lines.append(f"  - {source['url']}  取得日 {source.get('retrieved')}{note}")
        if source.get("says"):
            lines.append(f"      記載内容: {source['says']}")
    if entry.get("observation"):
        lines += ["", "【実施した確認とその結果】", f"  {entry.get('observation_ja') or entry['observation']}"]
    if entry.get("ruled_out"):
        lines += ["", "【切り分けとして除外した可能性】"]
        lines += [f"  - {item}" for item in entry["ruled_out"]]
    if entry.get("why_not_documented_is_not_absent"):
        lines += [
            "",
            "【断定を避けている理由】",
            f"  {entry.get('why_not_documented_is_not_absent_ja') or entry['why_not_documented_is_not_absent']}",
        ]
    lines += [
        "",
        "【この回答で決まること】",
        f"  {entry.get('decision_blocked', '(未記入)')}",
        "",
        "【期待する回答】",
        "  1. 現時点でドキュメントに記載された手段が存在するかどうか",
        "  2. 存在しない場合、対応予定の有無（「未対応」と公開ドキュメントに書く前に確認したいため）",
        "  3. ドキュメントの記述が曖昧な箇所があれば、ドキュメントフィードバックとして扱っていただけるか",
        "",
        "【緊急度】",
        "  低。稼働中の障害ではなく、公開する設計文書の記述と設計判断のための確認です。",
    ]
    if entry.get("category_note"):
        lines += ["", "【ケース分類について】", f"  {entry['category_note']}"]
    return "\n".join(lines)


def _language(entry: dict) -> str:
    """Case language. Japanese by default: this account is served by the JP team."""
    return entry["support_inquiry"].get("language", "ja")


def _service(entry: dict) -> str:
    """Service queue for the case, from the ledger."""
    return entry["support_inquiry"].get("service_code", DEFAULT_SERVICE_CODE)


def _category(entry: dict) -> str:
    """Category within the service queue, from the ledger."""
    return entry["support_inquiry"].get("category_code", "general-guidance")


def _body(entry: dict) -> str:
    """The body in the case's language."""
    return build_body_ja(entry) if _language(entry) == "ja" else build_body(entry)


def _subject(entry: dict) -> str:
    """Subject line: what is asked, not what we concluded."""
    inquiry = entry["support_inquiry"]
    return inquiry.get("subject") or f"{SUBJECT_PREFIX} {entry['claim'][:110]}"


def cmd_draft(entry: dict) -> int:
    """Print what would be sent, and change nothing.

    Args:
        entry: A ledger entry.

    Returns:
        0.
    """
    print(f"SUBJECT: {_subject(entry)}")
    print(f"service={_service(entry)}  category={_category(entry)}  language={_language(entry)}")
    print("-" * 72)
    print(_body(entry))
    print("-" * 72)
    print("Nothing was sent. Add --file --confirm to open the case.")
    return 0


def cmd_file(claims: list[dict], entry: dict, detail_file: str | None, confirm: bool) -> int:
    """Open a support case for the entry and record it without leaking the number.

    Args:
        claims: All entries, so the ledger can be written back.
        entry: The entry to ask about.
        detail_file: Optional gitignored file whose contents are appended.
        confirm: Must be true; filing is visible to AWS and cannot be unsent.

    Returns:
        0 on success.

    Raises:
        SystemExit: when confirmation is missing or a path would leak.
    """
    inquiry = entry["support_inquiry"]
    private_ref = inquiry.get("private_ref")
    if not private_ref:
        raise SystemExit(f"FAIL: {entry['id']} has no support_inquiry.private_ref to record the case number in")
    if not _gitignored(private_ref):
        raise SystemExit(
            f"FAIL: private_ref {private_ref} is not gitignored. That is where the case "
            "number goes and this repository is public."
        )

    # Filing into the wrong queue costs a round trip and looks like the answer is
    # slow. The default is the service most of these claims are about; anything else
    # has to say so. Guessing a service code here would be the same class of act this
    # ledger exists to prevent -- an unverified value written down as if checked.
    if entry.get("subject_service") and not inquiry.get("service_code"):
        raise SystemExit(
            f"FAIL: {entry['id']} names subject_service={entry['subject_service']!r} but no "
            "support_inquiry.service_code. Look the code up with "
            "`aws support describe-services` and record it, rather than letting the case "
            f"land in the {DEFAULT_SERVICE_CODE} queue."
        )

    body = _body(entry)
    if detail_file:
        if not _gitignored(detail_file):
            raise SystemExit(
                f"FAIL: --detail-file {detail_file} is not gitignored. Account and resource "
                "identifiers must not be readable from a tracked path."
            )
        body += "\n\nENVIRONMENT DETAIL:\n" + (ROOT / detail_file).read_text(encoding="utf-8")

    if not confirm:
        cmd_draft(entry)
        raise SystemExit(
            "FAIL: refusing to open a case without --confirm. A case is visible to AWS, "
            "is attributed to this account, and cannot be unsent."
        )

    client = _client()
    result = client.create_case(
        subject=_subject(entry),
        # From the ledger, because the queue decides who answers. A question about
        # Amazon Managed Service for Prometheus filed against the FSx service code is
        # answered late by someone who has to route it first.
        serviceCode=_service(entry),
        severityCode="low",
        categoryCode=_category(entry),
        communicationBody=body,
        issueType="technical",
        language=_language(entry),
    )
    case_id = result["caseId"]

    target = ROOT / private_ref
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(f"\n- {entry['id']}  filed {date.today().isoformat()}  case {case_id}\n")

    inquiry["status"] = "filed"
    inquiry["filed"] = date.today().isoformat()
    _save(claims)

    print(f"case opened for {entry['id']}. Identifier appended to {private_ref} (gitignored).")
    print("Ledger updated: support_inquiry.status = filed. The case number is not in it.")
    return 0


def _recorded_case_ids(claims: list[dict]) -> list[tuple[str, str]]:
    """Case identifiers recorded in the gitignored private refs, with their claim ids.

    Read from there rather than matched by subject. The first version filtered
    `describe_cases` on a subject prefix, which stopped finding anything the moment a
    ledger entry set its own Japanese subject -- the tool had filed two cases and then
    reported that it had filed none.

    Args:
        claims: Ledger entries, for the private_ref paths.

    Returns:
        Pairs of (claim id, case id), oldest first.
    """
    seen: set[str] = set()
    found: list[tuple[str, str]] = []
    for entry in claims:
        ref = entry.get("support_inquiry", {}).get("private_ref")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        path = ROOT / ref
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.search(r"^-\s*(\S+)\s+filed\s+\S+\s+case\s+(\S+)", line.strip())
            if match:
                found.append((match.group(1), match.group(2)))
    return found


def cmd_list(claims: list[dict]) -> int:
    """List the cases this tool opened, from the recorded identifiers.

    The case numbers themselves are not printed: they live only in the gitignored
    private refs, and a terminal transcript is one of the ways they escape.

    Args:
        claims: Ledger entries.

    Returns:
        0.
    """
    recorded = _recorded_case_ids(claims)
    if not recorded:
        print("no cases recorded by this tool")
        return 0
    client = _client()
    ids = [case_id for _, case_id in recorded]
    cases = {}
    for start in range(0, len(ids), 20):
        batch = client.describe_cases(caseIdList=ids[start : start + 20], includeResolvedCases=True, language="ja").get(
            "cases", []
        )
        cases.update({c["caseId"]: c for c in batch})
    for claim_id, case_id in recorded:
        case = cases.get(case_id)
        if case is None:
            print(f"{claim_id}: recorded but not readable from this account")
            continue
        print(
            f"{claim_id}  {case['status']:18s} {case['timeCreated'][:10]}  "
            f"{case['serviceCode'][:38]:38s} {case['subject'][:44]}"
        )
    return 0


def cmd_status(claims: list[dict]) -> int:
    """Show, for every entry, whether the vendor has been asked.

    Args:
        claims: All entries.

    Returns:
        0.
    """
    for entry in claims:
        inquiry = entry["support_inquiry"]
        flag = "PREMISE" if entry["premise"] else "-"
        blocking = entry["premise"] and entry["tier"] in ("hypothesis", "open") and inquiry["status"] == "required"
        mark = "  <-- blocks the gate" if blocking else ""
        print(f"{entry['id']}  {entry['tier']:10s} {flag:8s} support={inquiry['status']:10s}{mark}")
    return 0


def main() -> int:
    """Entry point.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", help="ledger claim id, e.g. E-001")
    parser.add_argument("--draft", action="store_true", help="print the case body and send nothing (default)")
    parser.add_argument("--file", action="store_true", help="open the support case")
    parser.add_argument("--confirm", action="store_true", help="required by --file")
    parser.add_argument("--detail-file", help="gitignored file whose contents are appended to the body")
    parser.add_argument("--list", action="store_true", help="list cases opened by this tool")
    parser.add_argument("--status", action="store_true", help="show which entries still block the gate")
    args = parser.parse_args()

    claims = _load()
    if args.list:
        return cmd_list(claims)
    if args.status or not args.id:
        return cmd_status(claims)

    entry = _entry(claims, args.id)
    if args.file:
        return cmd_file(claims, entry, args.detail_file, args.confirm)
    return cmd_draft(entry)


if __name__ == "__main__":
    sys.exit(main())
