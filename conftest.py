"""Root conftest.py for pytest path resolution.

Adds the project root to sys.path so that 'shared' module imports work
correctly when running tests from any directory.
"""
import sys
from pathlib import Path

# Add project root to path for shared module imports
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
