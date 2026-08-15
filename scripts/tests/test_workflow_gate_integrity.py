"""A workflow step must not discard the verdict of the tool it runs.

## What was found

24 occurrences of `|| true` sat in `.github/workflows/`. Adjudicated one by one on
2026-08-15, 21 were the ordinary no-match idiom — `HITS=$(grep ... || true)`
followed by `if [ -n "$HITS" ]` and an explicit `exit 1`. grep, `git ls-files` and
`find` all exit non-zero when they match nothing, which is the *clean* case, and
under `set -e` that would abort the step precisely when there is nothing wrong.
Those are safe: the verdict comes from the test, not the pipeline status.

Three were not.

**cfn-guard, twice.** `cfn-guard validate --data solutions/**/template-deploy.yaml
... || true`, duplicated in `ci.yml` and `validators.yml`. `**` is not expanded by
the default Actions shell — that needs `shopt -s globstar` — so cfn-guard received
the literal string, answered "The path `solutions/**/template-deploy.yaml` does not
exist", exited 255, and `|| true` turned it green. Neither job had ever validated a
template. Underneath that, all 7 files in `security/cfn-guard-rules/` fail to
*parse* under cfn-guard 3.x (they use the 2.x `rule ... when %INPUT` form), so even
with the glob fixed the rules enforce nothing. Three faults stacked, one `|| true`
hiding all three.

**zizmor.** `zizmor . || true` meant the workflow named "GitHub Actions Security
Lint" could not fail. A finding was uploaded to code scanning and the job went
green.

## What this test enforces

A `|| true` is allowed only where the output is captured for a later test, or
where it is listed below with a reason. A bare tool invocation ending in `|| true`
is rejected, because that is the shape that cannot fail.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Bare invocations whose status is deliberately discarded, with the reason.
# Keyed by a distinctive fragment of the line.
ALLOWED_BARE: dict[str, str] = {
    "zizmor --format sarif": (
        "zizmor exits non-zero on findings, and the SARIF file must exist for the "
        "upload-sarif step regardless of the verdict. The blocking decision is made "
        "by the separate `zizmor .` step, which has no `|| true`."
    ),
}

# Commands that must never be followed by `|| true`: their exit code IS the gate.
GATE_TOOLS = (
    "cfn-guard",
    "bandit",
    "pip-audit",
    "gitleaks",
    "cfn-lint",
    "ruff",
    "pytest",
    "zizmor",
    "npm run build",
    "tsc",
)


def run_blocks() -> list[tuple[str, str, str]]:
    """Every `run:` script in every workflow.

    Returns:
        Tuples of (workflow file name, job name, script text).
    """
    blocks: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (document.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                script = step.get("run")
                if isinstance(script, str):
                    blocks.append((path.name, job_name, script))
    return blocks


def _swallowing_lines() -> list[tuple[str, str, str]]:
    """Lines that discard an exit status without capturing output for a later test.

    Returns:
        Tuples of (workflow, job, offending line).
    """
    offenders: list[tuple[str, str, str]] = []
    for workflow, job, script in run_blocks():
        for raw in script.splitlines():
            line = raw.strip()
            if not re.search(r"\|\|\s*(true|:)\s*$", line):
                continue
            if line.startswith("#"):
                continue
            # Captured into a variable, or part of a command substitution whose
            # value is tested afterwards. This is the grep-no-match idiom.
            if "$(" in line or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
                continue
            if any(fragment in line for fragment in ALLOWED_BARE):
                continue
            offenders.append((workflow, job, line))
    return offenders


# --------------------------------------------------------------------------


def test_no_workflow_step_discards_a_tool_verdict() -> None:
    """The measurement. A bare `tool ... || true` is a step that cannot fail."""
    offenders = _swallowing_lines()
    assert not offenders, "workflow lines that discard an exit status:\n  " + "\n  ".join(
        f"{w}[{j}]: {line}" for w, j, line in offenders
    )


@pytest.mark.parametrize("tool", GATE_TOOLS)
def test_gate_tools_are_never_followed_by_true(tool: str) -> None:
    """Named explicitly so a regression says which gate was disarmed."""
    offenders: list[str] = []
    for workflow, job, script in run_blocks():
        for raw in script.splitlines():
            line = raw.strip()
            if line.startswith("#") or tool not in line:
                continue
            if re.search(r"\|\|\s*(true|:)\s*$", line) and not any(f in line for f in ALLOWED_BARE):
                offenders.append(f"{workflow}[{job}]: {line}")
    assert not offenders, f"{tool} runs with its exit code discarded:\n  " + "\n  ".join(offenders)


def test_cfn_guard_does_not_use_an_unexpanded_globstar() -> None:
    """`solutions/**/x.yaml` is passed literally; cfn-guard then exits 255.

    The regression this pins is subtle because the workflow still *runs* — it
    installs the tool, prints a step, and succeeds having scanned nothing.
    """
    offenders: list[str] = []
    for workflow, job, script in run_blocks():
        if "cfn-guard" not in script:
            continue
        for raw in script.splitlines():
            if "--data" in raw and "**" in raw:
                offenders.append(f"{workflow}[{job}]: {raw.strip()}")
    assert not offenders, (
        "cfn-guard is given a `**` glob the Actions shell does not expand "
        "(globstar is off), so it receives the literal string and exits 255:\n  " + "\n  ".join(offenders)
    )


def test_cfn_guard_rule_files_are_parse_checked_somewhere() -> None:
    """A rule that does not parse enforces nothing, so that must be gated.

    The check may live inline in a workflow or inside a script a workflow runs —
    what matters is that a pull request cannot merge with an unparseable rule file.
    It started as an inline `grep -q 'Parsing error'` step and now lives in
    `scripts/check_cfn_guard.py`, which validators.yml invokes; asserting the inline
    form would have failed on that move while the property still held.
    """
    if not (ROOT / "security" / "cfn-guard-rules").is_dir():
        pytest.skip("no cfn-guard rules in this checkout")

    combined = "\n".join(script for _, _, script in run_blocks())
    if re.search(r"grep\s+-q\s+'Parsing error'", combined):
        return

    # Look for the containment TEST, not the phrase. Every ported rule file and the
    # wrapper both discuss "Parsing error" in prose, so a bare substring search is
    # satisfied by a comment — it passed when the real check had been disabled.
    code = re.compile(r"""["']Parsing error["']\s+in\s+\w+""")
    referenced = re.findall(r"(scripts/[A-Za-z0-9_./-]+\.py)", combined)
    for name in dict.fromkeys(referenced):
        path = ROOT / name
        if path.is_file() and code.search(path.read_text(encoding="utf-8")):
            return

    pytest.fail(
        "nothing reachable from CI checks that the cfn-guard rule files parse. All 7 "
        "failed to parse under cfn-guard 3.x on 2026-08-15, which makes the scan "
        "vacuous whatever its exit code."
    )


def test_allowed_bare_entries_are_real_and_justified() -> None:
    """A stale exemption quietly re-permits the shape this test exists to reject."""
    combined = "\n".join(script for _, _, script in run_blocks())
    for fragment, reason in ALLOWED_BARE.items():
        assert fragment in combined, f"ALLOWED_BARE names {fragment!r}, which no workflow contains"
        assert len(reason) > 40, f"ALLOWED_BARE[{fragment!r}] has no substantive reason"


def test_the_scan_is_not_vacuous() -> None:
    """A YAML parse that yields nothing would make every check above pass."""
    blocks = run_blocks()
    assert len(blocks) > 40, f"only {len(blocks)} run: blocks parsed; the workflow reader is broken"
    assert any("|| true" in script for _, _, script in blocks), (
        "no `|| true` found anywhere; the reader is not seeing script bodies"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
