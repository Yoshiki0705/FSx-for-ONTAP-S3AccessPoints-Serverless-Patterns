"""Tests for the cfn-guard gate and the rule files it runs.

## Why the rule files themselves are tested

The gate was broken at three levels simultaneously for its whole existence: an
unexpanded `**` glob meant zero templates were passed, all 7 rule files failed to
parse under cfn-guard 3.x, and `|| true` made the job green regardless. None of the
three produced a symptom — the workflow installed the tool, printed a step and
succeeded.

So the assertions here are deliberately about the things that were silently false:
that every rule file parses, that the report parser actually finds findings in a
real report, and that a new finding fails. A parser that matches nothing would
report a clean tree, which is the same shape as the original bug.

## The type-guard tests

Porting the rules produced 296 non-compliant resources, 294 of them false positives
from comparing a CloudFormation intrinsic (a map) with a scalar. The fix was an
`is_string` / `is_int` / `is_bool` guard on every scalar comparison. Two tests below
pin both directions of that: an intrinsic must not be reported, and a literal
violation must still be caught. Getting only the first would give a rule that never
fires.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
RULES = ROOT / "security" / "cfn-guard-rules"
HAVE_CFN_GUARD = shutil.which("cfn-guard") is not None


def _load() -> ModuleType:
    """Import the gate module by path.

    Returns:
        The imported ``check_cfn_guard`` module.
    """
    spec = importlib.util.spec_from_file_location("check_cfn_guard", ROOT / "scripts" / "check_cfn_guard.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_cfn_guard"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


# --------------------------------------------------------------------------
# The rule files must parse. This is the fault that made everything else moot.
# --------------------------------------------------------------------------


def test_rule_files_exist() -> None:
    files = sorted(RULES.glob("*.guard"))
    assert files, "no .guard files found; the gate would validate nothing"
    assert len(files) >= 5, f"only {len(files)} rule files"


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
@pytest.mark.parametrize("rule_file", sorted(p.name for p in RULES.glob("*.guard")))
def test_each_rule_file_parses(rule_file: str) -> None:
    """A rule file that does not parse enforces nothing and says so only on stderr.

    All 7 were in this state, using the 2.x `rule <name> when %INPUT { ... }` form
    that 3.x rejects with "There were no clauses present".
    """
    sample = ROOT / "solutions" / "industry" / "legal-compliance" / "template-deploy.yaml"
    proc = subprocess.run(
        ["cfn-guard", "validate", "--rules", str(RULES / rule_file), "--data", str(sample), "--show-summary", "fail"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "Parsing error" not in combined, f"{rule_file} does not parse:\n{combined[:600]}"


def test_no_rule_file_uses_the_2x_when_input_form() -> None:
    """Static twin of the test above, so it still fails where cfn-guard is absent.

    Comment lines are excluded. Each ported file explains in its header why the 2.x
    `when %INPUT` form had to go, and a naive substring search flagged all six for
    quoting the very thing they removed — a check reporting correct code, which is
    what gets a check deleted.
    """
    offenders: list[str] = []
    for path in sorted(RULES.glob("*.guard")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "when %INPUT" in line:
                offenders.append(path.name)
                break
    assert not offenders, (
        "these rule files use the cfn-guard 2.x `when %INPUT` form, which 3.x cannot parse: " + ", ".join(offenders)
    )


def test_no_rule_file_uses_the_invalid_fail_keyword() -> None:
    """`FAIL` as a clause is not cfn-guard syntax; s3ap-iam-dual-format.guard had it."""
    offenders = []
    for path in sorted(RULES.glob("*.guard")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped == "FAIL" or stripped.startswith("FAIL "):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, "bare FAIL is not valid cfn-guard: " + ", ".join(offenders)


def test_rule_names_are_unique_across_files() -> None:
    """Two files declaring the same rule name makes a verdict untraceable.

    `iam-least-privilege.guard` and `iam-least-privilege-v2.guard` both declared
    `iam_no_admin_access` and `iam_inline_no_admin`, and nothing said which applied.
    """
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path in sorted(RULES.glob("*.guard")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("rule "):
                name = line.split()[1]
                if name in seen:
                    duplicates.append(f"{name} in {seen[name]} and {path.name}")
                seen[name] = path.name
    assert not duplicates, "duplicate rule names: " + "; ".join(duplicates)


# --------------------------------------------------------------------------
# Type guards: both directions
# --------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_intrinsics_are_not_reported_as_violations(tmp_path: Path) -> None:
    """`!Ref` / `!Sub` reach cfn-guard as maps; comparing them to scalars errored.

    This template is compliant in every way that can be checked, but expresses its
    values through intrinsics. Before the type guards it produced findings on
    Lambda memory, Lambda timeout, the trust policy principal and the scoped secret
    ARN — all four false.
    """
    template = tmp_path / "intrinsics.yaml"
    template.write_text(
        """
Parameters:
  Mem:
    Type: Number
    Default: 512
  Secret:
    Type: String
    Default: my-secret
