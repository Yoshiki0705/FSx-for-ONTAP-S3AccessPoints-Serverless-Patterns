"""Tests for the vendor-neutrality checker.

The point of these is the direction the predecessor could not be checked in. The
rule was a `grep` inlined in a workflow, and nothing asserted that a document it
should refuse actually fails -- so the gate's correctness rested on reading the
pattern, which is how a gate ends up reporting success while matching nothing.

So each test here fixes one of:
  - a ranking phrase is refused (the gate bites),
  - a trade-off written symmetrically passes (the gate is usable),
  - a legitimate use that would produce noise is not refused (the gate stays on),
  - an empty scan fails rather than printing a tick.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_neutral_wording import (  # noqa: E402
    ALLOW_MARKER,
    RULES,
    check_file,
    discover_files,
    main,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def write(tmp_path: Path, name: str, body: str) -> Path:
    """Create a file to scan."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --- The gate bites -------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "| Category | Service | Key differentiator |",
        "CloudFront delivery, the production preset's differentiator, also 200",
        "- 製品X はクラウド連携と API 公開が差別化要素",
        "他社列は公式ドキュメントに基づく記載です",
        "したがって他社の ✅ と当ポータルの ✅ は同じではありません",
        "この構成の優位性は明らかです",
        "競合ツールと比較すると",
        "S3 AP は NFS より優れています",
        "This is the strongest, a real game-changer",
        "最強のアーキテクチャ",
        "our competitive advantage in this space",
        "Option A is better than Option B",
        "DataSync is superior to a hand-rolled script",
    ],
)
def test_ranking_wording_is_refused(tmp_path: Path, line: str) -> None:
    """Each shape that ranks products is reported."""
    path = write(tmp_path, "doc.md", f"# Title\n\n{line}\n")
    findings = check_file(path)
    assert findings, f"not refused: {line!r}"


def test_case_is_ignored(tmp_path: Path) -> None:
    """`Differentiator` at the start of a heading is the same violation."""
    path = write(tmp_path, "doc.md", "## Differentiator\n")
    assert check_file(path)


def test_finding_carries_line_number_match_and_reason(tmp_path: Path) -> None:
    """A finding has to be actionable without re-reading the checker.

    "violation" alone leaves the author guessing which of several rules they hit
    and what to write instead, so the matched text and the reason travel with it.
    """
    path = write(tmp_path, "doc.md", "clean line\nthe key differentiator here\n")
    findings = check_file(path)
    assert len(findings) == 1
    lineno, matched, reason = findings[0]
    assert lineno == 2
    assert matched.lower() == "differentiator"
    assert reason.strip()


# --- The gate is usable ---------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "S3 AP suits object access; NFS suits POSIX workloads. Choose by workload.",
        "| Category | Service | Notable capabilities |",
        "The trade-off is latency against cost, stated for both options.",
        "比較対象の列は各サービスの公式ドキュメントに基づく記載です",
        "選定理由として挙がるのはクラウド連携と API 公開",
    ],
)
def test_trade_off_wording_passes(tmp_path: Path, line: str) -> None:
    """Neutral comparison framing is not a finding."""
    path = write(tmp_path, "doc.md", f"{line}\n")
    assert check_file(path) == []


@pytest.mark.parametrize(
    "line",
    [
        # `競合` on its own is technical contention, ~30 occurrences in this tree and
        # every one legitimate. Including the bare word would put dozens of findings
        # in front of a reader on every run, and a gate whose output is routinely
        # dismissed is a gate that gets removed.
        "VPC Endpoint の競合マトリクス",
        "S3 AP と NFS/SMB の帯域競合",
        "write conflict が発生した場合",
        "ポート競合を避けるため",
        # `顧客` likewise: 18 occurrences, all legitimate.
        "顧客データそのものではない",
        "顧客管理 CMK を使用する",
        # Spanish for "top bar", in docs/es/.
        "la barra superior de la pantalla",
        # A design note comparing two of our own implementation choices.
        "the 200 beats waiting for the list to settle",
    ],
)
def test_legitimate_use_is_not_refused(tmp_path: Path, line: str) -> None:
    """Words adjacent to the rule but legitimate here must not produce noise."""
    path = write(tmp_path, "doc.md", f"{line}\n")
    assert check_file(path) == []


