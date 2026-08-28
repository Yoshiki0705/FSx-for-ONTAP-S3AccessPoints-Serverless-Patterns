"""Test fixtures for the audit-log Lambda.

Loads the module under a name of its own. Fourteen functions under `functions/` have an
`index.py`, and importing one of them as `index` claims a name the others also answer to.
This directory happened to be the only one doing it, so the collision never fired -- it
resolved correctly because this directory's conftest was the last to put itself on
`sys.path` before its own test modules were imported. That is collection order, not a
guarantee. `scripts/check_test_module_names.py` now refuses the pattern; see
`functions/data-protection/tests/conftest.py` for what it looked like when it did fire.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ATHENA_DATABASE", "cloudtrail_logs")
os.environ.setdefault("ATHENA_TABLE", "cloudtrail_s3_events")
os.environ.setdefault("ATHENA_OUTPUT_LOCATION", "s3://example-athena-results/")
os.environ.setdefault("S3_AP_ALIAS", "example-ap-alias")
os.environ.setdefault("AWS_REGION", "ap-northeast-1")

MODULE_NAME = "audit_log_index"
MODULE_PATH = Path(__file__).parent.parent / "index.py"

_spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[MODULE_NAME] = _module
_spec.loader.exec_module(_module)
