#!/usr/bin/env python3
"""Tests for the repository-name redirect check.

The point of this gate is that it fires on input a link checker calls healthy, so the
tests that matter are the ones asserting it fails: a renamed name that still resolves,
and a name that does not resolve at all. A test that only proves the clean case passes
would be satisfied by a checker that never fails at all.

`collect` and `audit` are exercised directly rather than through the CLI, because the
CLI reads the real repository through `git ls-files` and reaches the real network. The
end-to-end negative case is covered separately by running the command against a
tracked scratch file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_repo_name_redirects import audit, collect  # noqa: E402


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_reference_inside_a_fenced_code_block_is_collected(tmp_path: Path) -> None:
    """The deliberate difference from the Playbook's version.

    Ninety-one files in this repository carry their only repository reference inside a
    ```bash fence as a `git clone` line. Skipping fences would skip exactly the case
    with the most direct consequence for a reader.
    """
    path = write(
        tmp_path,
        "demo-guide.md",
        "# Guide\n\n```bash\ngit clone https://github.com/Owner/old-name.git\n```\n",
    )
    assert collect([path], root=tmp_path) == {"Owner/old-name": ["demo-guide.md"]}


def test_clone_suffix_is_not_part_of_the_name(tmp_path: Path) -> None:
    plain = write(tmp_path, "a.md", "https://github.com/Owner/repo\n")
    cloned = write(tmp_path, "b.md", "https://github.com/Owner/repo.git\n")
    assert collect([plain, cloned], root=tmp_path) == {"Owner/repo": ["a.md", "b.md"]}


@pytest.mark.parametrize(
    "body",
    [
        "See [the repo](https://github.com/Owner/repo).\n",
        "See <https://github.com/Owner/repo>\n",
        "See https://github.com/Owner/repo, then stop.\n",
    ],
)
def test_trailing_prose_punctuation_is_stripped(tmp_path: Path, body: str) -> None:
    path = write(tmp_path, "a.md", body)
    assert list(collect([path], root=tmp_path)) == ["Owner/repo"]


def test_product_surfaces_are_not_repository_names(tmp_path: Path) -> None:
    """`github.com/apps/renovate` is a GitHub App, not a name that can go stale."""
    path = write(
        tmp_path,
        "a.md",
        "https://github.com/apps/renovate and https://github.com/Owner/repo\n",
    )
    assert list(collect([path], root=tmp_path)) == ["Owner/repo"]


def test_an_explicit_path_is_scanned_whatever_its_suffix(tmp_path: Path) -> None:
    """The suffix filter belongs to `tracked_prose()`, not to `collect()`.

    Named for what it asserts. `collect` scans what it is handed, so the `.md`/`.txt`
    restriction applies to the default file set only — worth pinning, because moving
    that filter into `collect` would silently change what a caller passing explicit
    paths gets back.
    """
    template = write(tmp_path, "template.yaml", "https://github.com/Owner/repo\n")
    assert list(collect([template], root=tmp_path)) == ["Owner/repo"]


def test_a_redirecting_name_is_a_finding() -> None:
    """The case a link checker reports as healthy: 200 through a redirect."""
    stale, unreachable = audit(
        {"Owner/old-name": ["docs/a.md"]},
        resolver=lambda _slug: ("renamed", "Owner/New-Name"),
    )
    assert unreachable == []
    assert len(stale) == 1
    assert "Owner/old-name is now Owner/New-Name" in stale[0]
    assert "docs/a.md" in stale[0]


def test_an_unresolvable_name_is_a_finding() -> None:
    stale, unreachable = audit(
        {"Owner/gone": ["README.md"]},
        resolver=lambda _slug: ("missing", "404 (deleted, redirect expired, or now private)"),
    )
    assert unreachable == []
    assert len(stale) == 1
    assert "does not resolve" in stale[0]


def test_a_canonical_name_is_not_a_finding() -> None:
    stale, unreachable = audit(
        {"Owner/repo": ["README.md"]},
        resolver=lambda _slug: ("ok", None),
    )
    assert (stale, unreachable) == ([], [])


