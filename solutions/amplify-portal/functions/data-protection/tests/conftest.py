"""Test fixtures for the data-protection Lambda."""

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

# Imported here under a name of its own rather than left to `import handler` in the test
# module.
#
# Four functions under `functions/` have a `handler.py`, and each test directory used to
# put its own on `sys.path` and import it as `handler`. Whichever ran first won
# `sys.modules["handler"]`, and the rest silently received that one: running the whole of
# `functions/` in one pytest invocation produced 375 failures and 58 errors, of the form
# "module 'handler' from .../agent-chat/handler.py does not have the attribute
# '_get_arp_response_client'". Per-directory runs passed, so the collision only appeared in
# the run nobody did.
#
# `--import-mode=importlib` in pytest.ini does not help: it addresses collisions between
# *test* module names, and the name colliding here belongs to the application module.
#
# A unique name also keeps `patch("dp_handler.…")` working as a string target, which is how
# the tests below are written. Registered in `sys.modules` before `exec_module` so the
# module can be patched by name, and after the environment above is set, because the module
# reads its configuration at import time.
MODULE_NAME = "dp_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "handler.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
