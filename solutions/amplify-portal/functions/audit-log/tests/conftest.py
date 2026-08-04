"""Test fixtures for the audit-log Lambda."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ATHENA_DATABASE", "cloudtrail_logs")
os.environ.setdefault("ATHENA_TABLE", "cloudtrail_s3_events")
os.environ.setdefault("ATHENA_OUTPUT_LOCATION", "s3://example-athena-results/")
os.environ.setdefault("S3_AP_ALIAS", "example-ap-alias")
os.environ.setdefault("AWS_REGION", "ap-northeast-1")
