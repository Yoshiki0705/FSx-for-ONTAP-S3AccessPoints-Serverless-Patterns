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


def test_the_layer_accepts_more_than_the_legacy_manylinux_tag():
    """A single legacy platform tag makes the pin's resolvability depend on upstream.

    This is the gap the pin-agreement rules above could not see. Renovate bumped Pillow
    to 12.3.0 and updated both pin files consistently, so every rule here passed -- but
    12.3.0 publishes no `manylinux2014_aarch64` wheel for cp313, and the layer build
    asked for exactly that tag with `--only-binary=:all:`. pip did not fall back; it
    reported no matching distribution and did not even list 12.3.0 as available. The
    break was invisible until the layer was built, which happens at deploy time.

    Whether a given release ships a given tag is an upstream fact this repository cannot
    assert offline. What it can assert is that the build does not narrow itself to the
    one tag that upstream has already stopped producing.
    """
    source = BACKEND.read_text(encoding="utf-8")
    tags = re.findall(r'"(manylinux[0-9_a-z]*_aarch64)"', source)
    assert len(tags) >= 2, (
        f"the layer build passes only {tags or 'no'} platform tag(s). Pillow moved from "
        "manylinux2014 to manylinux_2_28 for cp313, so a single tag can make an "
        "otherwise valid pin unresolvable. Pass both."
    )
