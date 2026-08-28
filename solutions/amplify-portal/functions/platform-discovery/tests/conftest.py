"""Load the handler under a unique module name.

Four functions in this portal have a file called ``handler.py``. Importing them
all as ``handler`` in one pytest run gives whichever loaded first to every test
that asks, so the name here is unique to this function.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MODULE_NAME = "platform_discovery_handler"
_spec = importlib.util.spec_from_file_location(MODULE_NAME, Path(__file__).parent.parent / "handler.py")
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
