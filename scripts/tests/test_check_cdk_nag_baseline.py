"""Tests for the cdk-nag ratchet.

A baseline is only worth having if it fails in both directions. Too permissive and it
becomes an allowlist that grows; too strict about the wrong thing and it fails on a
correct change, which is how a gate ends up bypassed.

Run against crafted reports rather than a synth: `npm run nag` takes a minute or two and
needs node_modules, and neither is necessary to test the comparison. Whether the report
itself is produced is asserted in the last class, against the real script.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_cdk_nag_baseline.py"


def load_checker(tmp_path: Path, findings: list[tuple[str, str]]) -> Any:
    """Import the checker with its report and baseline pointed at a temporary tree.

    Args:
        tmp_path: Directory to hold the crafted report and baseline.
        findings: (rule, path-without-stack-prefix) pairs the report should contain.

    Returns:
        The imported module, with `REPORT` and `BASELINE` redirected.
    """
    spec = importlib.util.spec_from_file_location("check_cdk_nag_baseline_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_cdk_nag_baseline_under_test"] = module
    spec.loader.exec_module(module)

    report = {
        "pluginReports": [
            {
                "pluginName": "AwsSolutions",
                "violations": [
                    {
                        "ruleName": rule,
                        # The stack segment is what the checker strips. Included so the
                        # test exercises that, rather than the already-stripped form.
                        "violatingConstructs": [{"constructPath": f"amplify-stack-abc123/{path}"}],
                    }
                    for rule, path in findings
                ],
            }
        ]
    }
    module.REPORT = tmp_path / "validation-report.json"
    module.REPORT.write_text(json.dumps(report))
    module.BASELINE = tmp_path / "cdk-nag-baseline.txt"
    module.ROOT = tmp_path
    return module


ONE = ("AwsSolutions-IAM5[Resource::*]", "data/ListFilesLambdaRole/Resource")
TWO = ("AwsSolutions-DDB3", "data/ChatHistoryTable/Resource")


class TestIdentity:
    def test_strips_the_stack_name_from_the_path(self, tmp_path: Path) -> None:
        # The stack name carries a hash of the backend identifier, so it differs between a
        # sandbox and CI. Left in, every finding would read as new in the other place.
        module = load_checker(tmp_path, [ONE])
        assert module.current_findings() == {ONE}

    def test_keeps_the_granular_rule_id(self, tmp_path: Path) -> None:
        # `AwsSolutions-IAM5` alone would let one wildcard be swapped for another without
        # the baseline noticing, which is the distinction the granular id carries.
        module = load_checker(tmp_path, [("AwsSolutions-IAM5[Action::s3:*]", "data/X/Resource")])
        rule, _ = next(iter(module.current_findings()))
        assert rule.endswith("[Action::s3:*]")


class TestRatchet:
    def test_passes_when_the_report_matches_the_baseline(self, tmp_path: Path) -> None:
        module = load_checker(tmp_path, [ONE, TWO])
        module.write_baseline({ONE, TWO})
        assert module.main([]) == 0

    def test_fails_on_a_finding_that_is_not_recorded(self, tmp_path: Path) -> None:
        module = load_checker(tmp_path, [ONE, TWO])
        module.write_baseline({ONE})
        assert module.main([]) == 1

    def test_fails_on_a_recorded_finding_that_is_gone(self, tmp_path: Path) -> None:
        # Progress the file does not know about. Left passing, the baseline would keep
        # claiming a finding exists long after it was fixed, and the next real finding
        # could hide in the gap.
        module = load_checker(tmp_path, [ONE])
        module.write_baseline({ONE, TWO})
        assert module.main([]) == 1

    def test_fails_when_no_baseline_is_recorded(self, tmp_path: Path) -> None:
        # An absent file must not read as "nothing known, so nothing to report".
        module = load_checker(tmp_path, [ONE])
        assert module.main([]) == 1

    def test_write_then_check_is_stable(self, tmp_path: Path) -> None:
        module = load_checker(tmp_path, [ONE, TWO])
        module.write_baseline(module.current_findings())
        assert module.main([]) == 0
        # And again, so the round trip does not depend on ordering or formatting.
        module.write_baseline(module.current_findings())
        assert module.main([]) == 0


class TestBaselineFile:
    def test_records_a_reason_for_every_finding(self, tmp_path: Path) -> None:
        module = load_checker(tmp_path, [ONE, TWO])
        module.write_baseline({ONE, TWO})
        written = module.BASELINE.read_text()
        assert "Lambda role we declare" in written
        assert "feature gates" in written or "chat history" in written

    def test_comments_and_blanks_are_ignored_when_reading(self, tmp_path: Path) -> None:
        module = load_checker(tmp_path, [ONE])
        module.BASELINE.write_text(f"# a comment\n\n{ONE[0]}\t{ONE[1]}\n")
        assert module.read_baseline() == {ONE}

    def test_an_unknown_path_is_reported_as_uncategorised(self, tmp_path: Path) -> None:
        # The signal the writer relies on: a path no category matches must not silently
        # acquire somebody else's reason. The real baseline is checked for this in
        # `TestAgainstTheRepository`.
        module = load_checker(tmp_path, [ONE])
        assert module.reason_for("something/nobody/declared") == "uncategorised"


class TestAgainstTheRepository:
    """The real baseline, without synthesising."""

    @staticmethod
    def real_module() -> Any:
        spec = importlib.util.spec_from_file_location("check_cdk_nag_baseline_real", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["check_cdk_nag_baseline_real"] = module
        spec.loader.exec_module(module)
        return module

    def test_the_baseline_file_is_committed(self) -> None:
        # Absent, the gate fails closed rather than passing — but it also fails for every
        # contributor, so its presence is asserted here rather than discovered in CI.
        module = self.real_module()
        assert module.BASELINE.is_file(), module.BASELINE

    def test_every_recorded_finding_has_a_reason(self) -> None:
        module = self.real_module()
        entries = module.read_baseline()
        assert entries, "the baseline is empty"
        for _, path in entries:
            assert module.reason_for(path) != "uncategorised", path

    def test_the_recorded_rules_look_like_cdk_nag_ids(self) -> None:
        # Guards the reader: a baseline of blank or truncated ids would compare equal to
        # nothing and pass forever.
        module = self.real_module()
        for rule, path in module.read_baseline():
            assert rule.startswith("AwsSolutions-"), rule
            assert path and not path.startswith("/"), path

    def test_the_fixed_categories_are_absent(self) -> None:
        # Two categories were fixed rather than recorded. If either reappears in the
        # baseline, it was re-recorded instead of kept fixed.
        module = self.real_module()
        rules = {rule.split("[")[0] for rule, _ in module.read_baseline()}
        assert "AwsSolutions-SNS3" not in rules
        paths = {path for _, path in module.read_baseline()}
        assert "data/AgentDirectoryTable/Resource" not in paths
        assert "data/AgentTeamsTable/Resource" not in paths


@pytest.fixture(autouse=True)
def _no_synth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test would shell out to `npm run nag`."""
    import subprocess

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a test tried to run npm; the report should be crafted instead")

    monkeypatch.setattr(subprocess, "run", refuse)


