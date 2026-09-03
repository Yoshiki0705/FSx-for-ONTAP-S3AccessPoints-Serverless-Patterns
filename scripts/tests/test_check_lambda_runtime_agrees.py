"""Tests for scripts/check_lambda_runtime_agrees.py.

The check exists because `PY_VERSION` in the Makefile carried a comment saying it
"must match the Lambda runtime in the SAM templates" and nothing verified it. The
version is repeated in 350+ tracked places, so these tests care most about the
directions the check must FAIL in — a version check that only ever passes is the
same thing as the comment it replaced.

`test_a_disagreeing_template_is_caught` and the CDK case below are the shapes that
would ship two runtimes from one repository. The vacuity tests matter as much: the
corpus is discovered from `git ls-files`, and a discovery that returns nothing
would report a clean tree for every version, forever.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_lambda_runtime_agrees.py"

_spec = importlib.util.spec_from_file_location("check_lambda_runtime_agrees", SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["check_lambda_runtime_agrees"] = mod
_spec.loader.exec_module(mod)


MAKEFILE = "PY_VERSION := 3.13\n"
PYPROJECT = """\
[project]
name = "x"
version = "0"
requires-python = ">=3.12"

[tool.ruff]
target-version = "py312"
"""
TEMPLATE = """\
Resources:
  Fn:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.13
