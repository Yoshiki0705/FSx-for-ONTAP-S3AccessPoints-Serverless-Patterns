"""Test fixtures for the agent-chat Lambda."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# The module reads these at import time and decides at call time whether a feature
# is configured, so they have to be set before the handler is imported.
os.environ.setdefault("AGENT_DIRECTORY_TABLE", "agents-test")
os.environ.setdefault("AGENT_TEAMS_TABLE", "teams-test")
os.environ.setdefault("CHAT_HISTORY_TABLE", "history-test")
os.environ.setdefault("S3_AP_ALIAS", "test-ap")
os.environ.setdefault("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# Loaded under a name of its own. This directory is the one that used to win
# `sys.modules["handler"]`, so the other two received *this* module and their patches
# failed against it. See `functions/data-protection/tests/conftest.py`.
MODULE_NAME = "agent_chat_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "handler.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
