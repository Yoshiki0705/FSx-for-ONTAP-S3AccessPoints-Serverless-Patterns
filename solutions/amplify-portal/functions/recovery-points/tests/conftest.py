"""Test fixtures for the recovery-points Lambda."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("BACKUP_VAULT_NAMES", '["vault1"]')

# Loaded under a name of its own rather than imported as `index`. Fourteen handlers
# under `functions/` are `index.py`, and a bare `import index` in each test module
# would make whichever ran first win `sys.modules["index"]`, with the rest silently
# receiving that one in a full-tree pytest run. `scripts/check_test_module_names.py`
# refuses the bare import for exactly this reason. A unique name also keeps
# `patch("rp_handler.…")` working as a string target.
#
# Registered in `sys.modules` before `exec_module` so the module can be patched by
# name, and after the environment above is set, because the module reads
# BACKUP_VAULT_NAMES at import time.
MODULE_NAME = "rp_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "index.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
