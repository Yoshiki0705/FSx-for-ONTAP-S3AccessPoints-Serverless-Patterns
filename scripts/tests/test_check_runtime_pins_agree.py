"""Tests for scripts/check_runtime_pins_agree.py.

Includes the disagreement that prompted the check: Renovate raised boto3 in
pyproject.toml and left requirements.txt behind, because it manages the two files
as separate managers. Nothing failed — the tests ran against one version while the
package metadata claimed the other.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_runtime_pins_agree.py"

_spec = importlib.util.spec_from_file_location("check_runtime_pins_agree", SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["check_runtime_pins_agree"] = mod
_spec.loader.exec_module(mod)


def write_pair(tmp_path: Path, pyproject_deps: str, requirements: str) -> tuple[Path, Path]:
    """Write a pyproject/requirements fixture pair.

    Args:
        tmp_path: pytest temporary directory.
        pyproject_deps: Body of the `dependencies` array.
        requirements: Contents of the requirements file.

    Returns:
        `(pyproject path, requirements path)`.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        f'[project]\nname = "x"\nversion = "0"\ndependencies = [\n{pyproject_deps}\n]\n',
        encoding="utf-8",
    )
    reqs = tmp_path / "requirements.txt"
    reqs.write_text(requirements, encoding="utf-8")
    return pyproject, reqs


def run(pyproject: Path, requirements: Path) -> int:
    """Invoke the checker against a fixture pair.

    Args:
        pyproject: Fixture `pyproject.toml`.
        requirements: Fixture `requirements.txt`.

    Returns:
        The checker's exit code.
    """
    return mod.main(["--pyproject", str(pyproject), "--requirements", str(requirements)])


def test_agreeing_pins_pass(tmp_path: Path) -> None:
    pair = write_pair(tmp_path, '    "boto3==1.43.68",', "boto3==1.43.68\n")
    assert run(*pair) == 0


def test_the_renovate_split_is_caught(tmp_path: Path) -> None:
    # The real case: a dependency PR that touched pyproject.toml only.
    pair = write_pair(tmp_path, '    "boto3==1.43.68",', "boto3==1.43.67\n")
    assert run(*pair) == 1


def test_a_dependency_in_only_one_file_is_not_a_finding(tmp_path: Path) -> None:
    # aws-xray-sdk is optional and lives in requirements.txt alone. Treating a
    # one-sided declaration as drift would make the check fail on the repository
    # as it is meant to be.
    pair = write_pair(tmp_path, '    "boto3==1.43.68",', "boto3==1.43.68\naws-xray-sdk==2.15.0\n")
    assert run(*pair) == 0


def test_comments_are_not_read_as_pins(tmp_path: Path) -> None:
    # requirements.txt carries long comment blocks, including versions that were
    # deliberately rejected. Reading `# ... 4.17.3 ...` as a pin would invent a
    # disagreement.
    pair = write_pair(
        tmp_path,
        '    "jsonschema==4.26.0",',
        "# jsonschema==4.17.3 was rejected; see the note\njsonschema==4.26.0\n",
    )
    assert run(*pair) == 0


def test_a_trailing_comment_on_a_pin_line_is_stripped(tmp_path: Path) -> None:
    pair = write_pair(tmp_path, '    "urllib3==2.7.0",', "urllib3==2.7.0  # runtime\n")
    assert run(*pair) == 0


def test_non_pinned_specifiers_are_skipped(tmp_path: Path) -> None:
    # A range is not a pin, so there is no version to compare. The pinning policy
    # is enforced elsewhere; this check is only about the two files agreeing.
    pair = write_pair(tmp_path, '    "boto3>=1.43",', "boto3==1.43.68\n")
    assert run(*pair) == 0


def test_names_are_compared_case_insensitively(tmp_path: Path) -> None:
    pair = write_pair(tmp_path, '    "AWS-XRay-SDK==2.15.0",', "aws-xray-sdk==2.15.1\n")
    assert run(*pair) == 1


def test_the_message_names_both_files_and_versions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pair = write_pair(tmp_path, '    "boto3==1.43.68",', "boto3==1.43.67\n")
    run(*pair)
    out = capsys.readouterr().out
    assert "1.43.68" in out and "1.43.67" in out
    assert "pyproject.toml" in out and "requirements.txt" in out
    # The likely cause is named, so the next person does not have to rediscover
    # that Renovate manages the two files separately.
    assert "separate managers" in out


def test_this_repository_agrees_with_itself() -> None:
    """The real files, not a fixture."""
    assert mod.main([]) == 0
