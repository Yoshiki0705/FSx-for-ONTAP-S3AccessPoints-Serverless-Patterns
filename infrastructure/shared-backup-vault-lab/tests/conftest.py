"""Fixtures for the shared-vault lab tests (offline: no AWS, no real aws binary)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# lab_testlib sits beside this file; --import-mode=importlib does not add the
# directory to sys.path, so do it here (conftest is loaded before the tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab_testlib import Lab  # noqa: E402


@pytest.fixture
def lab(tmp_path: Path) -> Lab:
    """A fresh copy of the lab with stubs on PATH."""
    return Lab(tmp_path)
