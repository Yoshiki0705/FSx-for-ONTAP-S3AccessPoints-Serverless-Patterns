"""Tests for scripts/aws_support_inquiry.py.

Two things must hold and neither is visible by reading the file:

- **Filing cannot happen by accident.** A support case is visible to AWS, attributed
  to the account, and cannot be unsent. `test_filing_without_confirm_refuses` pins
  that, and it is the reason `--draft` is the default.
- **The case number cannot reach a tracked path.** The ledger is committed to a public
  repository with permanent history. `test_a_tracked_private_ref_is_refused` and
  `test_a_tracked_detail_file_is_refused` pin both doors it could come in through.

The body is asserted on too, because a case that omits what was already read is a
question AWS has to reverse-engineer, and the whole point of building it from the
ledger is that the reading is already recorded.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "aws_support_inquiry.py"


def _load_module() -> ModuleType:
    """Import the tool by path, since scripts/ is not a package.

    Returns:
        The imported ``aws_support_inquiry`` module.
    """
    spec = importlib.util.spec_from_file_location("aws_support_inquiry", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

ENTRY: dict = {
    "id": "E-901",
    "claim": "AWS does not expose request metrics for this thing.",
    "subject": "AWS",
    "tier": "hypothesis",
    "premise": True,
    "sources": [
        {
            "url": "https://docs.aws.amazon.com/example.html",
            "read": "full",
            "retrieved": "2026-09-05",
            "says": "Enumerates the metrics; this is not among them.",
        },
        {"url": "https://docs.aws.amazon.com/other.html", "read": "selective", "retrieved": "2026-09-05"},
    ],
    "observation": "list-metrics returned 33 names, none matching, 2026-09-05 ap-northeast-1",
    "why_not_documented_is_not_absent": "Absence from a page is not a statement of absence.",
    "support_inquiry": {
        "status": "required",
        "topic": "Whether a documented mechanism exists today.",
        "private_ref": ".private/support-case-refs.md",
    },
    "feature_request": {"status": "not-yet"},
    "appears_in": ["AGENTS.md"],
}


# --- the body ------------------------------------------------------------------


def test_the_body_carries_the_claim_and_the_question() -> None:
    """A case without both is a question AWS cannot answer in one round trip."""
    body = mod.build_body(ENTRY)
    assert ENTRY["claim"] in body
    assert ENTRY["support_inquiry"]["topic"] in body


def test_the_body_lists_the_documents_that_were_read() -> None:
    """Filing without saying what was read invites the answer "see the docs"."""
    body = mod.build_body(ENTRY)
    assert "https://docs.aws.amazon.com/example.html" in body
    assert "retrieved 2026-09-05" in body


def test_a_selective_read_is_marked_as_such_in_the_body() -> None:
    """AWS should be able to see which pages were skimmed and which were read."""
    body = mod.build_body(ENTRY)
    assert "[selective]" in body


def test_the_body_carries_the_observation() -> None:
    """What was measured, with its environment, is the part that makes it answerable."""
    assert ENTRY["observation"] in mod.build_body(ENTRY)


def test_the_body_asks_about_the_roadmap() -> None:
    """Asking only "does it exist" produces an answer that goes stale silently."""
    assert "roadmap" in mod.build_body(ENTRY)


# --- the safety rules ----------------------------------------------------------


def test_filing_without_confirm_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default must not be to send."""
    monkeypatch.setattr(mod, "_gitignored", lambda _p: True)
    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_file([ENTRY], ENTRY, None, confirm=False)
    assert "--confirm" in str(excinfo.value)


def test_a_tracked_private_ref_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The case number must not be able to land where git will keep it forever."""
    monkeypatch.setattr(mod, "_gitignored", lambda _p: False)
    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_file([ENTRY], ENTRY, None, confirm=True)
    assert "not gitignored" in str(excinfo.value)


def test_a_missing_private_ref_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nowhere private to record it, filing would leave the number in a log."""
    entry = json.loads(json.dumps(ENTRY))
    del entry["support_inquiry"]["private_ref"]
    monkeypatch.setattr(mod, "_gitignored", lambda _p: True)
    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_file([entry], entry, None, confirm=True)
    assert "private_ref" in str(excinfo.value)


