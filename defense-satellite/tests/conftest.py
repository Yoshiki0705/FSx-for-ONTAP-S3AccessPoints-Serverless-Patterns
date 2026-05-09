"""Pytest fixtures for UC15 defense-satellite tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_handler(function_name: str):
    """Load UC15 handler module from defense-satellite/functions/{function_name}/handler.py."""
    module_name = f"uc15_{function_name}_handler"
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
def tiling_handler():
    return _load_handler("tiling")


@pytest.fixture
def object_detection_handler():
    return _load_handler("object_detection")


@pytest.fixture
def change_detection_handler():
    return _load_handler("change_detection")


@pytest.fixture
def geo_enrichment_handler():
    return _load_handler("geo_enrichment")


@pytest.fixture
def alert_generation_handler():
    return _load_handler("alert_generation")


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id-12345"
    ctx.function_name = "test-function"
    return ctx
