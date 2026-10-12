"""Every CloudFormation template is linted, and the cfn-lint job really blocks.

## The failure being closed

`.cfnlintrc` lists the templates cfn-lint checks as globs. A new template that no glob
matches is not an error: `make lint-cfn` finishes green having never opened it. The
same is true one level up: a `cfn-lint` job that is not in `validators-summary.needs`,
or is in `needs` but missing from the `results` map the summary evaluates, can go red
without anything reporting it (`validators-summary` only counts what its map lists).

## What this enforces

1. **Coverage ratchet.** Every tracked or untracked-but-not-ignored template (a JSON or
   YAML file whose `Resources` hold `AWS::`/`Custom::` types, or a SAM `Transform`) is
   matched by a `.cfnlintrc` `templates` glob, matched by an `ignore_templates` glob
   (a declared exclusion), or listed in ``KNOWN_UNLINTED`` with a reason. A new
   unregistered template fails; a recorded one that has since been registered also
   fails, so the list only shrinks.
2. **Wiring.** `.github/workflows/validators.yml` has exactly one job whose step runs
   `make lint-cfn`; neither the job nor the step carries `continue-on-error` or `if`;
   the job is in `validators-summary.needs` and in the `Evaluate` results map.

Both checks have negative controls: the detection functions take the data they judge,
and the tests feed them a broken variant.
"""

from __future__ import annotations

import copy
import glob
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from cfnlint.decode import cfn_json, cfn_yaml

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "validators.yml"
SUMMARY_JOB = "validators-summary"
LINT_COMMAND = "make lint-cfn"
SUFFIXES = (".yaml", ".yml", ".json", ".template")
MAX_BYTES = 2_000_000

_NOT_REGISTERED = (
    "Not matched by any .cfnlintrc glob when this ratchet was introduced (2026-10-11). "
    "Register it under a glob, or declare the exclusion in ignore_templates with its reason."
)

