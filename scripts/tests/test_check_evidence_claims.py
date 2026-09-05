"""Tests for scripts/check_evidence_claims.py.

The gate exists because five things went wrong in one session, and every one of them
looked like success at the time. So most of these assert that it **fails** on a
crafted input, rather than that it passes on a good one -- a gate that cannot be
shown to fail has not been shown to run.

The ones carrying the most weight:

- ``test_a_premise_on_an_inference_without_asking_the_vendor_fails`` is the whole
  point. A design resting on "AWS cannot do this" that nobody put to AWS is the
  failure being closed; if this test goes green while the rule is broken, the gate
  is decoration.
- ``test_a_snippet_is_not_a_source`` guards the second failure: a contradiction
  between two AWS pages was written down on the strength of a search-result snippet,
  and reading the page showed the opposite.
- ``test_documented_requires_a_full_read`` guards the first: a selective search
  returning no matches was treated as evidence of absence.
- ``test_a_tracked_private_ref_is_rejected`` keeps the split that stops a support
  case number reaching a public repository.
- ``test_the_detector_skips_code_fences`` is here because a detector that reads its
  own examples inside a fenced block reports the document that describes it.
"""

# Copied from the canonical checker shared by every project.
# canonical: ~/.kiro/hooks/scripts/evidence_claims_test.py  sha256:04218108af7fccfe
# Edit the canonical copy, then re-run the installer. Editing this copy alone
# means one project's gate quietly differs from the rest.

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_evidence_claims.py"


