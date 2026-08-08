"""Every Makefile target must be declared `.PHONY`.

`security` was not, and it collides with the `security/` directory. make therefore
answered "`security' is up to date" and ran bandit zero times — while `make
security` sat in the pre-commit list and in AGENTS.md, appearing to pass. The first
real run found nine Medium-and-above findings, two of them genuine SQL injection
vectors in handlers that interpolated values read from the watched volume.

The instance is fixed by adding the target. This closes the class: any future
target named after a path that exists would fail the same silent way, and a silent
no-op is the worst kind of gate because its output is indistinguishable from
success.

Declaring a target phony is only wrong when the recipe genuinely produces a file of
that name, so that is asserted too rather than assumed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "Makefile"

# Pattern-rule and special targets are not phony candidates.
IGNORED_PREFIXES = (".", "%")


def targets() -> list[str]:
    """Every explicit target defined in the Makefile, in order of appearance."""
    text = MAKEFILE.read_text(encoding="utf-8")
    found = re.findall(r"^([A-Za-z0-9_.\-]+):(?!=)", text, re.M)
    return [t for t in dict.fromkeys(found) if not t.startswith(IGNORED_PREFIXES)]


def declared() -> set[str]:
    """Every name listed in the Makefile's `.PHONY` declaration."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^\.PHONY:((?:[^\n\\]*\\\n)*[^\n]*)", text, re.M)
    if not match:
        return set()
    return set(match.group(1).replace("\\", " ").split())


def test_every_target_is_declared_phony() -> None:
    missing = [t for t in targets() if t not in declared()]
    assert not missing, (
        "Makefile targets missing from .PHONY: "
        + ", ".join(missing)
        + ". A target that is not phony is skipped when a path of the same name "
        "exists, and make reports success without running the recipe."
    )


def test_no_declared_target_shares_a_name_with_a_path() -> None:
    """The condition that makes the omission dangerous, checked directly.

    Passing this does not make the declaration optional — it records which targets
    are one `mkdir` away from breaking if the declaration were ever dropped.
    """
    colliding = [t for t in targets() if (ROOT / t).exists()]
    for target in colliding:
        assert target in declared(), (
            f"target {target!r} collides with an existing path and is not .PHONY, "
            "so make will report it up to date and never run it"
        )


def test_no_phony_target_produces_a_file_of_its_own_name() -> None:
    """Declaring a real file target phony would break incremental builds."""
    produced = [t for t in declared() if (ROOT / t).is_file()]
    assert not produced, "these .PHONY names are also files, so the declaration may be wrong: " + ", ".join(produced)


def test_the_declaration_is_not_empty() -> None:
    """A regex that silently matches nothing would make the checks above vacuous."""
    assert declared(), ".PHONY declaration not found or unparsed"
    assert targets(), "no Makefile targets found; the target regex is broken"
