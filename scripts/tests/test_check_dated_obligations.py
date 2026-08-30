"""Tests for scripts/check_dated_obligations.py.

The check exists to fire on a date. Its whole value is that it cannot go quiet, so
most of these assert that it *fails* on a crafted ledger, and several mutate the
module's own `LEDGER` to prove the reader reaches real content instead of passing
because it read nothing.

The two that carry the most weight:

- `test_it_fires_on_the_lead_day` and its neighbour pin the boundary. An off-by-one
  here is the difference between a deadline that arrives with time to act and one
  that arrives after the fact, and neither version fails visibly.
- `test_a_tracked_private_ref_is_rejected` guards the reason the ledger splits at
  all. `private_ref` is where a support case number and a file system ID go; if it
  can point at a tracked path, the ledger becomes the leak it was shaped to prevent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_dated_obligations.py"


def _load_module() -> ModuleType:
    """Import the checker by path, since scripts/ is not a package.

    Returns:
        The imported ``check_dated_obligations`` module.
    """
    spec = importlib.util.spec_from_file_location("check_dated_obligations", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

# A ledger entry that is valid in every respect, for tests that break one field.
GOOD_ENTRY = {
    "id": "example",
    "due": "2030-06-01",
    "lead_days": 14,
    "what": "do the thing",
    "why": "because the resource keeps billing until it is done",
    "where": "AGENTS.md",
    "private_ref": ".private/support-case-refs.md",
}


def _write_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: object) -> Path:
    """Point the module at a crafted ledger.

    Args:
        tmp_path: pytest temporary directory.
        monkeypatch: pytest monkeypatch fixture.
        payload: Object to serialise as the ledger, or a raw string to write verbatim.

    Returns:
        The path the module will now read.
    """
    path = tmp_path / "dated-obligations.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mod, "LEDGER", path)
    return path


# --------------------------------------------------------------------------
# The committed ledger


class TestTheRealLedger:
    """The ledger in the repository, read as the check reads it."""

    def test_it_is_sound_and_nothing_is_due_today(self) -> None:
        """A gate that fails on a clean tree is a gate someone turns off."""
        assert mod.check() == []

    def test_it_is_not_empty(self) -> None:
        """Every assertion below this would pass against an empty ledger."""
        assert len(mod._load()) >= 1

    def test_every_entry_has_every_field(self) -> None:
        for entry in mod._load():
            missing = [field for field in mod.REQUIRED_FIELDS if field not in entry]
            assert not missing, f"{entry.get('id')} is missing {missing}"

    def test_every_where_resolves(self) -> None:
        """The pointer is the only thing carrying why the deadline exists."""
        for entry in mod._load():
            assert (mod.ROOT / entry["where"]).is_file(), f"{entry['id']} points at a missing {entry['where']}"

    def test_every_private_ref_is_gitignored(self) -> None:
        """This repository is public and its history is permanent."""
        for entry in mod._load():
            assert mod._gitignored(entry["private_ref"]), (
                f"{entry['id']} names {entry['private_ref']}, which git does not ignore"
            )

    def test_the_snaplock_obligation_is_still_tracked(self) -> None:
        """Regression pin: this is the obligation the check was built for.

        Removing it should be a deliberate act performed after the volume is gone,
        not a side effect of an edit.
        """
        ids = {entry["id"] for entry in mod._load()}
        assert "snaplock-audit-log-volume-deletion" in ids


# --------------------------------------------------------------------------
# The date boundary


class TestWhenItFires:
    """`lead_days` is the whole mechanism; an off-by-one is invisible."""

    def test_it_is_silent_the_day_before_the_lead_day(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY]})
        assert mod.check(date(2030, 5, 17)) == []

    def test_it_fires_on_the_lead_day(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY]})
        problems = mod.check(date(2030, 5, 18))
        assert problems and "due in 14 day(s)" in problems[0]

    def test_it_fires_on_the_due_date_as_overdue(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY]})
        problems = mod.check(date(2030, 6, 1))
        assert problems and "OVERDUE" in problems[0]

    def test_it_stays_failing_long_after_the_due_date(self, tmp_path, monkeypatch) -> None:
        """An obligation does not expire by being ignored."""
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY]})
        assert mod.check(date(2031, 1, 1))

    def test_a_zero_lead_fires_exactly_on_the_due_date(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [{**GOOD_ENTRY, "lead_days": 0}]})
        assert mod.check(date(2030, 5, 31)) == []
        assert mod.check(date(2030, 6, 1))

    def test_the_failure_names_the_action_and_both_pointers(self, tmp_path, monkeypatch) -> None:
        """A failure that does not say what to do gets cleared by deleting the entry."""
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY]})
        report = mod.check(date(2030, 6, 1))[0]
        assert "do the thing" in report
        assert "AGENTS.md" in report
        assert ".private/support-case-refs.md" in report


# --------------------------------------------------------------------------
# Refusing to report a clean tree


class TestItCannotGoQuiet:
    """Each of these once-plausible ledgers must fail rather than pass."""

    def test_a_missing_ledger_is_fatal(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "LEDGER", tmp_path / "absent.json")
        with pytest.raises(SystemExit) as excinfo:
            mod.check()
        assert "missing" in str(excinfo.value)

    def test_an_empty_obligations_list_is_fatal(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": []})
        with pytest.raises(SystemExit):
            mod.check()

    def test_a_ledger_without_the_key_is_fatal(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"notes": "moved somewhere else"})
        with pytest.raises(SystemExit):
            mod.check()

    def test_unparseable_json_is_fatal(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, "{ not json")
        with pytest.raises(SystemExit):
            mod.check()


# --------------------------------------------------------------------------
# Malformed entries


class TestEntryValidation:
    """A field that is absent or wrong must be reported, not skipped over."""

    @pytest.mark.parametrize("field", mod.REQUIRED_FIELDS)
    def test_a_missing_field_is_reported(self, field, tmp_path, monkeypatch) -> None:
        entry = {key: value for key, value in GOOD_ENTRY.items() if key != field}
        _write_ledger(tmp_path, monkeypatch, {"obligations": [entry]})
        problems = mod.check(date(2026, 1, 1))
        assert problems and field in problems[0]

    def test_a_non_iso_due_date_is_reported(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [{**GOOD_ENTRY, "due": "2030/06/01"}]})
        problems = mod.check(date(2026, 1, 1))
        assert problems and "YYYY-MM-DD" in problems[0]

    @pytest.mark.parametrize("value", ["14", -1, 1.5, None])
    def test_a_bad_lead_days_is_reported(self, value, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [{**GOOD_ENTRY, "lead_days": value}]})
        assert mod.check(date(2026, 1, 1))

    def test_a_where_that_does_not_resolve_is_reported(self, tmp_path, monkeypatch) -> None:
        _write_ledger(tmp_path, monkeypatch, {"obligations": [{**GOOD_ENTRY, "where": "docs/gone.md"}]})
        problems = mod.check(date(2026, 1, 1))
        assert problems and "docs/gone.md" in problems[0]

    def test_a_tracked_private_ref_is_rejected(self, tmp_path, monkeypatch) -> None:
        """The reason the ledger splits into two files at all."""
        _write_ledger(tmp_path, monkeypatch, {"obligations": [{**GOOD_ENTRY, "private_ref": "docs/notes.md"}]})
        problems = mod.check(date(2026, 1, 1))
        assert problems and "does not ignore" in problems[0]

    def test_a_duplicate_id_is_reported(self, tmp_path, monkeypatch) -> None:
        """Two entries with one id let a later edit clear the earlier obligation."""
        _write_ledger(tmp_path, monkeypatch, {"obligations": [GOOD_ENTRY, {**GOOD_ENTRY, "due": "2031-01-01"}]})
        problems = mod.check(date(2026, 1, 1))
        assert any("duplicate id" in problem for problem in problems)

    def test_one_broken_entry_does_not_hide_a_due_one(self, tmp_path, monkeypatch) -> None:
        """Validation errors must not stop the scan before the deadline is seen."""
        broken = {key: value for key, value in GOOD_ENTRY.items() if key != "what"}
        due_now = {**GOOD_ENTRY, "id": "other", "due": "2026-01-01"}
        _write_ledger(tmp_path, monkeypatch, {"obligations": [broken, due_now]})
        problems = mod.check(date(2026, 1, 1))
        assert any("OVERDUE" in problem for problem in problems)


# --------------------------------------------------------------------------
# Wiring


class TestItIsWiredIn:
    """A check nothing runs is a file, not a gate."""

    def test_make_drift_runs_it(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "check_dated_obligations.py" in makefile

    def test_a_workflow_runs_it(self) -> None:
        workflows = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted((REPO_ROOT / ".github/workflows").glob("*.y*ml"))
        )
        assert "check_dated_obligations.py" in workflows


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
