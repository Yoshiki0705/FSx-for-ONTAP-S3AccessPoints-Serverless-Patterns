"""Test fixtures for the restore Lambda."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set before the module is loaded: the handler reads these at import time.
os.environ.setdefault("BACKUP_RESTORE_ROLE_ARN", "arn:aws:iam::111122223333:role/BackupRestore")
os.environ.setdefault("ALLOWED_SVM_IDS", '["svm-01234567890abcdef"]')
os.environ.setdefault("ALLOWED_FILE_SYSTEM_IDS", '["fs-01234567890abcdef"]')

# Loaded under a name of its own rather than imported as `index`. Fourteen handlers
# under `functions/` are `index.py`, and a bare `import index` in each test module
# would make whichever ran first win `sys.modules["index"]`, with the rest silently
# receiving that one in a full-tree pytest run. `scripts/check_test_module_names.py`
# refuses the bare import for exactly this reason. A unique name also keeps
# `patch("restore_handler.…")` working as a string target.
MODULE_NAME = "restore_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "index.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
