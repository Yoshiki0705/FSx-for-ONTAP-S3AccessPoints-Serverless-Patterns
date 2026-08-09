"""Tests for the agent context budget and reachability check.

The check exists because three failures had already happened and none of them
produced an error message.

AGENTS.md grew to 78 KB. It is loaded on every turn and cannot be made
conditional, so the cost was paid in every session, mostly for pitfall tables
that matter only while doing that one kind of work.

Eleven steering files declared `inclusion: auto` without the `name` and
`description` that auto inclusion requires, so Kiro never registered them and
never loaded them. An agent missing knowledge it was given looks exactly like an
agent that was never given it.

Then the fix caused the third: moving that content into `.kiro/`, which is
deliberately unpublished, deleted it from the repository and left AGENTS.md
pointing at twelve paths a reader cannot open. Hence the loader budget and the
published-target checks below — a loader that grows is knowledge leaking back to
the side nobody else can read, and neither leak is visible by reading the diff.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_agent_context_budget as budget  # noqa: E402

GOOD_LOADER = (
    "---\ninclusion: auto\nname: topic\ndescription: when to load\n---\n\n内容は `docs/agent/topic.md` にある。\n"
)
GOOD_SKILL = "---\nname: proc\ndescription: when to use\n---\n\n内容は `docs/agent/proc.md` にある。\n"
AGENTS = "# AGENTS\n\n[topic](docs/agent/topic.md)\n"


def build(root: Path, agents: str = AGENTS, **files: str) -> None:
    """Create a synthetic workspace.

    Args:
        root: Directory to populate.
        agents: Contents of AGENTS.md.
        **files: Extra files keyed by path relative to root, `|` as separator.
    """
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    (root / "docs/agent").mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        path = root / relative.replace("|", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def at(monkeypatch, tmp_path):
    """Return a callable that runs every check against a synthetic workspace."""

    def run(**kwargs) -> list[str]:
        build(tmp_path, **kwargs)
        monkeypatch.setattr(budget, "ROOT", tmp_path)
        problems: list[str] = []
        budget.check_budgets(problems)
        budget.check_index_targets(problems)
        budget.check_loaders(problems)
        return problems

    return run


BASE = {
    "docs|agent|topic.md": "# topic\n",
    ".kiro|steering|topic.md": GOOD_LOADER,
}


class TestHealthy:
    def test_a_well_formed_workspace_is_silent(self, at):
        assert at(**BASE) == []

    def test_skill_loader_is_accepted(self, at):
        problems = at(
            agents=AGENTS + "[proc](docs/agent/proc.md)\n",
            **BASE,
            **{
                "docs|agent|proc.md": "# proc\n",
                ".kiro|skills|proc|SKILL.md": GOOD_SKILL,
            },
        )
        assert problems == []


class TestPublishedSide:
    """AGENTS.md must only point at things a reader of the repository can open."""

    def test_link_to_kiro_is_rejected(self, at):
        problems = at(
            agents="# AGENTS\n\n[t](docs/agent/topic.md)\n[x](.kiro/steering/topic.md)\n",
            **BASE,
        )
        assert any(".kiro/" in p and "公開しない" in p for p in problems)

    def test_dangling_link_is_caught(self, at):
        problems = at(agents="# AGENTS\n\n[t](docs/agent/renamed.md)\n", **BASE)
        assert any("renamed.md" in p for p in problems)

    def test_missing_index_entirely_is_caught(self, at):
        problems = at(agents="# AGENTS\n\nno pointers at all\n", **BASE)
        assert any("入口" in p for p in problems)

    def test_gitignored_target_is_caught(self, monkeypatch, tmp_path):
        """A link that resolves locally and 404s for every reader.

        This needs a real repository: only git can tell the difference, which is
        the whole reason the check asks git rather than the filesystem.
        """
        build(tmp_path, **BASE)
        (tmp_path / ".gitignore").write_text("docs/agent/topic.md\n", encoding="utf-8")
        for args in (
            ["init", "-q"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "t"],
            ["add", "-A"],
        ):
            subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)
        monkeypatch.setattr(budget, "ROOT", tmp_path)
        problems: list[str] = []
        budget.check_index_targets(problems)
        assert any("含まれていません" in p for p in problems)


class TestLoaders:
    def test_auto_without_description_is_caught(self, at):
        problems = at(**{**BASE, ".kiro|steering|topic.md": "---\ninclusion: auto\nname: topic\n---\n"})
        assert any("description" in p for p in problems)

    def test_auto_without_name_is_caught(self, at):
        problems = at(**{**BASE, ".kiro|steering|topic.md": "---\ninclusion: auto\ndescription: d\n---\n"})
        assert any("name" in p for p in problems)

    def test_filematch_without_pattern_is_caught(self, at):
        problems = at(**{**BASE, ".kiro|steering|topic.md": "---\ninclusion: fileMatch\n---\n"})
        assert any("fileMatchPattern" in p for p in problems)

    def test_filematch_pattern_as_yaml_list_is_accepted(self, at):
        """A block list is a value. Reading only inline pairs reported it missing."""
        problems = at(
            **{
                **BASE,
                ".kiro|steering|topic.md": (
                    '---\ninclusion: fileMatch\nfileMatchPattern:\n  - "**/*.drawio"\n---\n\n`docs/agent/topic.md`\n'
                ),
            }
        )
        assert problems == []

    def test_invalid_inclusion_value_is_caught(self, at):
        problems = at(**{**BASE, ".kiro|steering|topic.md": "---\ninclusion: sometimes\n---\n"})
        assert any("sometimes" in p for p in problems)

    def test_skill_name_must_match_directory(self, at):
        problems = at(
            agents=AGENTS + "[proc](docs/agent/proc.md)\n",
            **BASE,
            **{
                "docs|agent|proc.md": "# proc\n",
                ".kiro|skills|proc|SKILL.md": "---\nname: other\ndescription: d\n---\n",
            },
        )
        assert any("proc" in p and "一致しません" in p for p in problems)

    def test_dangling_pointer_is_caught(self, at):
        problems = at(
            **{
                **BASE,
                ".kiro|steering|topic.md": GOOD_LOADER.replace("topic.md", "gone.md"),
            }
        )
        assert any("gone.md" in p for p in problems)

    def test_fat_loader_is_caught(self, at):
        """Content in an unpublished loader is content the repository does not have."""
        problems = at(**{**BASE, ".kiro|steering|topic.md": GOOD_LOADER + "x" * budget.LOADER_BUDGET})
        assert any("公開されない" in p for p in problems)

    def test_always_on_project_steering_may_hold_content(self, at):
        """`inclusion: always` files are project rules, not loaders, so they are exempt."""
        problems = at(
            **{
                **BASE,
                ".kiro|steering|rules.md": "---\ninclusion: always\n---\n" + "x" * 5000,
            }
        )
        assert problems == []


class TestBudgets:
    def test_oversized_agents_is_caught(self, at):
        problems = at(agents=AGENTS + "x" * budget.AGENTS_BUDGET, **BASE)
        assert any("AGENTS.md" in p and "予算" in p for p in problems)

    def test_oversized_agent_doc_is_caught(self, at):
        problems = at(**{**BASE, "docs|agent|topic.md": "# topic\n" + "y" * budget.AGENT_DOC_BUDGET})
        assert any("docs/agent/topic.md" in p for p in problems)


class TestCheckoutWithoutKiro:
    def test_loaders_are_skipped_but_the_index_is_not(self, monkeypatch, tmp_path):
        """A clone has no `.kiro/`. That is expected, and the index still matters."""
        build(tmp_path, **{"docs|agent|topic.md": "# topic\n"})
        monkeypatch.setattr(budget, "ROOT", tmp_path)
        assert budget.kiro_present() is False
        problems: list[str] = []
        budget.check_loaders(problems)
        assert problems == []
        budget.check_index_targets(problems)
        assert problems == []
        assert budget.main() == 0

    def test_a_broken_index_still_fails_without_kiro(self, monkeypatch, tmp_path):
        build(tmp_path, agents="# AGENTS\n\n[t](docs/agent/gone.md)\n")
        monkeypatch.setattr(budget, "ROOT", tmp_path)
        problems: list[str] = []
        budget.check_index_targets(problems)
        assert any("gone.md" in p for p in problems)


class TestRealRepository:
    def test_this_repository_passes(self):
        """The check must pass against the repository as it stands."""
        problems: list[str] = []
        budget.check_budgets(problems)
        budget.check_index_targets(problems)
        budget.check_loaders(problems)
        assert problems == []
