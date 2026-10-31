"""conftest for stepfunctions-agentcore-tools tests.

Puts this tests directory on sys.path so `from helpers import load_handler`
resolves. The root conftest already adds the repository root for `shared`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
