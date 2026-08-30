"""Tests for the shared-application-module-name check.

The check exists because a name shared by several function directories resolves to
whichever was imported first, and the wrong module is not an error -- it is a module that
answers, missing the attributes the test expects. That reads as 375 unrelated failures.

Written against a temporary tree rather than the repository, so a case can be constructed
and so the tests keep meaning something once the repository stops violating the rule.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_test_module_names.py"


def load_checker(function_roots: list[Path]) -> Any:
    """Import the checker with its scan roots pointed at a temporary tree."""
    spec = importlib.util.spec_from_file_location("check_test_module_names_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_test_module_names_under_test"] = module
    spec.loader.exec_module(module)
    module.FUNCTION_ROOTS = function_roots
    module.REPO_ROOT = function_roots[0].parent
    return module


def make_function(root: Path, name: str, module: str, test_body: str) -> None:
    """Create `root/name/<module>.py` and `root/name/tests/test_it.py`."""
    function_dir = root / name
    (function_dir / "tests").mkdir(parents=True)
    (function_dir / f"{module}.py").write_text("VALUE = 1\n")
    (function_dir / "tests" / "test_it.py").write_text(test_body)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An empty stand-in for `functions/`."""
    functions = tmp_path / "functions"
    functions.mkdir()
    return functions


class TestSharedNames:
    def test_reports_a_test_importing_a_name_two_directories_provide(self, root: Path) -> None:
        make_function(root, "alpha", "handler", "import handler\n")
        make_function(root, "beta", "handler", "from handler import VALUE\n")
        problems = load_checker([root]).problems()
        assert len(problems) == 2
        assert all("handler" in problem for problem in problems)
        # Names both providers, because the fix is to see that the name is contested.
        assert all("alpha" in problem and "beta" in problem for problem in problems)

    def test_accepts_a_name_only_one_directory_provides(self, root: Path) -> None:
        make_function(root, "alpha", "onlyhere", "import onlyhere\n")
        make_function(root, "beta", "handler", "import handler\n")
        assert load_checker([root]).problems() == []

    def test_accepts_a_unique_alias_even_where_the_file_is_shared(self, root: Path) -> None:
        # The fix the message asks for: the module is loaded under a name of its own, so
        # the test imports that name and not the contested one.
        make_function(root, "alpha", "handler", "import alpha_handler as handler\n")
        make_function(root, "beta", "handler", "from beta_handler import VALUE\n")
        assert load_checker([root]).problems() == []

    def test_reads_an_import_inside_a_function_body(self, root: Path) -> None:
        # The repository's style is to import inside each test, so a module-level-only
        # scan would see nothing at all.
        make_function(root, "alpha", "handler", "import handler\n")
        make_function(
            root,
            "beta",
            "handler",
            "def test_x():\n    from handler import VALUE\n    assert VALUE\n",
        )
        assert len(load_checker([root]).problems()) == 2


class TestWhatIsNotReported:
    def test_ignores_a_name_appearing_only_in_a_string(self, root: Path) -> None:
        # A subprocess given its own PYTHONPATH imports unambiguously, and
        # `functions/data-protection` has such a test.
        make_function(root, "alpha", "handler", "import alpha_handler\n")
        make_function(
            root,
            "beta",
            "handler",
            'CMD = ["python", "-c", "import handler; print(handler.VALUE)"]\n',
        )
        assert load_checker([root]).problems() == []

    def test_ignores_conftest(self, root: Path) -> None:
        # The conftest is where the unique-name load belongs; it names the module by path.
        make_function(root, "alpha", "handler", "import alpha_handler\n")
        make_function(root, "beta", "handler", "import beta_handler\n")
        (root / "beta" / "tests" / "conftest.py").write_text("import handler\n")
        assert load_checker([root]).problems() == []

    def test_ignores_a_relative_import(self, root: Path) -> None:
        make_function(root, "alpha", "handler", "import alpha_handler\n")
        make_function(root, "beta", "handler", "from . import handler\n")
        assert load_checker([root]).problems() == []


class TestExitCode:
    def test_fails_when_a_name_is_shared(self, root: Path) -> None:
        make_function(root, "alpha", "handler", "import handler\n")
        make_function(root, "beta", "handler", "import handler\n")
        assert load_checker([root]).main() == 1

    def test_passes_on_a_clean_tree(self, root: Path) -> None:
        make_function(root, "alpha", "handler", "import alpha_handler\n")
        assert load_checker([root]).main() == 0

    def test_passes_when_a_root_does_not_exist(self, tmp_path: Path) -> None:
        # The scan list is written by hand, so a renamed directory must not read as clean
        # by crashing. It reads as clean by having nothing to scan, which the repository
        # run below distinguishes.
        assert load_checker([tmp_path / "absent" / "functions"]).main() == 0


class TestAgainstTheRepository:
    def test_the_repository_has_no_shared_application_module(self) -> None:
        spec = importlib.util.spec_from_file_location("check_test_module_names_real", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["check_test_module_names_real"] = module
        spec.loader.exec_module(module)
        assert module.problems() == []

    def test_the_scan_root_exists(self) -> None:
        # Guards the check itself: pointed at a path that is not there, it reports PASS.
        spec = importlib.util.spec_from_file_location("check_test_module_names_real2", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["check_test_module_names_real2"] = module
        spec.loader.exec_module(module)
        assert module.FUNCTION_ROOTS
        for scan_root in module.FUNCTION_ROOTS:
            assert scan_root.is_dir(), scan_root
        # And that it is actually finding test files, so a PASS means something.
        found = sum(len(list(r.glob("*/tests/**/*.py"))) for r in module.FUNCTION_ROOTS)
        assert found > 5
