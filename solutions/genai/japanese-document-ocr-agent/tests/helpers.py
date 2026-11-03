"""Test helpers for japanese-document-ocr-agent.

Loads each handler (and each script under samples/) under a name unique to this
pattern, so a whole-tree pytest run does not collide with another pattern's
`handler` module in sys.modules (see scripts/check_test_module_names.py). The
root conftest already puts the repository root on sys.path, so `from shared...`
resolves inside the loaded modules.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PATTERN_DIR = Path(__file__).resolve().parent.parent
FUNCTIONS_DIR = PATTERN_DIR / "functions"
SAMPLES_DIR = PATTERN_DIR / "samples"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(unique_name: str, path: Path) -> ModuleType:
    if unique_name in sys.modules:
        return sys.modules[unique_name]
    spec = importlib.util.spec_from_file_location(unique_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so dataclasses can resolve their own module.
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


def load_handler(function_name: str) -> ModuleType:
    """Load a handler module under a name unique to this pattern.

    Args:
        function_name: Directory name under functions/ (e.g. "discovery").

    Returns:
        The loaded handler module.
    """
    return _load(f"ja_ocr_{function_name}_handler", FUNCTIONS_DIR / function_name / "handler.py")


def load_sample_module(script_name: str) -> ModuleType:
    """Load a script under samples/ under a name unique to this pattern.

    Args:
        script_name: File name without extension (e.g. "score_ocr").

    Returns:
        The loaded module.
    """
    return _load(f"ja_ocr_sample_{script_name}", SAMPLES_DIR / f"{script_name}.py")
