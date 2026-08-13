#!/usr/bin/env python3
"""Gate: the environment variables a pattern's template sets must be the ones its
handlers read.

Why this exists, and why the portal's rule does not cover it. The portal has a rule
for the opposite direction — a handler reading a name no template sets — and it
deliberately ignores reads that carry a real default, because those are tunables.
That exemption is what hid this defect:

  nonprofit-grant-management declared GrantPrefix / OutcomePrefix, passed them as
  GRANT_PREFIX / OUTCOME_PREFIX, and its discovery handler read
  GRANT_APPLICATION_PREFIX / ACTIVITY_REPORT_PREFIX with defaults of their own.
  Both sides looked healthy in isolation. The parameter did nothing, the operator's
  value was discarded without a word, and the run discovered zero objects.

  sustainability-esg-reporting was the same shape with the parameter entirely
  unwired: EsgReportPrefix went out as PREFIX_FILTER, which nothing reads, while the
  handler wanted three category prefixes.

So the check is on the provider side: a variable the template sets that no handler in
that pattern reads is either a dead setting or a renamed one, and a renamed one means
the operator's input is silently discarded.

Usage: python3 scripts/check_pattern_env_contract.py [--verbose]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERBOSE = "--verbose" in sys.argv

# Lambda supplies these; no template names them.
RUNTIME_SUPPLIED = {
    "AWS_REGION",
    "AWS_LAMBDA_FUNCTION_NAME",
    "AWS_EXECUTION_ENV",
    "AWS_DEFAULT_REGION",
    "LAMBDA_TASK_ROOT",
    "PYTHONPATH",
}

# Set for the platform rather than for our code to read.
PLATFORM_SET = {
    "AWS_LAMBDA_EXEC_WRAPPER",
    "AWS_XRAY_CONTEXT_MISSING",
    "AWS_XRAY_DAEMON_ADDRESS",
    "POWERTOOLS_SERVICE_NAME",
    "POWERTOOLS_METRICS_NAMESPACE",
    "LOG_LEVEL",
    "USE_CASE",
    "VERIFY_SSL",
    "ENVIRONMENT",
}

# Variables set but read by nothing, across every pattern. Three of these were the
# defect this rule was written for and are fixed; what remains is older debt of the
# same kind — mostly the vestigial ONTAP plumbing in patterns that never call ONTAP.
# The number is a ceiling so it can only fall. A new template that passes a name its
# handler does not read is invisible until someone sets the parameter, gets the
# handler's default instead, and has no way to tell.
BUDGET = 26

ENV_BLOCK = re.compile(r"^(\s+)Variables:\s*$")
ENV_NAME = re.compile(r"^\s+([A-Z][A-Z_0-9]*):\s")
READ = re.compile(r'os\.environ(?:\.get)?\(?\[?\s*"([A-Z][A-Z_0-9]*)"')


def env_names_read_by_shared() -> set[str]:
    """Variable names any module under shared/ reads.

    Derived rather than listed. A pattern legitimately sets variables that only a
    shared module consumes — OUTPUT_S3AP_PREFIX is read by shared/output_writer.py,
    not by any handler — and a hand-kept list of those would drift out of date the
    first time shared/ gained a setting.

    Returns:
        set[str]: environment variable names read anywhere under shared/.
    """
    names: set[str] = set()
    for source in (ROOT / "shared").rglob("*.py"):
        if "__pycache__" in source.parts or "tests" in source.parts:
            continue
        names.update(READ.findall(source.read_text(encoding="utf-8")))
    return names


def env_names_set_by(template: Path) -> dict[str, int]:
    """Variable names the template puts in an Environment.Variables block.

    Args:
        template: path to a pattern's template.yaml.

    Returns:
        dict[str, int]: variable name mapped to the line it is first set on.
    """
    names: dict[str, int] = {}
    lines = template.read_text(encoding="utf-8").splitlines()
    inside_at: int | None = None
    for number, line in enumerate(lines, start=1):
        m = ENV_BLOCK.match(line)
        if m:
            inside_at = len(m.group(1))
            continue
        if inside_at is None:
            continue
        if line.strip() and (len(line) - len(line.lstrip())) <= inside_at:
            inside_at = None  # left the block
            m2 = ENV_BLOCK.match(line)
            if m2:
                inside_at = len(m2.group(1))
            continue
        n = ENV_NAME.match(line)
        if n:
            names.setdefault(n.group(1), number)
    return names


def env_names_read_by(pattern: Path) -> set[str]:
    """Variable names the pattern's own handlers read.

    Args:
        pattern: path to a pattern directory containing functions/.

    Returns:
        set[str]: environment variable names read by that pattern's handlers.
    """
    names: set[str] = set()
    # Patterns are not all laid out the same way: the industry ones keep handlers in
    # functions/, the flexcache ones in src/. Missing a layout makes every variable
    # that pattern sets look unread, which is a clean tree reported as 20 findings.
    for holder in ("functions", "src"):
        directory = pattern / holder
        if not directory.is_dir():
            continue
        for source in directory.glob("*/*.py"):
            if "__pycache__" in source.parts:
                continue
            text = source.read_text(encoding="utf-8")
            names.update(READ.findall(text))
            # Some handlers read through a module-level constant
            # (`_IP = "ONTAP_MANAGEMENT_IP"` then `os.environ.get(_IP)`), so a
            # pattern anchored on os.environ does not see the name. Any quoted
            # occurrence counts: this rule is about a name drifting between the
            # two sides, and a name present in the source has not drifted.
            names.update(re.findall(r'"([A-Z][A-Z_0-9]{2,})"', text))
    return names


def main() -> int:
    """Report every environment variable a pattern sets that nothing reads.

    Returns:
        int: 0 when every variable set is consumed, 1 otherwise.
    """
    findings: list[str] = []
    checked = 0
    allowed = RUNTIME_SUPPLIED | PLATFORM_SET | env_names_read_by_shared()

    for group in ("industry", "sap", "flexcache", "genai", "ha", "event-driven", "edge"):
        base = ROOT / "solutions" / group
        if not base.is_dir():
            continue
        for pattern in sorted(base.iterdir()):
            template = pattern / "template.yaml"
            if not template.is_file():
                continue
            checked += 1
            provided = env_names_set_by(template)
            consumed = env_names_read_by(pattern)
            for name, line in sorted(provided.items()):
                if name in consumed or name in allowed:
                    continue
                findings.append(
                    f'{group}/{pattern.name}/template.yaml:{line}: sets "{name}" but no '
                    f"handler in this pattern reads it. Either the name drifted from what the "
                    f"handler reads — in which case the parameter behind it is silently "
                    f"discarded — or the setting is dead and should go."
                )
            if VERBOSE:
                print(f"  {pattern.name:34} set={len(provided):3} read={len(consumed):3}")

    if len(findings) > BUDGET:
        print("PATTERN ENV CONTRACT: FAIL", file=sys.stderr)
        print(
            f"  {len(findings)} variable(s) set and read by nothing, over the budget of {BUDGET}.",
            file=sys.stderr,
        )
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1

    if len(findings) < BUDGET:
        print(
            f"PATTERN ENV CONTRACT: PASS ({checked} patterns, {len(findings)} unread "
            f"variable(s)). The budget is now loose: lower BUDGET in "
            f"scripts/check_pattern_env_contract.py to {len(findings)} so it keeps ratcheting."
        )
        return 0

    print(f"PATTERN ENV CONTRACT: PASS ({checked} patterns, {len(findings)} unread variable(s) at the budget)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
