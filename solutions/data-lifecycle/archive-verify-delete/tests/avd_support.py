"""Constants and loaders shared by the tests (imported by name; see conftest.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PATTERN_DIR = Path(__file__).resolve().parent.parent
REGION = "ap-northeast-1"
AP = "source-ap-bucket"
ARCHIVE = "archive-bucket"
SECOND = "second-copy-bucket"
TABLE = "avd-ledger"


def load_handler(function_name: str):
    """Load functions/<name>/handler.py under a name no other pattern uses."""
    module_name = f"avd_{function_name}_handler"
    path = PATTERN_DIR / "functions" / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_fargate_entrypoint():
    path = PATTERN_DIR / "fargate" / "entrypoint.py"
    spec = importlib.util.spec_from_file_location("avd_fargate_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["avd_fargate_entrypoint"] = module
    spec.loader.exec_module(module)
    return module
