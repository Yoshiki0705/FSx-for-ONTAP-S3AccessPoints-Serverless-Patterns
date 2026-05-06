"""conftest.py for scripts/tests — pytest path resolution."""
import sys
from pathlib import Path

# Add scripts directory to path for register_model imports
scripts_dir = Path(__file__).parent.parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
