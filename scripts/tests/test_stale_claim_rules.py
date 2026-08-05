"""Tests for the stale-claim rules shared by the two drift checks.

The rules had no tests, and that is how the drift they exist to catch reached
readers. Two published Part 2 posts told people that block expiry and multi-SVM
fan-out were still theirs to build, for a month after both shipped, while
`check_portal_drift.py` reported PASS the whole time. The rule patterns had been
written against the phrasing used in `docs/`, and the articles said the same
thing in different words.

So the cases below are the sentences that actually shipped, and the corrected
sentences that replaced them. A rule that catches the first set and leaves the
second alone is the whole requirement; a rule that fires on the corrected text
would push someone back towards the wording that was wrong.

These tests need no network: the network-facing script is exercised through its
extractor, with HTML fixtures shaped like the two publishing platforms.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift():
    return _load("check_portal_drift")


@pytest.fixture(scope="module")
def published():
    _load("check_portal_drift")
    return _load("check_published_articles")


# Verbatim from the two posts as they stood before the correction. The EN entries
# keep the ~80 column hard wrap, because that wrap is exactly what a line-only
# matcher misses: neither line contains the claim on its own.
SHIPPED_STALE = {
    "en-prose-wrapped": (
        "Writing this section is what exposed the gap worth fixing. A block removes a\n"
        "principal's data access across the whole SVM, and the portal has no TTL, so\n"
        "nothing lifts it but a person. The first version executed on a single click, with\n"
        "no confirmation and no `confirm` parameter in the payload."
    ),
    "en-row-ttl": (
        "| Not leave a false-positive block in place indefinitely | TTL auto-unblock (EventBridge Scheduler) |"
    ),
    "en-row-fanout": ("| Apply the same block across several SVMs at once | A multi-SVM fan-out |"),
    "ja-prose": (
        "この整理をして初めて、直すべき穴が見えました。"
        "ブロックは対象のデータアクセスを SVM 全体で止め、しかもポータルには TTL がないので、"
        "人が解除するまで残ります。初版はそれをワンクリックで実行していました。"
    ),
    "ja-row-ttl": "| 誤検知のブロックを放置しない | TTL 自動解除（EventBridge Scheduler） |",
    "ja-row-fanout": "| 複数 SVM に同じブロックを一斉適用する | マルチ SVM へのファンアウト |",
    # The phrasings the rules already knew, kept so widening them did not drop any.
    "doc-en-original": "Containment blocks do not expire.",
    "doc-ja-original": "ブロックは自動では失効しません。",
}

# The text that replaced it. Tense carries the meaning here: the old behaviour
# described in the past is accurate history, the same words in the present are
# the false claim. A rule that cannot tell those apart is worse than no rule.
CORRECTED = {
    "en-prose-wrapped": (
        "Writing this section is what exposed the gap worth fixing. A block removes a\n"
        "principal's data access across the whole SVM. The first version executed on a\n"
        "single click, with no confirmation and no `confirm` parameter in the payload —\n"
        "the only guards were the Cognito group and a protected-accounts list. At the time\n"
        "there was also no expiry, so a block stayed until a person lifted it."
    ),
    "en-row-ttl": (
        "| Block expiry and automatic lifting (24 hours by default) | The block ledger (DynamoDB) being reachable |"
    ),
    "en-row-fanout": ("| Apply the same block across several SVMs (`svms` or `allSvms`) | — |"),
    "en-lead": (
        "Every one of these **starts when a person clicks**. Nothing in the portal\n"
        "contains a threat unattended — expiry is the one exception, and it only ever\n"
        "works in the direction of ending a lockout."
    ),
    "ja-prose": (
        "ブロックは対象のデータアクセスを SVM 全体で止めます。"
        "初版はそれをワンクリックで実行していました。"
        "しかも当時は有効期限がなく、人が解除するまで残り続けました。"
    ),
    "ja-row-ttl": "| ブロックの有効期限と自動解除（既定 24 時間） | ブロック台帳（DynamoDB）に到達できること |",
    "ja-row-fanout": "| 複数 SVM への一斉適用（`svms` 指定または `allSvms`） | — |",
    "ja-lead": (
        "いずれも **人が押して初めて動きます**。無人で封じ込める仕組みはポータルには"
        "入っていません（有効期限による自動解除は例外で、これは締め出しを終わらせる"
        "方向にのみ働きます）。"
    ),
    # True statements that share vocabulary with the false ones. The retention
    # policy sentence is the reason the expiry rule cannot simply match "TTL".
    "unrelated-ttl": "Set a retention policy (TTL) and archive old records to S3 Glacier.",
    "unrelated-ttl-ja": "保持ポリシー（TTL）を設定し、古いレコードを S3 Glacier にアーカイブします。",
    "read-only-is-fine": ("Regular users can view ARP status (read-only) but cannot execute containment actions."),
}


def test_rules_are_active(drift):
    """Both rules must be live, or the cases below prove nothing."""
    names = {rule["name"] for rule in drift.active_contradictions()}
    assert names == {"block-expiry", "multi-svm-fanout"}, (
        "a rule stopped applying because its disproving marker vanished from the "
        "handler; confirm the behaviour still ships before removing the rule"
    )


@pytest.mark.parametrize("case", sorted(SHIPPED_STALE))
def test_catches_what_actually_shipped(drift, case):
    assert drift.scan_text(SHIPPED_STALE[case]), f"{case}: this exact wording was live for a month and the check passed"


@pytest.mark.parametrize("case", sorted(CORRECTED))
def test_leaves_the_corrected_wording_alone(drift, case):
    hits = drift.scan_text(CORRECTED[case])
    assert not hits, f"{case}: fires on corrected text -> {[h[2] for h in hits]}"


# A claim split by the hard wrap so that no single line contains it. Any
# multi-word pattern can land this way in prose wrapped at a fixed column, and a
# line-only matcher reports nothing at all.
WRAPPED_ACROSS_LINES = {
    "en": "Containment blocks do not\nexpire, so a false positive stays until someone notices.",
    "ja": "この構成では TTL も\nスケジュール解除もないため、解除は手作業になります。",
}


def test_unwrap_adds_no_space_between_two_wide_characters(drift):
    """A Japanese line break takes no space, and inserting one hides the claim.

    Joining wrapped lines with a space is correct for English and wrong for
    Japanese: "TTL も" + "スケジュール解除もない" becomes a string with a space
    that exists in no document and matches no pattern. This was a real bug in the
    first version of the paragraph pass.
    """
    assert drift.unwrap(["TTL も", "スケジュール解除もないため"]) == "TTL もスケジュール解除もないため"
    assert drift.unwrap(["blocks do not", "expire at all"]) == "blocks do not expire at all"
    # A wide character next to an ASCII one still needs the space, or the English
    # word fuses into the Japanese clause.
    assert drift.unwrap(["設定は EventBridge", "Scheduler で行います"]) == ("設定は EventBridge Scheduler で行います")
    # Table rows begin and end with a pipe, so they stay separated.
    assert drift.unwrap(["| あ | い |", "| う | え |"]) == "| あ | い | | う | え |"


@pytest.mark.parametrize("case", sorted(WRAPPED_ACROSS_LINES))
def test_claim_split_by_the_wrap_is_still_found(drift, case):
    text = WRAPPED_ACROSS_LINES[case]
    rules = drift.active_contradictions()

    # The fixture only tests the paragraph pass while it really is split. If a
    # single line ever matches on its own, this test silently stops meaning
    # anything, so assert the precondition rather than trusting it.
    assert not any(any(rule["claim"].search(line) for rule in rules) for line in text.split("\n")), (
        "fixture no longer straddles the wrap, so it stops testing the paragraph pass"
    )

    hits = drift.scan_text(text)
    assert hits, "a claim broken across two lines went unreported"
    assert hits[0][1] == 1, "a wrapped hit should point at the start of its paragraph"


def test_wrapped_prose_that_shipped_is_reported_with_an_exact_line(drift):
    """The real Part 2 wording happens to leave one alternative intact per line."""
    text = SHIPPED_STALE["en-prose-wrapped"]
    hits = drift.scan_text(text)
    assert hits
    assert hits[0][1] == 2, "the claim sits on line 2; the location should say so"


def test_a_single_line_claim_is_reported_once(drift):
    """Line and paragraph passes must not both report the same hit."""
    hits = drift.scan_text(SHIPPED_STALE["en-row-fanout"])
    assert len(hits) == 1, hits


def test_line_numbers_point_at_the_claim(drift):
    text = "intro\n\nfiller line\n| Apply the same block across several SVMs at once | A multi-SVM fan-out |\n"
    (_, number, _), *rest = drift.scan_text(text)
    assert not rest
    assert number == 4


def test_exempt_file_marker_is_honoured_for_files(drift, tmp_path, monkeypatch):
    """A correction sheet has to quote the stale text to be usable as one."""
    doc = tmp_path / "docs" / "en"
    doc.mkdir(parents=True)
    stale = SHIPPED_STALE["en-row-ttl"]

    (doc / "quoting.md").write_text(f"<!-- drift-exempt-file: quotes the pre-correction wording -->\n\n{stale}\n")
    (doc / "asserting.md").write_text(f"# Guide\n\n{stale}\n")

    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "DOC_GLOBS", ["docs/en/*.md"])
    locations = {finding.location for finding in drift.check_doc_contradictions()}

    assert any("asserting.md" in location for location in locations)
    assert not any("quoting.md" in location for location in locations)


def test_exempt_line_marker_is_honoured_for_one_line(drift, tmp_path, monkeypatch):
    doc = tmp_path / "docs" / "en"
    doc.mkdir(parents=True)
    (doc / "mixed.md").write_text(
        "# Guide\n\n"
        "Blocks do not expire. <!-- drift-exempt: quoting the old release notes -->\n\n"
        "Containment blocks do not expire.\n"
    )
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "DOC_GLOBS", ["docs/en/*.md"])
    findings = drift.check_doc_contradictions()
    assert [finding.location for finding in findings] == ["docs/en/mixed.md:5"]


def test_repository_is_clean_under_the_widened_rules(drift):
    """Guards the fix: two committed guides carried the stale rows until now."""
    findings = drift.check_doc_contradictions()
    assert not findings, [f"{f.location}: {f.detail}" for f in findings]


# --- the network-facing script, exercised without the network -----------------

DEVTO_BODY_HTML = (
    "<p>A block removes a principal's data access across the whole SVM, and the"
    "<br>\nportal has no TTL, so<br>\nnothing lifts it but a person.</p>"
    "<table><tbody><tr><td>Apply the same block across several SVMs at once</td>"
    "<td>A multi-SVM fan-out</td></tr></tbody></table>"
)

HATENA_PAGE_HTML = (
    "<html><body>"
    "<div class='sidebar'><p>ブロックは自動では失効しません</p></div>"
    "<div class='entry-content'>"
    "<p>ポータルには TTL がないので、人が解除するまで残ります。</p>"
    "<div class='inner'><p>入れ子の段落</p></div>"
    "</div>"
    "<div class='comment-box'><p>マルチ SVM へのファンアウト</p></div>"
    "</body></html>"
)


def test_extractor_takes_only_the_article_body(published):
    text = published._TextExtractor(container_class="entry-content")
    text.feed(HATENA_PAGE_HTML)
    body = text.text
    assert "ポータルには TTL がないので" in body
    assert "入れ子の段落" in body, "closing a nested div ended the capture too early"
    assert "ブロックは自動では失効しません" not in body, "captured the sidebar"
    assert "マルチ SVM へのファンアウト" not in body, (
        "captured the comments; a false claim in someone else's comment is not ours"
    )


def test_extractor_preserves_the_br_wrap_dev_to_renders(published):
    parser = published._TextExtractor()
    parser.feed(DEVTO_BODY_HTML)
    body = parser.text
    assert "\n" in body, "dropped the <br> that dev.to renders a markdown newline as"
    assert not any("has no TTL, so nothing lifts it" in line for line in body.split("\n"))
    assert drift_hits(published, body), "claim lost between extraction and scanning"


def drift_hits(published, text):
    module = sys.modules["check_portal_drift"]
    return module.scan_text(text, module.active_contradictions())


def test_table_cells_stay_on_one_line(published):
    """A row split across lines would hide a claim that spans both cells."""
    parser = published._TextExtractor()
    parser.feed(DEVTO_BODY_HTML)
    rows = [line for line in parser.text.split("\n") if "multi-SVM fan-out" in line]
    assert rows and "several SVMs at once" in rows[0], parser.text


def test_hatena_fetch_is_wired_to_the_entry_content_container(published, monkeypatch):
    """Covers the wiring, not just the extractor: which kind picks which container."""
    monkeypatch.setattr(published, "_fetch", lambda url: HATENA_PAGE_HTML)
    text = published.article_text("https://example.test/entry/x", "hatena")
    assert "ポータルには TTL がないので" in text
    assert "ブロックは自動では失効しません" not in text, "sidebar reached the scanner"
    assert "マルチ SVM へのファンアウト" not in text, "comments reached the scanner"


def test_devto_fetch_reads_the_api_rather_than_the_page(published, monkeypatch):
    requested: list[str] = []

    def fake_fetch(url: str) -> str:
        requested.append(url)
        return json.dumps({"body_html": DEVTO_BODY_HTML})

    monkeypatch.setattr(published, "_fetch", fake_fetch)
    text = published.article_text("https://dev.to/aws-builders/some-slug", "devto")

    assert requested == ["https://dev.to/api/articles/aws-builders/some-slug"]
    assert "A multi-SVM fan-out" in text


@pytest.mark.parametrize("payload", ['{"body_html": ""}', "{}"])
def test_empty_body_is_an_error_not_a_pass(published, monkeypatch, payload):
    """An empty body would make every claim rule trivially pass."""
    monkeypatch.setattr(published, "_fetch", lambda url: payload)
    with pytest.raises(RuntimeError):
        published.article_text("https://dev.to/aws-builders/some-slug", "devto")


def test_manifest_covers_both_platforms_and_all_parts(published):
    kinds = {article["kind"] for article in published.ARTICLES}
    assert kinds == {"devto", "hatena"}
    assert len(published.ARTICLES) == 6, "the series is three parts in two languages"
    assert len({article["url"] for article in published.ARTICLES}) == 6


def test_no_exempt_marker_escape_hatch_for_published_text(published):
    """A live article cannot opt out of being checked."""
    source = (SCRIPTS / "check_published_articles.py").read_text()
    assert "EXEMPT_FILE" not in source
    assert "EXEMPT_LINE" not in source