def test_transport_failure_is_not_reported_as_a_rename() -> None:
    """A 503 says nothing about the name.

    Reporting it as stale would send someone to rewrite a name that was correct, and
    reporting it as clean would claim a verdict that was never reached.
    """
    stale, unreachable = audit(
        {"Owner/repo": ["README.md"]},
        resolver=lambda _slug: ("unreachable", "HTTP 503"),
    )
    assert stale == []
    assert unreachable == ["Owner/repo: HTTP 503"]


def test_the_file_list_is_truncated_but_counted() -> None:
    """A name in ninety-eight files must not print ninety-eight paths."""
    files = [f"docs/f{i}.md" for i in range(10)]
    stale, _ = audit(
        {"Owner/old": files},
        resolver=lambda _slug: ("renamed", "Owner/new"),
    )
    assert "and 6 more" in stale[0]
    assert "docs/f9.md" not in stale[0]


# --- fail-open and reporting ---


def test_an_empty_corpus_is_a_failure_not_a_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate that certifies nothing is a gate a file-filter change switches off silently."""
    import check_repo_name_redirects as module

    monkeypatch.setattr(module, "collect", lambda *a, **k: {})
    monkeypatch.setattr(sys, "argv", ["check_repo_name_redirects.py"])
    assert module.main() == 1


def test_findings_dominate_when_names_are_also_unreachable() -> None:
    def resolver(slug: str) -> tuple[str, str | None]:
        return ("missing", "404") if slug == "o/gone" else ("unreachable", "HTTP 503")

    stale, unreachable = audit({"o/gone": ["a.md"], "o/x": ["b.md"], "o/y": ["c.md"]}, resolver=resolver)
    assert len(stale) == 1
    assert len(unreachable) == 2


# --- casing, the class the default mode cannot see ---


def test_a_miscased_name_is_a_finding_under_strict_casing() -> None:
    stale, unreachable = audit(
        {"Owner/lower-case-name": ["README.md"]},
        resolver=lambda _s: ("ok", None),
        casing_resolver=lambda _s: ("miscased", "Owner/Lower-Case-Name"),
    )
    assert unreachable == []
    assert len(stale) == 1
    assert "capitalised Owner/Lower-Case-Name" in stale[0]


def test_casing_is_not_consulted_for_a_name_that_already_failed() -> None:
    """Reporting a rename and its capitalisation would be one problem under two labels."""
    calls: list[str] = []

    def casing(slug: str) -> tuple[str, str | None]:
        calls.append(slug)
        return "ok", None

    audit(
        {"o/renamed": ["a.md"]},
        resolver=lambda _s: ("renamed", "o/new"),
        casing_resolver=casing,
    )
    assert calls == []


def test_casing_is_skipped_entirely_when_no_resolver_is_given() -> None:
    stale, unreachable = audit({"o/x": ["a.md"]}, resolver=lambda _s: ("ok", None))
    assert (stale, unreachable) == ([], [])


def test_an_unreachable_casing_lookup_is_not_a_finding() -> None:
    stale, unreachable = audit(
        {"o/x": ["a.md"]},
        resolver=lambda _s: ("ok", None),
        casing_resolver=lambda _s: ("unreachable", "HTTP 403"),
    )
    assert stale == []
    assert unreachable == ["o/x (casing): HTTP 403"]


# --- collect() edges the first version got wrong ---


def test_a_hyphen_wrapped_url_does_not_accuse_a_real_repository(tmp_path: Path) -> None:
    """A name cannot end in a hyphen, so one came from a wrapped line, not from the name."""
    path = write(tmp_path, "a.md", "see https://github.com/Owner/repo-\n")
    assert list(collect([path], root=tmp_path)) == ["Owner/repo"]


@pytest.mark.parametrize("segment", ["trending", "gist", "explore", "codespaces"])
def test_more_product_surfaces_are_excluded(tmp_path: Path, segment: str) -> None:
    path = write(tmp_path, "a.md", f"https://github.com/{segment}/whatever\n")
    assert collect([path], root=tmp_path) == {}


def test_an_owner_named_like_a_product_surface_is_still_collected(tmp_path: Path) -> None:
    """`Security` is a plausible org name; the exclusion list is lowercase URL segments."""
    path = write(tmp_path, "a.md", "https://github.com/Security/realrepo\n")
    assert list(collect([path], root=tmp_path)) == ["Security/realrepo"]
