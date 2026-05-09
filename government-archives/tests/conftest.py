"""Pytest fixtures for UC16 government-archives tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_handler(function_name: str):
    """Load UC16 handler module from government-archives/functions/{function_name}/handler.py."""
    module_name = f"uc16_{function_name}_handler"
    handler_path = (
        Path(__file__).resolve().parent.parent
        / "functions"
        / function_name
        / "handler.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def discovery_handler():
    return _load_handler("discovery")


@pytest.fixture
def ocr_handler():
    return _load_handler("ocr")


@pytest.fixture
def classification_handler():
    return _load_handler("classification")


@pytest.fixture
def entity_extraction_handler():
    return _load_handler("entity_extraction")


@pytest.fixture
def redaction_handler():
    return _load_handler("redaction")


@pytest.fixture
def index_generation_handler():
    return _load_handler("index_generation")


@pytest.fixture
def compliance_check_handler():
    return _load_handler("compliance_check")


@pytest.fixture
def foia_deadline_handler():
    return _load_handler("foia_deadline_reminder")


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id-uc16"
    ctx.function_name = "test-function"
    return ctx
