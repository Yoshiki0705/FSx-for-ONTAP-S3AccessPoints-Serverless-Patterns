"""Tests for the pattern env-var contract rule.

The rule exists because three patterns passed an environment variable under a name
their handler did not read, so the operator's parameter was discarded in silence and
the run found nothing. The tests below matter more than the rule: a reader that stops
seeing code reports a clean tree, and this rule has two known blind spots it had to be
taught (patterns laid out under src/ rather than functions/, and handlers that read
through a module-level constant instead of a literal).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rule() -> ModuleType:
    """The rule under test, loaded from scripts/ by path.

    Returns:
        ModuleType: the check_pattern_env_contract module.
    """
    return _load("check_pattern_env_contract")


@pytest.fixture
def pattern(tmp_path: Path) -> Callable[..., Path]:
    """Build a throwaway pattern with a chosen template/handler arrangement."""

    def build(*, sets: str, reads: str, holder: str = "functions") -> Path:
        root = tmp_path / "solutions" / "industry" / "made-up"
        (root / holder / "discovery").mkdir(parents=True)
        (root / "template.yaml").write_text(
            "Resources:\n"
            "  DiscoveryFunction:\n"
            "    Properties:\n"
            "      Environment:\n"
            "        Variables:\n"
            f"          {sets}: !Ref SomeParam\n",
            encoding="utf-8",
        )
        (root / holder / "discovery" / "handler.py").write_text(
            f'import os\n\nprefix = os.environ.get("{reads}", "fallback/")\n',
            encoding="utf-8",
        )
        return root

    return build


class TestTheDefectThatShipped:
    def test_a_name_nothing_reads_is_reported(self, rule: ModuleType, pattern: Callable[..., Path]) -> None:
        """The shape found in three patterns: set as X, read as Y."""
        root = pattern(sets="GRANT_PREFIX", reads="GRANT_APPLICATION_PREFIX")
        provided = rule.env_names_set_by(root / "template.yaml")
        consumed = rule.env_names_read_by(root)
        assert "GRANT_PREFIX" in provided
        assert "GRANT_PREFIX" not in consumed, "the rule must not consider this name read"

    def test_the_corrected_arrangement_is_quiet(self, rule: ModuleType, pattern: Callable[..., Path]) -> None:
        root = pattern(sets="GRANT_APPLICATION_PREFIX", reads="GRANT_APPLICATION_PREFIX")
        provided = rule.env_names_set_by(root / "template.yaml")
        consumed = rule.env_names_read_by(root)
        assert set(provided) <= consumed


class TestTheBlindSpotsItWasTaught:
    def test_a_pattern_laid_out_under_src_is_still_read(self, rule: ModuleType, pattern: Callable[..., Path]) -> None:
        """flexcache keeps handlers in src/. Missing that reported a clean tree as ~20 findings."""
        root = pattern(sets="CACHE_SVM_NAME", reads="CACHE_SVM_NAME", holder="src")
        assert "CACHE_SVM_NAME" in rule.env_names_read_by(root)

    def test_a_read_through_a_module_constant_counts_as_read(self, rule: ModuleType, tmp_path: Path) -> None:
        """`_IP = "ONTAP_MANAGEMENT_IP"` then `os.environ.get(_IP)` is still a read."""
        root = tmp_path / "solutions" / "industry" / "indirect"
        (root / "functions" / "discovery").mkdir(parents=True)
        (root / "functions" / "discovery" / "handler.py").write_text(
            'import os\n\n_IP = "ONTAP_MANAGEMENT_IP"\nip = os.environ.get(_IP, "")\n',
            encoding="utf-8",
        )
        assert "ONTAP_MANAGEMENT_IP" in rule.env_names_read_by(root)


class TestTheRealTree:
    def test_shared_reads_are_derived_not_listed(self, rule: ModuleType) -> None:
        """A variable only a shared module consumes must not be reported.

        Derived from shared/ at runtime rather than hand-listed, so it cannot drift.
        """
        shared = rule.env_names_read_by_shared()
        assert "OUTPUT_S3AP_PREFIX" in shared, (
            "shared/output_writer.py reads this; if the derivation breaks, every pattern that sets it is reported"
        )

    def test_the_tree_is_within_budget(self, rule: ModuleType) -> None:
        assert rule.main() == 0
