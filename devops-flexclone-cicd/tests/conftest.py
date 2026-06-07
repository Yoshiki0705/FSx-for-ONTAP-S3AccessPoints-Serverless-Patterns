"""Test configuration for devops-flexclone-cicd UC."""

import sys
from pathlib import Path

# Add UC functions to path for test imports
UC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(UC_ROOT))
