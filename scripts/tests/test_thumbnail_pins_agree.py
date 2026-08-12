"""The thumbnail layer's Pillow pin must match the one the tests import.

Three places name this version and they can disagree silently: the function's
`requirements.txt` (what the layer is built from), `requirements-dev.txt` (what the
tests import), and the installed interpreter. A test suite that decodes images with a
different Pillow than production runs is a test of something else -- and image
libraries are exactly where a version difference changes behaviour, because the
decoders, the resampling filters and the bomb limits all move between releases.

There is a sibling rule for the Lambda runtime pins (`test_check_runtime_pins_agree`).
This is the same idea for the one third-party dependency the portal deploys.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYER_REQUIREMENTS = REPO_ROOT / "solutions" / "amplify-portal" / "functions" / "thumbnails" / "requirements.txt"
DEV_REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"
BACKEND = REPO_ROOT / "solutions" / "amplify-portal" / "amplify" / "backend.ts"

PIN = re.compile(r"^Pillow==(\d+\.\d+\.\d+)$", re.MULTILINE | re.IGNORECASE)


def _pinned(path: Path) -> str:
    match = PIN.search(path.read_text(encoding="utf-8"))
    assert match, f"no exact Pillow pin in {path.relative_to(REPO_ROOT)}"
    return match.group(1)


def test_the_layer_pins_pillow_exactly():
    """A range would make the layer's contents depend on the day it was built."""
    assert _pinned(LAYER_REQUIREMENTS)


def test_the_dev_pin_matches_the_layer_pin():
    layer = _pinned(LAYER_REQUIREMENTS)
    dev = _pinned(DEV_REQUIREMENTS)
    assert dev == layer, (
        f"requirements-dev.txt pins Pillow {dev} but the layer is built from {layer}. "
        "The tests would decode images with a different build than production runs."
    )


def test_the_installed_pillow_matches_the_pin():
    """Skipped where Pillow is absent, so this does not block an unrelated suite."""
    pillow = pytest.importorskip("PIL")
    assert pillow.__version__ == _pinned(LAYER_REQUIREMENTS), (
        f"installed Pillow {pillow.__version__} does not match the pin. Run: pip install -r requirements-dev.txt"
    )


def test_the_layer_reads_the_version_from_the_requirements_file():
    """backend.ts must not carry a second copy of the number.

    Naming it in the CDK as well would put the value in two places, and the one that
    drifts is the one nothing imports.
    """
    source = BACKEND.read_text(encoding="utf-8")
    assert "functions/thumbnails/requirements.txt" in source, (
        "backend.ts should read the Pillow version from the function's requirements.txt"
    )
    hardcoded = re.search(r"Pillow==\d", source)
    assert not hardcoded, "backend.ts hardcodes a Pillow version instead of reading the pin"
