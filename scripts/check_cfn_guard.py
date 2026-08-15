#!/usr/bin/env python3
"""Run cfn-guard against every deployable template and fail on any NEW finding.

## Why a wrapper instead of calling cfn-guard directly

cfn-guard has no baseline mechanism: it either passes or it does not. The workflow
therefore ended in `|| true`, which meant it could not fail at all — and that hid
three separate faults for as long as it existed:

1. `--data solutions/**/template-deploy.yaml` was never expanded. `**` needs
   `shopt -s globstar`, which the default Actions shell does not set, so cfn-guard
   received the literal string, answered "The path ... does not exist" and exited
   255. **Zero templates were ever validated**, in two duplicated jobs.
2. All 7 rule files failed to PARSE under cfn-guard 3.x. They used the 2.x
   `rule <name> when %INPUT { ... }` form, which 3.x rejects with "There were no
   clauses present". Even with the glob fixed, nothing would have been enforced.
3. `|| true` turned both of the above into a green check.

Fixing 1 and 2 produced 296 non-compliant resources across 76 template/rule pairs —
almost all false positives, because a CloudFormation intrinsic is a *map* and
comparing a map with a scalar is a ComparisonError that cfn-guard counts as
non-compliant. `Resource: !Sub "arn:aws:secretsmanager:...:secret:${Name}*"` was
reported as "must be scoped to a secret ARN, not *" while being exactly that. Adding
type guards to the rules took it to 2.

Those 2 are real, and they are recorded below rather than suppressed silently. The
gate is now blocking for anything else.

## The baseline

`KNOWN_FINDINGS` is a ratchet, not an allowlist to grow. Each entry names the
resource, the rule and why it is not fixed yet. A finding that is not listed fails
the build; a listed finding that has been fixed also fails, so the baseline cannot
quietly drift upward or hide progress.

## Usage

    python3 scripts/check_cfn_guard.py           # blocking; fails on a new finding
    python3 scripts/check_cfn_guard.py --list    # print what cfn-guard reports now
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "security" / "cfn-guard-rules"

# (template, resource, rule) -> why it is not fixed.
#
# Both entries are in solutions/industry/autonomous-driving/template-deploy.yaml,
# the only template here that declares SageMaker resources. Neither is a false
# positive; both need an infrastructure decision that cannot be validated without
# deploying, which is why they are recorded rather than patched blind.
KNOWN_FINDINGS: dict[tuple[str, str, str], str] = {
    (
        "solutions/industry/autonomous-driving/template-deploy.yaml",
        "RealtimeSageMakerModel",
        "sagemaker_model_vpc",
    ): (
        "Placing the model in the VPC requires interface endpoints for the SageMaker "
        "API and runtime, ECR (to pull the pytorch-inference image) and S3 (to fetch "
        "model.tar.gz). Adding VpcConfig without them makes the endpoint fail to "
        "start, so this is a networking change to design and deploy, not a property "
        "to add. Subnets and a security group already exist in the template "
        "(PrivateSubnetIds, LambdaSecurityGroup)."
    ),
    (
        "solutions/industry/autonomous-driving/template-deploy.yaml",
        "RealtimeEndpointConfig",
        "sagemaker_endpoint_encryption",
    ): (
        "KmsKeyId encrypts the ML storage volume on the hosting instance "
        "(ml.m5.large). The template declares no KMS key and uses alias/aws/sns for "
        "SNS only, so this needs a key resource plus a decision on customer-managed "
        "versus AWS-managed, and on who holds the key policy."
    ),
}


def templates() -> list[Path]:
    """Deployable templates to validate.

    `find` rather than a shell glob: `solutions/**/template-deploy.yaml` is not
    expanded by the default Actions shell, which is how this gate came to validate
    nothing at all.

    Returns:
        Sorted template paths.
    """
    return sorted((ROOT / "solutions").rglob("template-deploy.yaml"))


def run(paths: list[Path]) -> str:
    """Invoke cfn-guard and return its combined output.

    Args:
        paths: Templates to pass as ``--data`` arguments.

    Returns:
        Combined stdout and stderr.
    """
    command = ["cfn-guard", "validate", "--rules", str(RULES), "--show-summary", "fail"]
    for path in paths:
        command += ["--data", str(path)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    return proc.stdout + proc.stderr


TEMPLATE_LINE = re.compile(r"^(\S+) Status = (FAIL|PASS|SKIP)", re.M)
RESOURCE_LINE = re.compile(r"^Resource = (\S+) \{", re.M)
RULE_LINE = re.compile(r"^\s*Rule = (\w+) \{", re.M)


def findings(output: str) -> set[tuple[str, str, str]]:
    """Parse (template, resource, rule) triples out of cfn-guard's report.

    cfn-guard's text output is the only machine-readable-enough surface here; its
    JSON output changes shape between versions. The parse is asserted by
    scripts/tests/test_check_cfn_guard.py against a captured real report, because a
    parser that silently matches nothing would report a clean tree.

    Args:
        output: Combined cfn-guard output.

    Returns:
        Set of findings, with template paths relative to the repository root.
    """
    found: set[tuple[str, str, str]] = set()
    current_template = ""
    current_resource = ""
    for line in output.splitlines():
        evaluating = re.match(r"^Evaluating data (\S+) against rules", line)
        if evaluating:
            try:
                current_template = str(Path(evaluating.group(1)).resolve().relative_to(ROOT))
            except ValueError:
                current_template = evaluating.group(1)
            continue
        resource = RESOURCE_LINE.match(line)
        if resource:
            current_resource = resource.group(1)
            continue
        rule = RULE_LINE.match(line)
        if rule and current_template and current_resource:
            found.add((current_template, current_resource, rule.group(1)))
    return found


def main(argv: list[str]) -> int:
    """Validate and compare against the baseline.

    Args:
        argv: Command-line arguments.

    Returns:
        1 on a new finding, a fixed-but-still-listed finding, a parse failure or a
        missing tool, otherwise 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print current findings and exit 0")
    args = parser.parse_args(argv)

    if shutil.which("cfn-guard") is None:
        print(
            "cfn-guard is not installed. Install it with:\n"
            "  curl --proto '=https' --tlsv1.2 -sSf "
            "https://raw.githubusercontent.com/aws-cloudformation/cloudformation-guard/main/install-guard.sh | sh\n"
            "Failing rather than skipping: a scan that did not run must not look like a scan that found nothing.",
            file=sys.stderr,
        )
        return 1

    paths = templates()
    if not paths:
        print("CFN-GUARD: FAIL — no template-deploy.yaml found, so this check proves nothing", file=sys.stderr)
        return 1

    output = run(paths)

    # A rule file that does not parse enforces nothing, and cfn-guard reports that
    # on stderr while still exiting as though it had run. This is the fault that
    # sat here for the lifetime of the gate.
    if "Parsing error" in output:
        print("CFN-GUARD: FAIL — a rule file could not be parsed, so it enforces nothing:", file=sys.stderr)
        for line in output.splitlines():
            if "Parsing error" in line:
                print(f"  {line[:200]}", file=sys.stderr)
        return 1

    current = findings(output)

    if args.list:
        print(f"CFN-GUARD: {len(paths)} template(s), {len(current)} finding(s)")
        for template, resource, rule in sorted(current):
            known = "known" if (template, resource, rule) in KNOWN_FINDINGS else "NEW"
            print(f"  [{known}] {template} :: {resource} :: {rule}")
        return 0

    new = sorted(current - set(KNOWN_FINDINGS))
    fixed = sorted(set(KNOWN_FINDINGS) - current)

    if new:
        print(f"CFN-GUARD: {len(new)} new finding(s):", file=sys.stderr)
        for template, resource, rule in new:
            print(f"  {template}\n    resource {resource} fails {rule}", file=sys.stderr)
        print(
            "\nFix the template, or — if it is a false positive — fix the rule rather than "
            "adding the finding here. A CloudFormation intrinsic is a map, so a scalar "
            "comparison against it needs an is_string / is_int / is_bool guard; that alone "
            "accounted for 294 of the 296 findings on the first run.",
            file=sys.stderr,
        )
        return 1

    if fixed:
        print(f"CFN-GUARD: {len(fixed)} baseline finding(s) no longer reported:", file=sys.stderr)
        for template, resource, rule in fixed:
            print(f"  {template} :: {resource} :: {rule}", file=sys.stderr)
        print("\nRemove them from KNOWN_FINDINGS to lock the progress in.", file=sys.stderr)
        return 1

    print(
        f"CFN-GUARD: PASS ({len(paths)} templates, {len(list(RULES.glob('*.guard')))} rule files, "
        f"{len(current)} known finding(s) at the baseline)"
    )
    for template, resource, rule in sorted(current):
        print(f"  known: {template} :: {resource} :: {rule}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