class TestTheSynthUsesTheSharedConfig:
    """The script synthesises against the committed example, not a local config.

    Several finding ids embed a value from `portal-config.ts` -- an IAM5 finding names the
    ARN it objects to -- and that file is gitignored, so a developer's copy differs from the
    example CI puts in place. A baseline recorded from a local config named a DemoMode
    bucket CI has never heard of, and the gate failed on its first CI run with 13 findings
    "no longer reported".
    """

    @staticmethod
    def script() -> str:
        return (
            Path(__file__).resolve().parents[2] / "solutions" / "amplify-portal" / "scripts" / "cdk-nag.sh"
        ).read_text()

    def test_copies_the_example_over_the_local_config(self) -> None:
        assert 'cp "$EXAMPLE" "$CONFIG"' in self.script()

    def test_restores_the_local_config_on_any_exit(self) -> None:
        # Including an interrupt: losing somebody's configuration to a read-only check
        # would be a poor trade.
        script = self.script()
        assert "trap restore_config EXIT INT TERM" in script
        assert 'mv -f "$STASHED" "$CONFIG"' in script

    def test_offers_an_escape_for_a_local_synth(self) -> None:
        assert "CDK_NAG_KEEP_CONFIG" in self.script()

    def test_the_baseline_holds_no_value_from_a_local_config(self) -> None:
        # The concrete symptom, asserted against the committed file: the DemoMode bucket
        # names in the example are commented out, so no bucket ARN should appear here.
        module = TestAgainstTheRepository.real_module()
        for rule, _ in module.read_baseline():
            assert "fsxn-audit-logs" not in rule, rule
