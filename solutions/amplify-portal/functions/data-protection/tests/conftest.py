"""Test fixtures for the data-protection Lambda."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ONTAP_MGMT_IP", "10.0.0.1")
os.environ.setdefault("ONTAP_SECRET_NAME", "test/secret")
os.environ.setdefault("SVM_NAME", "svm1")
os.environ.setdefault("VOLUME_NAME", "vol1")
