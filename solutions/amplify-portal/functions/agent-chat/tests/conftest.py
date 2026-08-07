"""Test fixtures for the agent-chat Lambda."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# The module reads these at import time and decides at call time whether a feature
# is configured, so they have to be set before `handler` is imported.
os.environ.setdefault("AGENT_DIRECTORY_TABLE", "agents-test")
os.environ.setdefault("AGENT_TEAMS_TABLE", "teams-test")
os.environ.setdefault("CHAT_HISTORY_TABLE", "history-test")
os.environ.setdefault("S3_AP_ALIAS", "test-ap")
os.environ.setdefault("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
