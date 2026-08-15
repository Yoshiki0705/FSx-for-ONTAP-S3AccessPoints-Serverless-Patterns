"""Tests for scripts/check_account_id_placeholders.py.

The point of the check is that it cannot go quiet. So most of these tests assert
that it *fires* on a crafted input, and two of them mutate the module's own
configuration to prove that the repository-wide scan is reaching real content
rather than passing because it read nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_account_id_placeholders.py"


def _load_module() -> ModuleType:
    """Import the checker by path, since scripts/ is not a package.

    Returns:
        The imported ``check_account_id_placeholders`` module.
    """
    spec = importlib.util.spec_from_file_location("check_account_id_placeholders", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

# A 12-digit value that is neither a documented placeholder nor a repeated digit.
REAL_LOOKING = "504821736095"


class TestPlaceholderRecognition:
    """is_placeholder must accept the three placeholder shapes and nothing else."""

    @pytest.mark.parametrize("digit", list("0123456789"))
    def test_repeated_single_digit_accepted(self, digit: str) -> None:
        assert mod.is_placeholder(digit * 12)

    @pytest.mark.parametrize(
        "value",
        [
            "111122223333",  # AWS documentation convention
            "444455556666",  # AWS documentation convention
            "000011112222",
        ],
    )
    def test_repeated_digit_groups_accepted(self, value: str) -> None:
        assert mod.is_placeholder(value)

    @pytest.mark.parametrize(
        "value",
        [
            "123456789012",  # the repository's standard placeholder
            "234567890123",  # the same run shifted, used for a second account
            "987654321098",  # descending, used for "the other account"
            "890123456789",
        ],
    )
    def test_sequential_runs_accepted(self, value: str) -> None:
        assert mod.is_placeholder(value)

    def test_real_looking_id_rejected(self) -> None:
        assert not mod.is_placeholder(REAL_LOOKING)

    @pytest.mark.parametrize(
        "value",
        [
            "111122223334",  # last group broken, so not a group pattern
            "123456789013",  # last digit breaks the run
            "112233445566",  # pairs, not groups of four
            "121212121212",
        ],
    )
    def test_near_miss_shapes_rejected(self, value: str) -> None:
        # A near miss must NOT be waved through: these are the values a real ID
        # would most plausibly be mistaken for if the shape rules were loose.
        assert not mod.is_placeholder(value)

    def test_repeated_digit_rule_requires_exactly_twelve(self) -> None:
        # Guards against the regex being anchored loosely enough to accept an
        # 11- or 13-digit run and thereby wave through a near-miss.
        assert not mod.is_placeholder("1" * 11)
        assert not mod.is_placeholder("1" * 13)

    def test_sequential_rule_wraps_only_at_the_decimal_boundary(self) -> None:
        assert mod._is_sequential_run("789012345678")
        assert not mod._is_sequential_run("789012345679")


class TestPositionsThatFire:
    """Each supported account-ID position must be detected."""

    @pytest.mark.parametrize(
        "line",
        [
            f"    AccountId={REAL_LOOKING} \\",
            f'    account_id: "{REAL_LOOKING}"',
            f"  account-id = '{REAL_LOOKING}'",
            f"    ACCOUNTID={REAL_LOOKING}",
            f"│   Workload Account ({REAL_LOOKING})   │",
            f'  "Resource": "arn:aws:s3:::bucket", "Principal": "arn:aws:iam::{REAL_LOOKING}:root"',
            f"  arn:aws-us-gov:sns:us-gov-west-1:{REAL_LOOKING}:topic",
        ],
    )
    def test_account_id_position_is_detected(self, line: str) -> None:
        findings = mod.scan_text(line)
        assert findings, f"no finding for: {line}"
        assert findings[0][1] == REAL_LOOKING

    def test_placeholder_in_the_same_positions_is_not_detected(self) -> None:
        for line in (
            "AccountId=123456789012 \\",
            'account_id: "987654321098"',
            "Workload Account (111111111111)",
            # Uses the standard placeholder rather than a repeated-digit one because
            # commit_gate.py's ARN rule exempts only 123456789012 by literal value.
            # is_placeholder is covered exhaustively above, so nothing is lost here.
            "arn:aws:iam::123456789012:role/Example",
        ):
            assert mod.scan_text(line) == [], line

    def test_line_number_is_reported(self) -> None:
        text = "first\nsecond\nAccountId=" + REAL_LOOKING + "\n"
        assert mod.scan_text(text) == [(3, REAL_LOOKING)]

    def test_multiple_findings_on_one_line(self) -> None:
        other = "615093472281"
        text = f"a AccountId={REAL_LOOKING} b account_id: {other}"
        values = {value for _, value in mod.scan_text(text)}
        assert values == {REAL_LOOKING, other}


class TestNarrownessAgainstNoise:
    """The shapes measured in this repository must not be reported.

    These are the classes that made a bare `\\b\\d{12}\\b` rule unusable: byte
    counts in fixtures, the trailing segment of a UUID, a subnet-ID fragment, and
    prose that merely discusses account IDs.
    """

    @pytest.mark.parametrize(
        "line",
        [
            f'    "compression_savings_bytes": {REAL_LOOKING},',
            f'    "available_bytes": {REAL_LOOKING}',
            f'    "uuid": "e5f6a7b8-c9d0-1234-efab-{REAL_LOOKING}",',
            f'    "event_id": "550e8400-e29b-41d4-a716-{REAL_LOOKING}",',
            f'    "ParameterValue": "subnet-0aaa{REAL_LOOKING}a"',
            f"      # placeholders such as {REAL_LOOKING}, and AWS's own public ECR account",
            f"      # {REAL_LOOKING}. Making them blocking would fail every pull request",
            f"    https://support.box.com/hc/en-us/articles/{REAL_LOOKING}",
            f"    the account id convention is described above, see {REAL_LOOKING}",
        ],
    )
    def test_non_account_position_is_ignored(self, line: str) -> None:
        assert mod.scan_text(line) == [], line

    def test_prose_near_the_word_account_does_not_fire(self) -> None:
        # The ci.yml comments sit one word away from "account". A proximity-based
        # rule would report them; an adjacency-based rule must not.
        line = f"# this account was migrated, ticket {REAL_LOOKING} refers"
        assert mod.scan_text(line) == []


class TestExemption:
    """The inline escape hatch must work and must be explicit."""

    def test_marker_suppresses_the_finding(self) -> None:
        line = f"AccountId={REAL_LOOKING}  # allow:account-id: AWS-owned public account"
        assert mod.scan_text(line) == []

    def test_marker_only_affects_its_own_line(self) -> None:
        text = f"AccountId={REAL_LOOKING}  # allow:account-id\nAccountId={REAL_LOOKING}\n"
        assert mod.scan_text(text) == [(2, REAL_LOOKING)]

    def test_marker_string_matches_the_documented_one(self) -> None:
        assert mod.EXEMPTION_MARKER == "allow:account-id"


class TestMasking:
    """CI logs are public, so a finding must never print the value."""

    def test_mask_hides_all_but_the_first_two_digits(self) -> None:
        masked = mod.mask(REAL_LOOKING)
        assert masked == "50##########"
        assert REAL_LOOKING not in masked

    def test_mask_preserves_length(self) -> None:
        assert len(mod.mask(REAL_LOOKING)) == len(REAL_LOOKING)

    def test_reported_output_does_not_contain_the_value(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod, "scan_repository", lambda _root: [(Path("x.yaml"), 3, REAL_LOOKING)])
        assert mod.main(["--root", str(tmp_path)]) == 1
        out = capsys.readouterr().out
        assert REAL_LOOKING not in out
        assert "x.yaml:3" in out


class TestRepositoryScanIsNotVacuous:
    """Prove the real scan reads real content, then that the repo is clean."""

    def test_repository_is_clean(self) -> None:
        assert mod.scan_repository(REPO_ROOT) == []

    def test_scan_reaches_content_at_all(self) -> None:
        # If tracked_files or the read loop were broken, scan_repository would
        # return [] for the wrong reason and test_repository_is_clean would pass
        # vacuously. Removing every placeholder must therefore produce findings,
        # because the repository provably does contain placeholder account IDs in
        # account-ID positions.
        saved = (
            mod.DOCUMENTED_PLACEHOLDERS,
            mod.REPEATED_SINGLE_DIGIT,
            mod.REPEATED_DIGIT_GROUPS,
            mod._is_sequential_run,
        )
        never_matches = mod.re.compile(r"^(?!)$")
        try:
            mod.DOCUMENTED_PLACEHOLDERS = frozenset()
            mod.REPEATED_SINGLE_DIGIT = never_matches
            mod.REPEATED_DIGIT_GROUPS = never_matches
            mod._is_sequential_run = lambda _value: False
            findings = mod.scan_repository(REPO_ROOT)
        finally:
            (
                mod.DOCUMENTED_PLACEHOLDERS,
                mod.REPEATED_SINGLE_DIGIT,
                mod.REPEATED_DIGIT_GROUPS,
                mod._is_sequential_run,
            ) = saved
        assert findings, "scan_repository found nothing even with placeholders disallowed"

    def test_tracked_files_returns_a_plausible_inventory(self) -> None:
        files = mod.tracked_files(REPO_ROOT)
        assert len(files) > 100
        assert all(f.suffix.lower() not in mod.SKIP_SUFFIXES for f in files)
        assert Path("AGENTS.md") in files


class TestExitCodes:
    """main must exit nonzero only when there is a finding."""

    def test_clean_repository_exits_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "scan_repository", lambda _root: [])
        assert mod.main(["--root", str(tmp_path)]) == 0

    def test_finding_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "scan_repository", lambda _root: [(Path("a.md"), 1, REAL_LOOKING)])
        assert mod.main(["--root", str(tmp_path)]) == 1
