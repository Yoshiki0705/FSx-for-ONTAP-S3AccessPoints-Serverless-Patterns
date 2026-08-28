#!/usr/bin/env python3
"""Refuse a test that imports an application module by a name another one also uses.

The failure this prevents
------------------------
Fourteen functions under `solutions/amplify-portal/functions/` have an `index.py` and nine
have a `handler.py`. Each test directory puts its own function directory on `sys.path` and
imported its module as `handler` or `index`. Whichever was imported first won
`sys.modules[<name>]`, and every later test file silently received that one.

Per-directory runs passed, so nothing reported it. Running the whole tree in one pytest
invocation produced 375 failures and 58 errors, of the form:

    AttributeError: <module 'handler' from '.../agent-chat/handler.py'>
    does not have the attribute '_get_arp_response_client'

and one test that patched the wrong module reached real AWS instead, turning a 10-second
directory into a 5-minute one waiting on credential discovery.

`--import-mode=importlib` in pytest.ini does not cover this. It addresses collisions
between *test* module names; the name colliding here belongs to the application module.

The rule
--------
A test may import a module that sits beside it, as long as no other function directory
provides a module of the same name. Where the name is shared, load it under a name of its
own:

    spec = importlib.util.spec_from_file_location("dp_handler", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["dp_handler"] = module
    spec.loader.exec_module(module)

Registering it in `sys.modules` keeps `patch("dp_handler.…")` working as a string target,
so the tests do not have to move to `patch.object`.

Not checked here: a module imported inside a subprocess that sets its own `PYTHONPATH`.
That one is unambiguous by construction, and `functions/data-protection` has such a test.
Only module-level and function-level `import` statements are read, so a name appearing
inside a string is ignored.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Where a function's code and its tests live side by side. Each entry is scanned for
# `<root>/<function>/<module>.py` and `<root>/<function>/tests/`.
FUNCTION_ROOTS = [
    REPO_ROOT / "solutions" / "amplify-portal" / "functions",
]


def modules_by_name(root: Path) -> dict[str, list[Path]]:
    """Map each top-level module name under `root` to the directories providing it.

    Args:
        root: A directory whose children are function directories.

    Returns:
        Module name to the function directories that contain `<name>.py`.
    """
    found: dict[str, list[Path]] = defaultdict(list)
    for function_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for module in sorted(function_dir.glob("*.py")):
            found[module.stem].append(function_dir)
    return found


def imported_names(test_file: Path) -> set[str]:
    """The top-level module names this file imports.

    Only the first component matters: `from index import handler` claims `index`, and
    `import handler as handler_module` claims `handler`.

    Args:
        test_file: The test file to read.

    Returns:
        Module names imported by name, ignoring relative imports.
    """
    names: set[str] = set()
    tree = ast.parse(test_file.read_text(), filename=str(test_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def problems() -> list[str]:
    """One message per test file importing a shared application module name."""
    found: list[str] = []
    for root in FUNCTION_ROOTS:
        if not root.is_dir():
            continue
        providers = modules_by_name(root)
        shared = {name: dirs for name, dirs in providers.items() if len(dirs) > 1}
        for test_file in sorted(root.glob("*/tests/**/*.py")):
            if test_file.name == "conftest.py":
                # A conftest is where the unique-name load belongs, so it names the module
                # deliberately and by path rather than by import.
                continue
            for name in sorted(imported_names(test_file) & shared.keys()):
                owners = ", ".join(d.name for d in shared[name])
                found.append(
                    f"{test_file.relative_to(REPO_ROOT)} imports `{name}`, which "
                    f"{len(shared[name])} function directories provide ({owners}). "
                    "Whichever is imported first wins sys.modules and the rest receive it. "
                    "Load it under a name of its own in the directory's conftest.py."
                )
    return found


def main() -> int:
    found = problems()
    if found:
        print("TEST MODULE NAMES: FAIL")
        for problem in found:
            print(f"  {problem}")
        return 1
    total = sum(len(list(root.glob("*/tests/**/*.py"))) for root in FUNCTION_ROOTS if root.is_dir())
    print(f"TEST MODULE NAMES: PASS ({total} test file(s), no shared application module)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