def test_allow_marker_exempts_a_line(tmp_path: Path) -> None:
    """A document recording the guardrail has to be able to name what it forbids."""
    path = write(tmp_path, "doc.md", f"Do not write 'differentiator'. {ALLOW_MARKER}\n")
    assert check_file(path) == []


# --- Scope, and an empty scan ---------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["doc.md", "handler.py", "component.tsx", "config.ts", "template.yaml", "run.sh"],
)
def test_scan_covers_comments_not_only_markdown(tmp_path: Path, name: str) -> None:
    """Code and comments are published too.

    The naming check learned this the hard way: restricted to `.md`, it let the
    violation sit in a shell comment, a Python comment and a CloudFormation
    description indefinitely, because nothing looked there.
    """
    path = write(tmp_path, name, "# our key differentiator\n")
    assert check_file(path), f"{name} not audited"
    assert path in discover_files(tmp_path)


def test_rule_defining_paths_are_excluded(tmp_path: Path) -> None:
    """The workflow and AGENTS.md contain the words as the rule text itself."""
    write(tmp_path, ".github/workflows/audit.yml", "PATTERN='優位性|差別化'\n")
    write(tmp_path, "AGENTS.md", "Do not write 差別化 or differentiator.\n")
    kept = write(tmp_path, "docs/guide.md", "clean\n")
    assert discover_files(tmp_path) == [kept]


def test_named_path_still_honours_exclusions(tmp_path: Path) -> None:
    """CI passes changed files by name; a rule file among them is still excluded."""
    write(tmp_path, "AGENTS.md", "differentiator\n")
    assert discover_files(tmp_path, ["AGENTS.md"]) == []


def test_empty_scan_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No matches means the globs stopped fitting the tree, not a clean run.

    This is the failure the sibling IAM checker actually shipped: a hand-kept list
    that had drifted off the tree printed a tick over 35 unscanned directories. The
    assertion is on the exit code, because a checker can find nothing and still say
    so with a 0.
    """
    import check_neutral_wording as mod

    write(tmp_path, "docs/guide.md", "clean prose\n")
    monkeypatch.setattr(mod, "SCAN_GLOBS", ("**/*.nothing-matches-this",))
    assert discover_files(tmp_path) == []
    assert main([], project_root=tmp_path) == 1


def test_binary_file_is_not_a_finding(tmp_path: Path) -> None:
    """A file the checker cannot read is not one it can make a claim about."""
    path = tmp_path / "blob.md"
    path.write_bytes(b"\xff\xfe\x00\x01differentiator")
    assert check_file(path) == []


# --- Against the real tree ------------------------------------------------------


def test_every_rule_has_a_reason() -> None:
    """A pattern without a reason produces a finding nobody can act on."""
    for pattern, reason in RULES:
        assert pattern.strip(), "empty pattern"
        assert reason.strip(), f"no reason for {pattern!r}"


def test_real_tree_is_clean() -> None:
    """The tree passes, and enough files are scanned for that to mean something."""
    files = discover_files(ROOT)
    assert len(files) > 500, f"only {len(files)} files scanned — scope has narrowed"
    findings = {path.relative_to(ROOT).as_posix(): check_file(path) for path in files if check_file(path)}
    assert findings == {}, f"vendor-versus wording in the tree: {findings}"


def test_main_returns_zero_on_the_real_tree() -> None:
    """The exit code the gate actually reports."""
    assert main([]) == 0


def test_main_returns_one_on_a_violation(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """The exit code, and the report, on a tree carrying a ranking phrase."""
    write(tmp_path, "docs/bad.md", "clean line\nour key differentiator\n")
    assert main([], project_root=tmp_path) == 1
    out = capsys.readouterr().out
    assert "docs/bad.md:2" in out
    assert "differentiator" in out


def test_main_returns_zero_on_a_clean_fixture_tree(tmp_path: Path) -> None:
    """The other direction, over a tree that is genuinely scanned and genuinely clean."""
    write(tmp_path, "docs/good.md", "S3 AP suits object access; NFS suits POSIX work.\n")
    assert main([], project_root=tmp_path) == 0


def test_main_accepts_named_paths(tmp_path: Path) -> None:
    """The form CI uses to narrow a run to a pull request's changed files."""
    write(tmp_path, "docs/bad.md", "our key differentiator\n")
    write(tmp_path, "docs/good.md", "stated as a trade-off\n")
    assert main(["docs/good.md"], project_root=tmp_path) == 0
    assert main(["docs/bad.md"], project_root=tmp_path) == 1
