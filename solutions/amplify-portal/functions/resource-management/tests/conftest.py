"""Test fixtures for the resource-management Lambda.

Loads the handler under a name of its own. See
`functions/data-protection/tests/conftest.py` for what went wrong when four functions with
a `handler.py` each imported theirs as `handler`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ONTAP_MGMT_IP", "10.0.0.1")
os.environ.setdefault("ONTAP_SECRET_NAME", "test/secret")
os.environ.setdefault("SVM_NAME", "svm1")
os.environ.setdefault("VOLUME_NAME", "vol1")

MODULE_NAME = "rm_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "handler.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