def _load_module() -> ModuleType:
    """Import the checker by path, since scripts/ is not a package.

    Returns:
        The imported ``check_evidence_claims`` module.
    """
    spec = importlib.util.spec_from_file_location("check_evidence_claims", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

#: An entry that is valid in every respect, for tests that break exactly one field.
GOOD_ENTRY: dict = {
    "id": "E-900",
    "claim": "AWS does not expose request metrics for this thing.",
    "subject": "AWS",
    "tier": "documented",
    "premise": True,
    "sources": [
        {
            "url": "https://docs.aws.amazon.com/example.html",
            "read": "full",
            "retrieved": "2026-09-05",
            "says": "Enumerates the metrics and this is not among them.",
        }
    ],
    "observation": "",
    "support_inquiry": {"status": "not-needed", "topic": "documented directly"},
    "feature_request": {"status": "not-applicable"},
    "appears_in": ["AGENTS.md"],
}


def _entry(**overrides: object) -> dict:
    """A copy of the good entry with fields replaced.

    Args:
        **overrides: Fields to replace.

    Returns:
        The modified entry.
    """
    entry = copy.deepcopy(GOOD_ENTRY)
    entry.update(overrides)
    return entry


# --- the ledger rules ----------------------------------------------------------


def test_the_good_entry_passes() -> None:
    """The baseline case, so a failure elsewhere means the rule and not the fixture."""
    assert mod.check_ledger([_entry()]) == []


def test_a_premise_on_an_inference_without_asking_the_vendor_fails() -> None:
    """The rule the gate exists for."""
    entry = _entry(
        tier="hypothesis",
        premise=True,
        support_inquiry={
            "status": "required",
            "topic": "whether it exists",
            "private_ref": ".private/support-case-refs.md",
        },
    )
    problems = mod.check_ledger([entry])
    assert any("the vendor has not been asked" in p for p in problems)


def test_the_same_inference_passes_once_the_vendor_has_been_asked() -> None:
    """Asking is what clears it -- not lowering the tier or editing the wording."""
    entry = _entry(
        tier="hypothesis",
        premise=True,
        support_inquiry={
            "status": "filed",
            "topic": "whether it exists",
            "private_ref": ".private/support-case-refs.md",
        },
    )
    assert mod.check_ledger([entry]) == []


def test_an_inference_that_is_not_a_premise_is_allowed() -> None:
    """Speculation is fine as long as nothing is built on it."""
    entry = _entry(tier="hypothesis", premise=False)
    assert mod.check_ledger([entry]) == []


def test_a_snippet_is_not_a_source() -> None:
    """A search result quoted without opening the page produced a false contradiction."""
    entry = _entry(sources=[{"url": "https://example.com/x", "read": "snippet", "retrieved": "2026-09-05"}])
    problems = mod.check_ledger([entry])
    assert any("snippet is not a source" in p for p in problems)


def test_documented_requires_a_full_read() -> None:
    """A selective search returning no matches is not evidence of absence."""
    entry = _entry(
        tier="documented",
        sources=[{"url": "https://example.com/x", "read": "selective", "retrieved": "2026-09-05"}],
    )
    problems = mod.check_ledger([entry])
    assert any("no source was read in full" in p for p in problems)


def test_a_source_without_a_retrieval_date_fails() -> None:
    """Vendor documentation changes; a citation without a date cannot be re-checked."""
    entry = _entry(sources=[{"url": "https://example.com/x", "read": "full"}])
    problems = mod.check_ledger([entry])
    assert any("`retrieved`" in p for p in problems)


def test_verified_requires_an_observation() -> None:
    """Claiming a measurement without recording one is the shape of an unfalsifiable claim."""
    entry = _entry(tier="verified", observation="")
    problems = mod.check_ledger([entry])
    assert any("no `observation`" in p for p in problems)


def test_a_tracked_private_ref_is_rejected() -> None:
    """The case number has to land somewhere git ignores."""
    entry = _entry(
        support_inquiry={"status": "filed", "topic": "x", "private_ref": "AGENTS.md"},
    )
    problems = mod.check_ledger([entry])
    assert any("does not\n" in p or "does not ignore" in p for p in problems)


def test_an_answered_inquiry_with_no_feature_request_fails() -> None:
    """Being told "no" and filing nothing is the fifth failure this closes."""
    entry = _entry(
        support_inquiry={
            "status": "answered",
            "topic": "x",
            "private_ref": ".private/support-case-refs.md",
        },
        feature_request={"status": "not-yet"},
    )
    problems = mod.check_ledger([entry])
    assert any("no feature request was raised" in p for p in problems)


def test_appears_in_must_resolve() -> None:
    """A pointer to nothing leaves the claim unreadable."""
    entry = _entry(appears_in=["docs/does-not-exist-anywhere.md"])
    problems = mod.check_ledger([entry])
    assert any("does not exist" in p for p in problems)


def test_duplicate_ids_fail() -> None:
    """Two entries with one id would answer for each other."""
    problems = mod.check_ledger([_entry(), _entry()])
    assert any("duplicate id" in p for p in problems)


def test_missing_required_fields_fail() -> None:
    """An entry without a claim is a row that satisfies the reference and says nothing."""
    entry = _entry()
    del entry["claim"]
    problems = mod.check_ledger([entry])
    assert any("missing required field" in p for p in problems)


@pytest.mark.parametrize("tier", ["settled", "probably", ""])
def test_an_invented_tier_fails(tier: str) -> None:
    """The vocabulary is fixed so that "probably documented" cannot be a tier.

    Args:
        tier: A value outside the allowed set.
    """
    problems = mod.check_ledger([_entry(tier=tier)])
    assert problems


# --- the document scan ---------------------------------------------------------


def _write(tmp_path: Path, name: str, body: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Write a markdown file inside a temporary root the scanner will read.

    Args:
        tmp_path: pytest temporary directory.
        name: File name to create.
        body: File contents.
        monkeypatch: Fixture used to repoint the module's ROOT.

    Returns:
        The name, which is also the repository-relative path under the fake root.
    """
    (tmp_path / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return name


def test_an_unattributed_claim_is_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The detector fires on prose asserting a vendor cannot do something."""
    name = _write(tmp_path, "a.md", "AWS does not support this metric.\n", monkeypatch)
    found = mod.scan([name])
    assert found[name][0][0] == 1


def test_a_ledger_reference_suppresses_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attaching evidence is how a claim is allowed to stay."""
    name = _write(tmp_path, "b.md", "AWS does not support this metric [E-001].\n", monkeypatch)
    assert mod.scan([name]) == {}


def test_a_reference_on_the_previous_line_suppresses_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tables and bullet lists put the marker one line up; that has to count."""
    name = _write(tmp_path, "c.md", "See [E-001].\nAWS does not support this metric.\n", monkeypatch)
    assert mod.scan([name]) == {}


def test_an_explicit_allow_suppresses_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deliberate speculation is permitted when it says so and gives a reason."""
    body = "AWS does not support this metric. <!-- allow:unverified: speculative aside -->\n"
    name = _write(tmp_path, "d.md", body, monkeypatch)
    assert mod.scan([name]) == {}


def test_a_not_a_claim_allow_suppresses_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prose that quotes a claim without making one is permitted, with a reason.

    A document explaining this gate trips it on the example sentence it exists to
    quote. `evidence-discipline.md` did, on its own opening line. The alternative was
    rewording the example to dodge the pattern, which damages the document to suit the
    tool.
    """
    body = '"AWS does not support X" is a claim. <!-- allow:not-a-claim: quotes the shape -->\n'
    name = _write(tmp_path, "d2.md", body, monkeypatch)
    assert mod.scan([name]) == {}


def test_a_not_a_claim_allow_without_a_reason_does_not_suppress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare marker is not an explanation, so it must not silence the finding.

    Same requirement as `allow:unverified`: the reason is what lets a reader tell an
    example from an evasion, and a marker that works empty invites the empty form.
    """
    body = "AWS does not support this metric. <!-- allow:not-a-claim: -->\n"
    name = _write(tmp_path, "d3.md", body, monkeypatch)
    assert name in mod.scan([name])


def test_the_two_allow_markers_are_not_interchangeable() -> None:
    """Each marker matches only its own spelling.

    They say different things -- "deliberately speculative" against "not a claim at
    all" -- so one standing in for the other would file a claim under the wrong reason.
    """
    speculative = "x <!-- allow:unverified: reason -->"
    not_a_claim = "x <!-- allow:not-a-claim: reason -->"
    assert mod.ALLOW.search(speculative) and not mod.ALLOW_NOT_A_CLAIM.search(speculative)
    assert mod.ALLOW_NOT_A_CLAIM.search(not_a_claim) and not mod.ALLOW.search(not_a_claim)


def test_prose_without_a_vendor_is_not_swept_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ "This panel cannot be opened twice" is not a claim about a vendor."""
    name = _write(tmp_path, "e.md", "この画面は二重に開けません。\n", monkeypatch)
    assert mod.scan([name]) == {}


def test_the_detector_skips_code_fences(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A detector that reads its own examples reports the document describing it."""
    body = "```\nAWS does not support this metric.\n```\n"
    name = _write(tmp_path, "f.md", body, monkeypatch)
    assert mod.scan([name]) == {}


def test_japanese_phrasing_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The documents are written in Japanese first, so the patterns have to be."""
    name = _write(tmp_path, "g.md", "FSx for ONTAP は S3 のメトリクスを提供していない。\n", monkeypatch)
    assert name in mod.scan([name])


def test_the_baseline_accepts_a_pre_existing_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ratchet: what was already there does not block work on something else."""
    name = _write(tmp_path, "h.md", "AWS does not support this metric.\n", monkeypatch)
    found = mod.scan([name])
    fingerprint = found[name][0][1]
    assert mod.check_scan(found, {name: [fingerprint]}) == []


def test_a_stale_baseline_entry_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fingerprint kept for text that has changed is a hole that reopens later."""
    name = _write(tmp_path, "i.md", "AWS does not support this metric.\n", monkeypatch)
    found = mod.scan([name])
    problems = mod.check_scan(found, {name: [found[name][0][1], "deadbeef01"]})
    assert any("no longer" in p for p in problems)


def test_whitespace_changes_do_not_break_the_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reflowing a paragraph must not turn into a wall of new failures."""
    first = _write(tmp_path, "j.md", "AWS does not support this metric.\n", monkeypatch)
    before = mod.scan([first])[first][0][1]
    second = _write(tmp_path, "k.md", "   AWS  does not support this metric.   \n", monkeypatch)
    after = mod.scan([second])[second][0][1]
    assert before == after


# --- the ledger that ships -----------------------------------------------------


def test_the_committed_ledger_is_structurally_sound() -> None:
    """The real ledger's invariants, not a fixture.

    Structure only. Whether an outstanding inference has been put to the vendor is a
    policy rule, and it is expected to be red while that work is outstanding -- the
    checker reports it in ``make drift``. Asserting it here would mean editing a test
    every time an inquiry is filed, and worse, it would tempt someone to clear the red
    by editing the ledger instead of asking.
    """
    assert mod.check_ledger(mod.load_ledger(), policy=False) == []


def test_the_policy_rule_reaches_the_committed_ledger() -> None:
    """The policy rule must actually be evaluated against the real entries.

    Without this, ``policy=False`` in the test above could hide a checker that never
    applies the rule at all -- the shape of gate that reports success without running.
    """
    strict = mod.check_ledger(mod.load_ledger(), policy=True)
    structural = mod.check_ledger(mod.load_ledger(), policy=False)
    premises = [c for c in mod.load_ledger() if c["premise"] and c["tier"] in mod.WEAK_TIERS]
    unasked = [c for c in premises if c["support_inquiry"]["status"] == "required"]
    assert len(strict) - len(structural) == len(unasked)


def test_the_committed_ledger_parses_as_json() -> None:
    """A ledger that cannot be read reports no claims, which looks like having none.

    Only the shape is asserted, not that anything is in it. A freshly adopted project
    starts with zero claims and must still pass -- an earlier version required a
    non-empty list and failed the moment the gate was installed anywhere else.
    """
    data = json.loads(mod.LEDGER.read_text(encoding="utf-8"))
    assert isinstance(data["claims"], list)


def test_limiting_the_scan_does_not_report_other_files_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the checker on one path used to fail every time.

    The staleness half compared the whole baseline against a scan of one file, so every
    entry in every other file looked like text that had changed. Found while installing
    the gate into a fresh repository, where checking a single new document reported the
    untouched README.
    """
    name = _write(tmp_path, "one.md", "AWS does not support this metric.\n", monkeypatch)
    found = mod.scan([name])
    baseline = {name: [found[name][0][1]], "other.md": ["deadbeef01"]}
    assert mod.check_scan(found, baseline, scanned={name}) == []
    # Without the restriction the untouched file is still reported, which is what the
    # full run must keep doing.
    assert mod.check_scan(found, baseline) != []


#: Phrasings that must be detected. The vocabulary is the part of this gate that keeps
#: going quiet -- three gaps were found by a test rather than by rereading the pattern --
#: so every one that gets missed in future belongs here rather than only in the regex.
ABSENCE_CORPUS = [
    "AWS does not support this metric.",
    "AWS does not expose request-level metrics.",
    "Amazon CloudWatch does not publish anything for it.",
    "The FSx API doesn't provide that field.",
    "ONTAP cannot return it through REST.",
    "This is not supported by Harvest.",
    "The metric is not available in the AWS/FSx namespace.",
    "There is no way to shorten the retention in Amazon S3.",
    "FSx for ONTAP は S3 のメトリクスを提供していない。",
    "FSx for ONTAP は S3 のメトリクスを提供されていない扱いになる。",
    "ONTAP はこのカウンタを公開していない。",
    "Amazon Managed Grafana は匿名アクセスに未対応。",
    "AWS のドキュメントからは取得できない。",
    "CloudWatch では監視できません。",
    "Amazon S3 側に相当する機構は存在しない。",
]


@pytest.mark.parametrize("line", ABSENCE_CORPUS)
def test_every_phrasing_in_the_corpus_is_detected(line: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A detector is as narrow as its list, and the list is not self-evident.

    Args:
        line: A sentence asserting a vendor cannot do something.
    """
    name = _write(tmp_path, "corpus.md", line + "\n", monkeypatch)
    assert name in mod.scan([name]), f"not detected: {line}"
