"""Tests for `scripts/check_incoming_probes.py`.

The checker's whole value is failing when a registered string is gone, so most of
this exercises the failing side. Three shapes are pinned because each one, if it
went the other way, would report a clean run while checking nothing:

- **zero rows** for this repository, from a contract that parsed. That is the
  repository name or the field order having moved, not "nothing registered".
- **an unrecognised role**. The vocabulary is two words; a third means the format
  changed or the row is a typo, and guessing which is how a probe stops being
  checked silently.
- **a skip standing in for a pass**. Every pull-request runner lacks the sibling
  checkout, so the default mode skips there. It has to say so.

The last test reads the real contract when a sibling checkout exists, which is the
only assertion here about the actual nine rows.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = ROOT / "scripts" / "check_incoming_probes.py"


def _load() -> ModuleType:
    """Import the checker by path.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location("check_incoming_probes", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_incoming_probes"] = module
    spec.loader.exec_module(module)
    return module


probes = _load()
REPO = probes.THIS_REPO_NAMES[0]


def _contract(*rows: str) -> str:
    """Build a contract body with a comment header, as the real file has.

    Args:
        rows: Tab-separated lines.

    Returns:
        The contract text.
    """
    return "# Generated - do not hand-edit.\n#\n" + "\n".join(rows) + "\n"


def _point_every_source_at(path: Path) -> dict[str, str]:
    """Environment overrides sending every source's lookup to one directory.

    Without this a test that patches only the Playbook's variable leaves the second source
    resolving against whatever sits beside the real checkout — so the assertion would
    depend on the machine.

    Args:
        path: Directory to treat as every sibling checkout.

    Returns:
        Variable names mapped to that path.
    """
    return {"SIBLING_" + s.repo.replace("-", "_").upper(): str(path) for s in probes.SOURCES}


def test_a_present_retraction_string_passes(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("the claim holds\n", encoding="utf-8")
    parsed, malformed = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tretraction\tthe claim holds"))
    assert not malformed
    assert probes.audit(parsed, root=tmp_path) == ([], [])


def test_a_missing_retraction_string_fails(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("the claim was reworded\n", encoding="utf-8")
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tretraction\tthe claim holds"))
    failures, warnings = probes.audit(parsed, root=tmp_path)
    assert not warnings
    assert len(failures) == 1
    assert "the claim holds" in failures[0], "the reason has to name the string that went missing"


def test_a_missing_reread_string_only_warns(tmp_path: Path) -> None:
    """`reread` pins a min or max, so adding a measurement rewrites it by construction."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("5 GB to 60 GB\n", encoding="utf-8")
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\treread\t5 GB to 50 GB"))
    failures, warnings = probes.audit(parsed, root=tmp_path)
    assert failures == []
    assert len(warnings) == 1


def test_an_absent_cited_file_fails(tmp_path: Path) -> None:
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/gone.md\tretraction\tanything"))
    failures, _ = probes.audit(parsed, root=tmp_path)
    assert len(failures) == 1
    assert "absent" in failures[0]


def test_an_unrecognised_role_fails_rather_than_being_skipped(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("present\n", encoding="utf-8")
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tadvisory\tpresent"))
    failures, _ = probes.audit(parsed, root=tmp_path)
    assert len(failures) == 1, "an unknown role must not pass just because the string happens to be there"
    assert "advisory" in failures[0]


def test_rows_for_other_repositories_are_ignored() -> None:
    parsed, _ = probes.parse_contract(
        _contract(
            "S3-Burst-on-ONTAP-Files\tdocs/x.md\tretraction\tnot ours",
            f"{REPO}\tdocs/a.md\tretraction\tours",
        )
    )
    assert [p.text for p in parsed] == ["ours"]


def test_the_previous_name_of_this_repository_is_still_recognised() -> None:
    """The contract is generated on their side, so which spelling appears is their state.

    Accepting only the current name would make a stale spelling read as "no rows
    registered", which is the same output as a clean run.
    """
    parsed, _ = probes.parse_contract(_contract("fsxn-s3ap-serverless-patterns\tdocs/a.md\tretraction\tx"))
    assert len(parsed) == 1


def test_a_hash_inside_a_probe_string_is_not_a_comment() -> None:
    parsed, malformed = probes.parse_contract(
        _contract(f"{REPO}\tdocs/a.md\tretraction\tsee #設定例 for the six patterns")
    )
    assert not malformed
    assert parsed[0].text == "see #設定例 for the six patterns"


def test_a_tab_inside_a_probe_string_is_kept() -> None:
    """The string is last and taken whole, so only the first three tabs are separators."""
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tretraction\tleft\tright"))
    assert parsed[0].text == "left\tright"


def test_a_short_row_is_reported_rather_than_dropped() -> None:
    _, malformed = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tretraction"))
    assert len(malformed) == 1


def test_nothing_is_normalised(tmp_path: Path) -> None:
    """Their index escapes markdown, so source and rendered forms differ by backslashes.

    Normalising either side turns a real break into a pass or the reverse.
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(r"a \* literal asterisk", encoding="utf-8")
    parsed, _ = probes.parse_contract(_contract(f"{REPO}\tdocs/a.md\tretraction\ta * literal asterisk"))
    failures, _ = probes.audit(parsed, root=tmp_path)
    assert len(failures) == 1, "an unescaped probe must not match escaped source"


def test_zero_rows_from_a_parsed_contract_is_a_finding(tmp_path: Path) -> None:
    """Finding none means the repository name or the field order moved, not an empty registration."""
    contract = tmp_path / "docs" / "agent" / probes.CONTRACT.name
    contract.parent.mkdir(parents=True)
    contract.write_text(_contract("Some-Other-Repository\tdocs/x.md\tretraction\tnot ours"), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", **_point_every_source_at(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == probes.EXIT_FINDINGS, proc.stdout + proc.stderr
    assert "registers nothing against" in proc.stderr


def test_a_skip_says_it_is_not_a_pass(tmp_path: Path) -> None:
    """Every pull-request runner lacks the checkouts, so this is the common path."""
    proc = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", **_point_every_source_at(tmp_path / "absent")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == probes.EXIT_CLEAN
    assert "SKIPPED" in proc.stdout and "not a pass" in proc.stdout


def test_the_published_contract_is_declared_published() -> None:
    """A 404 from `--fetch` has two opposite meanings and the response cannot tell them apart.

    Each contract was read over the network before its source was added here, so
    unreachable means gone.
    """
    assert probes.CONTRACT_IS_PUBLISHED is True


def test_every_source_is_read_not_only_the_first() -> None:
    """Two repositories cite this one, and reading one was the gap #401 left open.

    S3-Burst-on-ONTAP-Files published its contract after #401 merged and registered eight
    rows against this repository. Nothing here looked at them, because the reader held a
    single URL. A source list is what makes a third citer a data change rather than a code
    change.
    """
    assert len(probes.SOURCES) >= 2
    repos = [s.repo for s in probes.SOURCES]
    assert "FSx-for-ONTAP-Adoption-Playbook" in repos
    assert "S3-Burst-on-ONTAP-Files" in repos
    for source in probes.SOURCES:
        assert source.raw_url.startswith("https://raw.githubusercontent.com/"), source
        assert source.raw_url.endswith(probes.CONTRACT.as_posix()), source
        assert source.checkout_names, source


def test_findings_beat_undetermined_when_both_happen() -> None:
    """The numerically larger code is 2, and returning it would bury an actionable break.

    A string that is gone can be acted on now. A contract that could not be read is a
    question about the check itself.
    """
    assert probes.EXIT_FINDINGS < probes.EXIT_UNDETERMINED, (
        "if this ordering changes, the precedence in main() has to be re-read rather than kept"
    )


@pytest.mark.parametrize("source", probes.SOURCES, ids=lambda s: s.repo)
def test_each_sibling_directory_name_is_usable(source: object) -> None:
    for name in source.checkout_names:  # type: ignore[attr-defined]
        assert isinstance(name, str) and name and "/" not in name


def test_the_real_registered_strings_still_hold() -> None:
    """The only assertion here about the actual rows. Skips a source without a checkout."""
    seen = 0
    for source in probes.SOURCES:
        body, _ = probes.read_contract(False, source)
        if body is None:
            continue
        parsed, malformed = probes.parse_contract(body)
        assert not malformed, (source.repo, malformed)
        assert parsed, f"{source.repo} registers nothing against this repository"
        failures, _ = probes.audit(parsed)
        assert not failures, f"{source.repo}: registered strings have gone missing: " + "; ".join(failures)
        seen += 1
    if not seen:
        pytest.skip("no sibling checkout beside this repository")