def test_a_tracked_detail_file_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The second door: account and resource identifiers appended from a tracked path."""

    def ignored(path: str) -> bool:
        return path != "AGENTS.md"

    monkeypatch.setattr(mod, "_gitignored", ignored)
    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_file([ENTRY], ENTRY, "AGENTS.md", confirm=True)
    assert "not gitignored" in str(excinfo.value)


def test_an_unknown_id_fails_rather_than_filing_something_else() -> None:
    """Silently picking a neighbouring entry would file the wrong question."""
    with pytest.raises(SystemExit):
        mod._entry([ENTRY], "E-999")


# --- the service code ----------------------------------------------------------


def test_the_default_service_code_exists() -> None:
    """A blank service code is rejected by the API at the worst moment."""
    assert mod.DEFAULT_SERVICE_CODE


def test_a_ledger_entry_may_override_the_service_code() -> None:
    """A question about a different service filed to the FSx queue is answered late."""
    entry = json.loads(json.dumps(ENTRY))
    entry["support_inquiry"]["service_code"] = "amazon-managed-prometheus"
    assert entry["support_inquiry"].get("service_code", mod.DEFAULT_SERVICE_CODE) == "amazon-managed-prometheus"


# --- the committed ledger ------------------------------------------------------


def test_every_committed_entry_can_produce_a_body() -> None:
    """A ledger row that cannot be turned into a case is a requirement nobody can meet."""
    for entry in mod._load():
        body = mod.build_body(entry)
        assert entry["claim"] in body
        assert len(body) > 200


def test_no_committed_entry_names_a_tracked_private_ref() -> None:
    """Checked here as well as in the gate, because this is the tool that writes there."""
    for entry in mod._load():
        ref = entry["support_inquiry"].get("private_ref")
        if ref:
            assert mod._gitignored(ref), f"{entry['id']}: private_ref {ref} is not gitignored"


def test_a_named_subject_service_without_a_service_code_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guessing a queue is the same act the ledger exists to prevent."""
    entry = json.loads(json.dumps(ENTRY))
    entry["subject_service"] = "Amazon Managed Service for Prometheus"
    monkeypatch.setattr(mod, "_gitignored", lambda _p: True)
    with pytest.raises(SystemExit) as excinfo:
        mod.cmd_file([entry], entry, None, confirm=True)
    assert "service_code" in str(excinfo.value)


def test_recorded_case_ids_are_read_from_the_private_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Listing must not depend on the subject line.

    The first version filtered describe_cases on a subject prefix. A ledger entry with
    its own Japanese subject then matched nothing, so the tool reported that it had
    filed no cases immediately after filing two.

    The identifiers here are deliberately not digit strings. Real case numbers are
    numeric, but the parser matches `\\S+`, so digits exercise no additional path -- and
    a digit run of that length is what the commit gate looks for when keeping case
    numbers out of a public repository. Leave these non-numeric.
    """
    ref = tmp_path / "refs.md"
    ref.write_text(
        "\n- E-001  filed 2026-09-05  case CASE-PLACEHOLDER-A\n- E-005  filed 2026-09-05  case CASE-PLACEHOLDER-B\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    entry = json.loads(json.dumps(ENTRY))
    entry["support_inquiry"]["private_ref"] = "refs.md"
    assert mod._recorded_case_ids([entry]) == [
        ("E-001", "CASE-PLACEHOLDER-A"),
        ("E-005", "CASE-PLACEHOLDER-B"),
    ]


def test_a_missing_private_ref_lists_nothing_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh project has no refs file yet; listing must still work."""
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    entry = json.loads(json.dumps(ENTRY))
    entry["support_inquiry"]["private_ref"] = "nope.md"
    assert mod._recorded_case_ids([entry]) == []