Resources:
  Fn:
    Type: AWS::Lambda::Function
    Properties:
      MemorySize: !Ref Mem
      Timeout: !Ref Mem
  Role:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyDocument:
            Statement:
              - Effect: Allow
                Action: ["secretsmanager:GetSecretValue"]
                Resource:
                  - !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:${Secret}*"
""",
        encoding="utf-8",
    )
    output = gate.run([template])
    assert "Parsing error" not in output, output[:400]
    assert not gate.findings(output), f"intrinsics reported as violations:\n{output[:1200]}"


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_literal_violations_are_still_caught(tmp_path: Path) -> None:
    """The other direction: the guards must not have disarmed the rules."""
    template = tmp_path / "bad.yaml"
    template.write_text(
        """
Resources:
  Role:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Statement:
          - Effect: Allow
            Principal: "*"
            Action: sts:AssumeRole
      Policies:
        - PolicyDocument:
            Statement:
              - Effect: Allow
                Action: ["secretsmanager:GetSecretValue"]
                Resource: ["*"]
  Fn:
    Type: AWS::Lambda::Function
    Properties:
      MemorySize: 99999
      Timeout: 5000
""",
        encoding="utf-8",
    )
    output = gate.run([template])
    rules = {rule for _, _, rule in gate.findings(output)}
    for expected in (
        "iam_trust_policy_no_wildcard_principal",
        "secrets_manager_access_scoped",
        "lambda_memory_limit",
        "lambda_timeout_limit",
    ):
        assert expected in rules, f"{expected} did not fire on a literal violation; rules that fired: {rules}"


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_absent_resource_types_skip_rather_than_fail(tmp_path: Path) -> None:
    """Without `when %var !empty`, every rule fails on every unrelated template."""
    template = tmp_path / "minimal.yaml"
    template.write_text(
        "Resources:\n  Q:\n    Type: AWS::SQS::Queue\n    Properties:\n      KmsMasterKeyId: alias/aws/sqs\n",
        encoding="utf-8",
    )
    output = gate.run([template])
    assert not gate.findings(output), f"a template with one compliant queue produced findings:\n{output[:800]}"


# --------------------------------------------------------------------------
# The report parser must not be vacuous
# --------------------------------------------------------------------------


def test_parser_extracts_findings_from_a_real_report() -> None:
    """A parser that matches nothing reports a clean tree, which is the old bug."""
    report = """
Evaluating data /repo/solutions/industry/x/template-deploy.yaml against rules sagemaker-security.guard
Number of non-compliant resources 1
Resource = RealtimeSageMakerModel {
  Type      = AWS::SageMaker::Model
  Rule = sagemaker_model_vpc {
    ALL {
      Check =  Properties.VpcConfig EXISTS   {
      }
    }
  }
}
"""
    found = gate.findings(report)
    assert found, "the parser found nothing in a report that clearly contains a finding"
    assert any(resource == "RealtimeSageMakerModel" and rule == "sagemaker_model_vpc" for _, resource, rule in found)


def test_parser_returns_nothing_for_a_clean_report() -> None:
    assert gate.findings("template.yaml Status = PASS\nPASS rules\n") == set()


# --------------------------------------------------------------------------
# The baseline
# --------------------------------------------------------------------------


def test_every_baseline_entry_has_a_reason() -> None:
    """A suppressed finding without a reason is indistinguishable from an oversight."""
    for key, reason in gate.KNOWN_FINDINGS.items():
        assert len(reason) > 60, f"baseline entry {key} has no substantive reason"


def test_baseline_templates_exist() -> None:
    """A stale entry silently excuses a finding that may have moved elsewhere."""
    for template, _, _ in gate.KNOWN_FINDINGS:
        assert (ROOT / template).is_file(), f"baseline names {template}, which does not exist"


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_the_repository_is_at_its_baseline() -> None:
    """Fails on a new finding AND on a fixed-but-still-listed one."""
    assert gate.main([]) == 0, "cfn-guard findings differ from the recorded baseline"


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_a_new_finding_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty the baseline: the two known findings must then fail the gate."""
    monkeypatch.setattr(gate, "KNOWN_FINDINGS", {})
    assert gate.main([]) == 1


@pytest.mark.skipif(not HAVE_CFN_GUARD, reason="cfn-guard is not installed")
def test_a_stale_baseline_entry_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A finding listed but no longer reported must fail, so progress gets locked in."""
    monkeypatch.setattr(
        gate,
        "KNOWN_FINDINGS",
        {**gate.KNOWN_FINDINGS, ("solutions/industry/legal-compliance/template-deploy.yaml", "Nope", "nope"): "x" * 70},
    )
    assert gate.main([]) == 1


def test_templates_are_found_without_a_shell_glob() -> None:
    """The original fault: `solutions/**/template-deploy.yaml` was passed literally."""
    found = gate.templates()
    assert len(found) >= 25, f"only {len(found)} templates discovered"
    assert all(p.name == "template-deploy.yaml" for p in found)


def test_missing_cfn_guard_fails_rather_than_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scan that did not run must not look like a scan that found nothing."""
    monkeypatch.setattr(gate.shutil, "which", lambda _name: None)
    assert gate.main([]) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
