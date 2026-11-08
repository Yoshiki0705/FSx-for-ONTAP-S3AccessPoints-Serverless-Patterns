"""The CloudFormation lint gates must be able to fail, and the operations templates must satisfy them.

Two defects this pins:

* ``ci.yml`` Stage 1 ran ``cfn-lint ... || echo "lint_failed=true"``. The exit code was thrown away, the
  value written to ``$GITHUB_OUTPUT`` was read by nothing, and ``CI Final Status`` showed "Lint: success"
  whatever cfn-lint said. The gate that actually blocks is ``validators.yml``.
* ``make lint-cfn-ops`` exited 12 on informational findings (I3011) that CI never looked at, so the
  hand-written target was red on main and nobody noticed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def _job_block(name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n((?:    .*\n|\n)+)", CI, re.M)
    assert match, f"ci.yml has no job {name}"
    return match.group(1)


def test_stage_1_lint_does_not_swallow_the_exit_code() -> None:
    lint = _job_block("lint")
    assert "cfn-lint" in lint or "lint-cfn" in lint
    assert "|| echo" not in lint, "an `|| echo` after cfn-lint turns every finding into a green step"
    assert "lint_failed" not in lint, "a flag nothing reads is not a gate"


def test_stage_1_runs_the_same_command_as_the_blocking_validator() -> None:
    validators = (ROOT / ".github" / "workflows" / "validators.yml").read_text(encoding="utf-8")
    assert "make lint-cfn" in validators
    assert "make lint-cfn" in _job_block("lint"), "Stage 1 and the validator must not apply different rules"


def test_every_row_of_the_final_status_names_a_job_it_waits_for() -> None:
    final = _job_block("final-status")
    needs = set(re.findall(r"^      - ([a-z0-9-]+)\s*$", final.split("steps:")[0], re.M))
    rows = set(re.findall(r"needs\.([a-z0-9-]+)\.result", final))
    assert needs, "could not read the needs list"
    assert rows <= needs, f"read but not waited for (always empty): {sorted(rows - needs)}"


def test_the_ops_lint_target_uses_the_same_bar_as_ci() -> None:
    target = re.search(r"^lint-cfn-ops:\n((?:\t.*\n)+)", MAKEFILE, re.M)
    assert target, "Makefile has no lint-cfn-ops target"
    assert "--non-zero-exit-code error" in target.group(1)


def test_stateful_operations_resources_state_their_deletion_behaviour() -> None:
    """cfn-lint I3011: say what happens on delete and on replace, even when it is the default."""
    stateful = ("AWS::Logs::LogGroup", "AWS::SQS::Queue")
    missing: list[str] = []
    checked = 0
    for template in sorted((ROOT / "operations").glob("*/template.yaml")):
        text = template.read_text(encoding="utf-8")
        resources = text.split("\nResources:\n", 1)[1]
        for match in re.finditer(r"^  (\w+):\n((?:    .*\n|\n|  #.*\n)+)", resources, re.M):
            body = match.group(2)
            if not any(f"Type: {t}" in body for t in stateful):
                continue
            checked += 1
            for key in ("DeletionPolicy", "UpdateReplacePolicy"):
                if f"    {key}:" not in body:
                    missing.append(f"{template.parent.name}/{match.group(1)} lacks {key}")
    assert checked >= 19, f"expected at least 19 stateful resources, found {checked}"
    assert not missing, "\n".join(missing)