# Templates that exist but are not linted. A ratchet, not an allowlist to grow: a
# template that is not here and not registered fails the test, and a template that is
# listed here and has since been registered fails too.
KNOWN_UNLINTED: dict[str, str] = {
    "infrastructure/agentcore-mcp-gateway/template.yaml": _NOT_REGISTERED,
    "infrastructure/ci-iam-roles.yaml": _NOT_REGISTERED,
    "infrastructure/demo-ad-environment.yaml": _NOT_REGISTERED,
    "infrastructure/pstk-automation/template.yaml": _NOT_REGISTERED,
    "infrastructure/s3ap-data-collection/template.yaml": _NOT_REGISTERED,
    "scripts/benchmark-lambda-template.yaml": _NOT_REGISTERED,
    "scripts/demo-inference-components.yaml": _NOT_REGISTERED,
    "solutions/amplify-portal/infrastructure/bedrock-guardrail.yaml": _NOT_REGISTERED,
    "solutions/edge/media-ivs-vod-publishing/cloudfront/cloudfront-s3ap-delivery.yaml": _NOT_REGISTERED,
    "solutions/event-driven/fpolicy/template-ec2.yaml": _NOT_REGISTERED,
}


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def candidate_files(root: Path) -> list[str]:
    """List files that might be templates: tracked plus untracked and not ignored.

    Args:
        root: Repository root (a git work tree), or a directory without git.

    Returns:
        Repository-relative paths with a template-like suffix, without node_modules.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        names = [n for n in proc.stdout.decode("utf-8").split("\0") if n]
    else:
        names = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    return sorted(n for n in names if n.endswith(SUFFIXES) and "node_modules" not in Path(n).parts)


def is_template(root: Path, name: str) -> bool:
    """Tell whether a file is a CloudFormation or SAM template.

    Args:
        root: Repository root.
        name: Repository-relative path.

    Returns:
        True when it parses, has a ``Resources`` map with an ``AWS::``/``Custom::``
        type, or a SAM ``Transform``.
    """
    path = root / name
    try:
        if path.stat().st_size > MAX_BYTES:
            return False
        if "Resources" not in path.read_text(encoding="utf-8"):
            return False
        data = cfn_json.load(str(path)) if name.endswith(".json") else cfn_yaml.load(str(path))
    except Exception:  # noqa: BLE001 - anything that does not decode is not a template
        return False
    if not isinstance(data, dict) or not isinstance(data.get("Resources"), dict):
        return False
    transform = data.get("Transform")
    if transform and "Serverless" in str(transform):
        return True
    return any(
        isinstance(r, dict) and isinstance(r.get("Type"), str) and r["Type"].startswith(("AWS::", "Custom::"))
        for r in data["Resources"].values()
    )


def expand(root: Path, patterns: list[str]) -> set[str]:
    """Expand ``.cfnlintrc`` globs the way cfn-lint does (recursive, from the root).

    Args:
        root: Repository root.
        patterns: Glob patterns.

    Returns:
        Matching repository-relative paths.
    """
    found: set[str] = set()
    for pattern in patterns:
        found |= set(glob.glob(pattern, root_dir=root, recursive=True))
    return found


def unlinted_templates(root: Path) -> set[str]:
    """Templates that are neither registered nor declared as ignored.

    Args:
        root: Repository root containing ``.cfnlintrc``.

    Returns:
        Repository-relative paths.
    """
    config = yaml.safe_load((root / ".cfnlintrc").read_text(encoding="utf-8"))
    registered = expand(root, config.get("templates", []))
    ignored = expand(root, config.get("ignore_templates", []))
    templates = {n for n in candidate_files(root) if is_template(root, n)}
    return templates - (registered - ignored) - ignored


def coverage_problems(unlinted: set[str], known: dict[str, str]) -> list[str]:
    """Compare the unlinted set with the ratchet.

    Args:
        unlinted: Templates found without registration.
        known: The ratchet (path -> reason).

    Returns:
        One message per problem (empty when the ratchet holds).
    """
    problems = [
        f"{name}: template is not linted. Register it in .cfnlintrc (templates:), or declare it in "
        "ignore_templates with a reason"
        for name in sorted(unlinted - set(known))
    ]
    problems += [
        f"{name}: is now linted or gone; remove it from KNOWN_UNLINTED" for name in sorted(set(known) - unlinted)
    ]
    problems += [f"{name}: KNOWN_UNLINTED entry has no reason" for name, why in sorted(known.items()) if not why]
    return problems


def test_every_template_is_linted_or_on_the_ratchet() -> None:
    assert coverage_problems(unlinted_templates(ROOT), KNOWN_UNLINTED) == []


def test_the_shared_vault_lab_templates_are_registered() -> None:
    config = yaml.safe_load((ROOT / ".cfnlintrc").read_text(encoding="utf-8"))
    registered = expand(ROOT, config["templates"]) - expand(ROOT, config.get("ignore_templates", []))
    lab = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "infrastructure" / "shared-backup-vault-lab" / "cloudformation").glob("*.yaml")
    )
    assert len(lab) == 3
    assert set(lab) <= registered


def _repo_with(tmp_path: Path, rc: str, files: dict[str, str]) -> Path:
    (tmp_path / ".cfnlintrc").write_text(rc, encoding="utf-8")
    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


TEMPLATE = "Resources:\n  Topic:\n    Type: AWS::SNS::Topic\n"
RC = 'templates:\n  - "a/*.yaml"\nignore_templates:\n  - "c/*.yaml"\n'


def test_an_unregistered_template_is_reported(tmp_path: Path) -> None:
    """Negative control: a template outside every glob must fail the ratchet."""
    repo = _repo_with(
        tmp_path,
        RC,
        {"a/x.yaml": TEMPLATE, "b/y.yaml": TEMPLATE, "c/z.yaml": TEMPLATE, "b/notes.yaml": "key: value\n"},
    )
    unlinted = unlinted_templates(repo)
    assert unlinted == {"b/y.yaml"}
    problems = coverage_problems(unlinted, {})
    assert len(problems) == 1 and "b/y.yaml" in problems[0]


def test_a_recorded_template_that_became_linted_is_reported(tmp_path: Path) -> None:
    repo = _repo_with(tmp_path, RC, {"a/x.yaml": TEMPLATE})
    problems = coverage_problems(unlinted_templates(repo), {"a/x.yaml": "was unregistered"})
    assert problems and "remove it from KNOWN_UNLINTED" in problems[0]


def test_a_known_entry_needs_a_reason() -> None:
    assert coverage_problems({"b/y.yaml"}, {"b/y.yaml": ""}) == ["b/y.yaml: KNOWN_UNLINTED entry has no reason"]


def test_sam_templates_and_json_templates_are_recognised(tmp_path: Path) -> None:
    repo = _repo_with(
        tmp_path,
        RC,
        {
            "b/sam.yaml": "Transform: AWS::Serverless-2016-10-31\nResources:\n  F:\n    Type: AWS::Serverless::Function\n",
            "b/t.json": '{"Resources": {"T": {"Type": "AWS::SNS::Topic"}}}',
            "b/other.json": '{"Resources": ["not", "a", "map"]}',
        },
    )
    assert unlinted_templates(repo) == {"b/sam.yaml", "b/t.json"}


def test_every_known_unlinted_template_exists() -> None:
    missing = [name for name in KNOWN_UNLINTED if not (ROOT / name).is_file()]
    assert missing == []


# --------------------------------------------------------------------------
# Wiring of the blocking job
# --------------------------------------------------------------------------


def load_workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    """Parse a workflow file with yaml.safe_load.

    Args:
        path: Workflow path.

    Returns:
        The parsed mapping.
    """
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def lint_jobs(workflow: dict[str, Any]) -> list[str]:
    """Names of jobs with a step whose ``run`` (stripped) is exactly ``make lint-cfn``.

    A comment line such as ``# make lint-cfn`` or a step that ends in ``|| echo`` is
    a different string, so it does not count.

    Args:
        workflow: Parsed workflow.

    Returns:
        Job ids.
    """
    return [
        job_id
        for job_id, job in workflow["jobs"].items()
        if any(str(step.get("run", "")).strip() == LINT_COMMAND for step in job.get("steps", []))
    ]


def wiring_problems(workflow: dict[str, Any]) -> list[str]:
    """Judge whether the cfn-lint job is blocking and reported by the summary.

    Args:
        workflow: Parsed workflow.

    Returns:
        One message per problem (empty when the wiring is sound).
    """
    jobs = lint_jobs(workflow)
    if len(jobs) != 1:
        return [f"expected exactly one job running `{LINT_COMMAND}`, found {jobs}"]
    name = jobs[0]
    job = workflow["jobs"][name]
    problems: list[str] = []
    if "continue-on-error" in job or "if" in job:
        problems.append(f"job {name} must not set continue-on-error or if")
    for step in job["steps"]:
        if str(step.get("run", "")).strip() == LINT_COMMAND and ("continue-on-error" in step or "if" in step):
            problems.append(f"the `{LINT_COMMAND}` step in {name} must not set continue-on-error or if")
    runs = [str(step.get("run", "")) for step in job["steps"]]
    if not any("scripts/check_tool_versions.py" in r for r in runs):
        problems.append(f"job {name} must check the resolved tool versions before linting")
    if not any("pip install -r requirements-dev.txt" in r for r in runs):
        problems.append(f"job {name} must install the pinned requirements-dev.txt")
    summary = workflow["jobs"].get(SUMMARY_JOB)
    if summary is None:
        return [*problems, f"{SUMMARY_JOB} job is missing"]
    if name not in summary.get("needs", []):
        problems.append(f"{name} is not in {SUMMARY_JOB}.needs")
    evaluate = "\n".join(str(step.get("run", "")) for step in summary["steps"] if step.get("name") == "Evaluate")
    entry = f'["{name}"]="${{{{ needs.{name}.result }}}}"'
    if entry not in evaluate:
        problems.append(f"{name} is not in the {SUMMARY_JOB} results map (expected {entry})")
    return problems


def test_the_cfn_lint_job_is_blocking_and_reported() -> None:
    assert wiring_problems(load_workflow()) == []


def test_the_cfn_lint_job_is_the_one_called_cfn_lint() -> None:
    assert lint_jobs(load_workflow()) == ["cfn-lint"]


def test_continue_on_error_is_detected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["cfn-lint"]["continue-on-error"] = True
    assert any("continue-on-error" in p for p in wiring_problems(workflow))
    workflow = copy.deepcopy(load_workflow())
    for step in workflow["jobs"]["cfn-lint"]["steps"]:
        if step.get("run") == LINT_COMMAND:
            step["continue-on-error"] = True
    assert any("step" in p and "continue-on-error" in p for p in wiring_problems(workflow))


def test_a_conditional_job_is_detected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["cfn-lint"]["if"] = "github.event_name == 'push'"
    assert wiring_problems(workflow)


def test_a_job_missing_from_needs_is_detected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"][SUMMARY_JOB]["needs"].remove("cfn-lint")
    assert any("needs" in p for p in wiring_problems(workflow))


def test_a_job_missing_from_the_results_map_is_detected() -> None:
    workflow = copy.deepcopy(load_workflow())
    for step in workflow["jobs"][SUMMARY_JOB]["steps"]:
        if step.get("name") == "Evaluate":
            step["run"] = "\n".join(line for line in step["run"].splitlines() if "needs.cfn-lint.result" not in line)
    assert any("results map" in p for p in wiring_problems(workflow))


def test_a_swallowed_exit_code_is_not_the_lint_command() -> None:
    """`make lint-cfn || echo` is a different string, so the job no longer counts."""
    workflow = copy.deepcopy(load_workflow())
    for step in workflow["jobs"]["cfn-lint"]["steps"]:
        if step.get("run") == LINT_COMMAND:
            step["run"] = f"{LINT_COMMAND} || echo failed"
    assert wiring_problems(workflow) == ["expected exactly one job running `make lint-cfn`, found []"]


def test_a_second_job_running_the_command_is_detected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["cfn-lint-again"] = copy.deepcopy(workflow["jobs"]["cfn-lint"])
    assert len(wiring_problems(workflow)) == 1


def test_a_commented_command_is_not_counted() -> None:
    workflow = copy.deepcopy(load_workflow())
    for step in workflow["jobs"]["cfn-lint"]["steps"]:
        if step.get("run") == LINT_COMMAND:
            step["run"] = f"# {LINT_COMMAND}"
    assert lint_jobs(workflow) == []


def test_the_job_installs_and_checks_the_pinned_tools() -> None:
    steps = load_workflow()["jobs"]["cfn-lint"]["steps"]
    runs = [step.get("run", "") for step in steps]
    assert runs.index("pip install -r requirements-dev.txt") < runs.index("python3 scripts/check_tool_versions.py")
    assert runs.index("python3 scripts/check_tool_versions.py") < runs.index(LINT_COMMAND)


@pytest.mark.parametrize("missing", ["scripts/check_tool_versions.py", "pip install -r requirements-dev.txt"])
def test_missing_tool_setup_is_detected(missing: str) -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["cfn-lint"]["steps"] = [
        step for step in workflow["jobs"]["cfn-lint"]["steps"] if missing not in str(step.get("run", ""))
    ]
    assert any("must" in p for p in wiring_problems(workflow))
