"""A workflow GitHub refuses to load runs nothing, and says so only in its own UI.

## The failure being closed

`ci.yml` stopped running on 2026-08-15 and nobody noticed for three days.

`c26d131a` removed the `security-cfn` job as a duplicate of validators.yml
`cfn-guard-security`, and left `security-cfn` in `final-status.needs`. GitHub
rejects a workflow whose `needs` names a job that does not exist, so the file was
never loaded again: 94 runs recorded as failures without executing a step, and
zero pull request runs. Eight jobs -- CloudFormation lint, unit tests, runtime
compatibility, generated-file staleness, the portal vitest/tsc build, the storage
browser demo build, the Python security scan and the final status gate -- were
simply absent from every pull request merged in between.

Nothing local could see it. `yaml.safe_load` parses the file happily, because a
dangling `needs` is valid YAML and invalid only against the Actions schema. The
run list shows "failure", which reads like a test failure rather than a file that
was never loaded, and the commit that broke it was titled "make the quality gates
fail when they have not run".

## What this asserts

Only the things that stop a workflow from loading at all, checked against the
whole `.github/workflows` directory:

  1. every `needs` entry names a job defined in the same workflow
  2. the file parses, with no duplicate mapping keys (GitHub rejects those; PyYAML
     silently keeps the last one, which is how a duplicate survives review)

It deliberately does not try to validate the full Actions schema. That would mean
maintaining a copy of it here, and drifting from it quietly -- the same class of
problem as the one above.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


class _NoDuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys instead of keeping the last."""


def _no_duplicates(loader: yaml.Loader, node: yaml.Node, deep: bool = False) -> dict:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _no_duplicates,
)


def load_workflow(path: Path) -> dict:
    """Parse one workflow file.

    Args:
        path: The workflow file to read.

    Returns:
        The parsed workflow mapping.

    Raises:
        yaml.YAMLError: If the file does not parse, or repeats a mapping key.
    """
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_NoDuplicateKeyLoader)


def dangling_needs(workflow: dict) -> list[tuple[str, str]]:
    """Find `needs` entries that name no job in the same workflow.

    Args:
        workflow: A parsed workflow mapping.

    Returns:
        One `(job, missing dependency)` pair per unresolvable entry, empty when all
        dependencies resolve.
    """
    jobs = workflow.get("jobs") or {}
    missing: list[tuple[str, str]] = []
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        needs = job.get("needs")
        if needs is None:
            continue
        for dependency in [needs] if isinstance(needs, str) else needs:
            if dependency not in jobs:
                missing.append((name, dependency))
    return missing


def workflow_files() -> list[Path]:
    """Every workflow file GitHub would try to load.

    Returns:
        The `.yml` and `.yaml` files in `.github/workflows`, sorted by name.
    """
    return sorted(WORKFLOWS.glob("*.y*ml"))


@pytest.mark.parametrize("path", workflow_files(), ids=lambda p: p.name)
def test_workflow_parses_without_duplicate_keys(path: Path) -> None:
    try:
        workflow = load_workflow(path)
    except yaml.YAMLError as exc:
        pytest.fail(f"{path.name} will not load: {exc}")
    assert isinstance(workflow, dict), f"{path.name} did not parse to a mapping"


@pytest.mark.parametrize("path", workflow_files(), ids=lambda p: p.name)
def test_every_needs_names_a_job_that_exists(path: Path) -> None:
    missing = dangling_needs(load_workflow(path))
    assert not missing, (
        f"{path.name}: `needs` names jobs that do not exist, so GitHub will refuse to "
        f"load the workflow and none of its jobs will run: "
        + ", ".join(f"{job} -> {dependency}" for job, dependency in missing)
    )


def test_the_scan_is_not_vacuous() -> None:
    """An empty glob would make every parametrised case above pass by not existing."""
    found = workflow_files()
    assert len(found) >= 10, f"only {len(found)} workflow files found; the glob is broken"


def test_a_dangling_need_is_detected(tmp_path: Path) -> None:
    """The detector fails on the exact shape that shipped."""
    broken = tmp_path / "broken.yml"
    broken.write_text(
        "name: x\non:\n  pull_request:\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n    steps: []\n"
        "  final:\n    runs-on: ubuntu-latest\n    needs:\n      - a\n      - gone\n    steps: []\n",
        encoding="utf-8",
    )
    assert dangling_needs(load_workflow(broken)) == [("final", "gone")]


def test_a_resolvable_need_is_accepted(tmp_path: Path) -> None:
    """And passes the shape it must not block, including the single-string form."""
    fine = tmp_path / "fine.yml"
    fine.write_text(
        "name: x\non:\n  pull_request:\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n    steps: []\n"
        "  b:\n    runs-on: ubuntu-latest\n    needs: a\n    steps: []\n",
        encoding="utf-8",
    )
    assert dangling_needs(load_workflow(fine)) == []


def test_a_duplicate_key_is_detected(tmp_path: Path) -> None:
    """PyYAML's default would keep the last value and report nothing."""
    dupe = tmp_path / "dupe.yml"
    dupe.write_text("name: x\non:\n  pull_request:\non:\n  push:\njobs: {}\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_workflow(dupe)
