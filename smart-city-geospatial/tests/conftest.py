"""Pytest fixtures for UC17 smart-city-geospatial tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_handler(function_name: str):
    module_name = f"uc17_{function_name}_handler"
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
def preprocessing_handler():
    return _load_handler("preprocessing")


@pytest.fixture
def land_use_classification_handler():
    return _load_handler("land_use_classification")


@pytest.fixture
def change_detection_handler():
    return _load_handler("change_detection")


@pytest.fixture
def infra_assessment_handler():
    return _load_handler("infra_assessment")


@pytest.fixture
def risk_mapping_handler():
    return _load_handler("risk_mapping")


@pytest.fixture
def report_generation_handler():
    return _load_handler("report_generation")


@pytest.fixture
def lambda_context():
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id-uc17"
    ctx.function_name = "test-function"
    return ctx
