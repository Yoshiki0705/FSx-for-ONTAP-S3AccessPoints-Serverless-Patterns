"""Test helpers for stepfunctions-agentcore-tools.

Loads each handler module under a name unique to this pattern so a whole-tree
pytest run does not collide with another pattern's `handler` module in
sys.modules (see scripts/check_test_module_names.py). The root conftest already
puts the repository root on sys.path, so `from shared...` resolves inside the
loaded handlers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_FUNCTIONS = Path(__file__).resolve().parent.parent / "functions"


def load_handler(function_name: str) -> ModuleType:
    """Load a handler module under a name unique to this pattern.

    Args:
        function_name: Directory name under functions/ (discovery/processing/report).

    Returns:
        The loaded handler module.
    """
    unique_name = f"sfn_agentcore_{function_name}_handler"
    if unique_name in sys.modules:
        return sys.modules[unique_name]
    path = _FUNCTIONS / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(unique_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module