"""
CDK = """\
const layer = new lambda.LayerVersion(stack, "L", {
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_12, lambda.Runtime.PYTHON_3_13],
});
const fn = new lambda.Function(stack, "F", {
  runtime: lambda.Runtime.PYTHON_3_13,
});
"""
WORKFLOW = """\
name: ci
jobs:
  runtime-compat:
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
"""


def build_repo(
    tmp_path: Path,
    *,
    makefile: str = MAKEFILE,
    pyproject: str = PYPROJECT,
    template: str | None = TEMPLATE,
    cdk: str | None = CDK,
    workflow: str | None = WORKFLOW,
) -> Path:
    """Create a git repository shaped like the real one, with the given contents.

    A real repository is needed rather than a directory: the check discovers its
    corpus with `git ls-files`, which is how build artefacts under `.aws-sam/` stay
    out of scope.

    Args:
        tmp_path: pytest temporary directory.
        makefile: Contents of `Makefile`.
        pyproject: Contents of `pyproject.toml`.
        template: Contents of a SAM template, or `None` to omit it.
        cdk: Contents of a TypeScript file, or `None` to omit it.
        workflow: Contents of a workflow, or `None` to omit it.

    Returns:
        The repository root.
    """
    root = tmp_path / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    if template is not None:
        (root / "template.yaml").write_text(template, encoding="utf-8")
    if cdk is not None:
        (root / "backend.ts").write_text(cdk, encoding="utf-8")
    if workflow is not None:
        (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")

    for argv in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    return root


def run(root: Path) -> int:
    """Invoke the checker against a fixture repository.

    Args:
        root: Repository root produced by `build_repo`.

    Returns:
        The checker's exit code.
    """
    return mod.main(["--root", str(root)])


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required to discover the corpus")


# -- the agreeing baseline -------------------------------------------------


def test_a_repository_that_agrees_passes(tmp_path: Path) -> None:
    assert run(build_repo(tmp_path)) == 0


# -- the disagreements this exists to catch -------------------------------


def test_a_disagreeing_template_is_caught(tmp_path: Path) -> None:
    # One stack left behind on a bump. Nothing else in the repository puts two
    # templates side by side, so this is invisible without the check.
    root = build_repo(tmp_path, template=TEMPLATE.replace("python3.13", "python3.12"))
    assert run(root) == 1


def test_a_disagreeing_cdk_runtime_is_caught(tmp_path: Path) -> None:
    root = build_repo(
        tmp_path, cdk=CDK.replace("runtime: lambda.Runtime.PYTHON_3_13", "runtime: lambda.Runtime.PYTHON_3_12")
    )
    assert run(root) == 1


def test_bumping_py_version_alone_is_caught(tmp_path: Path) -> None:
    # The failure the check is named for: raising PY_VERSION changes which
    # interpreter runs the tests and nothing that gets deployed.
    root = build_repo(tmp_path, makefile="PY_VERSION := 3.14\n")
    assert run(root) == 1


def test_a_version_hardcoded_in_a_test_file_is_in_scope(tmp_path: Path) -> None:
    # backend-assertions.test.ts asserts on `lambda.Runtime.PYTHON_3_13` as a regex
    # literal. It is not deployed, but it pins the version, so a bump that misses it
    # fails the portal suite instead of this check — with a message about a count.
    root = build_repo(tmp_path)
    (root / "assertions.test.ts").write_text("match(/runtime: lambda\\.Runtime\\.PYTHON_3_12/g)\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    assert run(root) == 1


def test_a_layer_that_cannot_be_attached_from_the_pinned_runtime_is_caught(tmp_path: Path) -> None:
    root = build_repo(
        tmp_path,
        cdk="const l = new lambda.LayerVersion(s, 'L', { compatibleRuntimes: [lambda.Runtime.PYTHON_3_12] });\n",
    )
    assert run(root) == 1


# -- what must NOT be a finding -------------------------------------------


def test_an_older_runtime_in_a_layer_compatibility_list_is_allowed(tmp_path: Path) -> None:
    # A layer may stay attachable from an older runtime; the list is a superset by
    # design. The real backend.ts lists [PYTHON_3_12, PYTHON_3_13], and reporting
    # that would make the check fail on the repository as it is meant to be.
    assert run(build_repo(tmp_path)) == 0


def test_a_source_floor_below_the_runtime_is_allowed(tmp_path: Path) -> None:
    # requires-python is >=3.12 against a python3.13 runtime on purpose: the modules
    # stay importable on the older interpreter. Requiring equality here would force
    # one of the two to be wrong.
    assert run(build_repo(tmp_path)) == 0


def test_build_artefacts_are_out_of_scope(tmp_path: Path) -> None:
    # `.aws-sam/build/` holds copies of the templates and is not tracked. One of
    # them really does say python3.12 while its source says 3.13 — a stale artefact
    # `make clean` removes, not drift.
    root = build_repo(tmp_path)
    stale = root / ".aws-sam" / "build"
    stale.mkdir(parents=True)
    (stale / "template.yaml").write_text(TEMPLATE.replace("python3.13", "python3.12"), encoding="utf-8")
    assert run(root) == 0


def test_workflow_yaml_is_not_read_as_a_template(tmp_path: Path) -> None:
    # Workflows are .yml too. A `Runtime:` line in one is not a Lambda declaration,
    # and pinning the setup-python version there is not a runtime either.
    root = build_repo(tmp_path, workflow=WORKFLOW + "        # Runtime: python3.9\n")
    assert run(root) == 0


# -- the floor and the matrix ---------------------------------------------


def test_a_floor_disagreeing_with_ruff_is_caught(tmp_path: Path) -> None:
    root = build_repo(tmp_path, pyproject=PYPROJECT.replace('target-version = "py312"', 'target-version = "py311"'))
    assert run(root) == 1


def test_a_floor_newer_than_the_runtime_is_caught(tmp_path: Path) -> None:
    root = build_repo(
        tmp_path,
        pyproject=PYPROJECT.replace('">=3.12"', '">=3.14"').replace('"py312"', '"py314"'),
    )
    assert run(root) == 1


def test_a_matrix_that_omits_the_deployed_runtime_is_caught(tmp_path: Path) -> None:
    root = build_repo(tmp_path, workflow=WORKFLOW.replace('["3.12", "3.13"]', '["3.12"]'))
    assert run(root) == 1


def test_a_matrix_reaching_below_the_floor_is_caught(tmp_path: Path) -> None:
    # The state this repository was in: requires-python said >=3.12 and CI gated the
    # build on 3.11 as well.
    root = build_repo(tmp_path, workflow=WORKFLOW.replace('["3.12", "3.13"]', '["3.11", "3.12", "3.13"]'))
    assert run(root) == 1


def test_no_matrix_at_all_is_caught(tmp_path: Path) -> None:
    root = build_repo(tmp_path, workflow="name: ci\njobs: {}\n")
    assert run(root) == 1


# -- vacuity: a check that scans nothing must not pass ---------------------


def test_a_missing_py_version_is_an_error_not_a_pass(tmp_path: Path) -> None:
    root = build_repo(tmp_path, makefile="PYTHON := python3\n")
    assert run(root) == 1


def test_no_templates_found_is_an_error_not_a_pass(tmp_path: Path) -> None:
    assert run(build_repo(tmp_path, template=None)) == 1


def test_no_cdk_tokens_found_is_an_error_not_a_pass(tmp_path: Path) -> None:
    assert run(build_repo(tmp_path, cdk=None)) == 1


def test_the_message_names_the_file_and_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = build_repo(tmp_path, template=TEMPLATE.replace("python3.13", "python3.12"))
    run(root)
    out = capsys.readouterr().out
    assert "template.yaml:5" in out
    assert "python3.12" in out


# -- the real repository ---------------------------------------------------


def test_this_repository_agrees_with_itself() -> None:
    """The real files, not a fixture."""
    assert mod.main([]) == 0


def test_the_real_scan_is_not_vacuous(capsys: pytest.CaptureFixture[str]) -> None:
    """Guards the counts printed above against a discovery that quietly narrows."""
    mod.main([])
    out = capsys.readouterr().out
    template_count = int(out.split("Scanned ", 1)[1].split(" ", 1)[0])
    assert template_count > 100, f"only {template_count} template declarations found; discovery is broken"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
