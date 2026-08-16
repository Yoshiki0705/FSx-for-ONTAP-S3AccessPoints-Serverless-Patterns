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
    """Every rule must be live, or the cases below prove nothing.

    Pinned to the exact set rather than a subset: a rule that quietly stops
    applying is the failure this whole file exists to prevent, and a
    `>=` assertion would not notice one leaving.
    """
    names = {rule["name"] for rule in drift.active_contradictions()}
    assert names == {"block-expiry", "multi-svm-fanout", "system-manager-vpn"}, (
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


# --------------------------------------------------------------------------
# Count claims
#
# The phrasing rules above cannot reach these. "4 groups × 13 sections" is not a
# false phrasing — it was the true number when it was written. Three documents
# and two published articles disagreed with the sidebar at once, in four
# languages, and every one of them read as correct prose.
# --------------------------------------------------------------------------

# The number as each locale actually writes it, paired with what the surrounding
# text looks like. Taken from the eight README files and the two published posts,
# so a pattern that only understands the English form fails here rather than in
# production.
SECTION_PHRASINGS = [
    "4 groups × 17 sections. Same sidebar pattern as Google Drive and Box.",
    "4 グループ × 17 セクション。Google Drive や Box と同じサイドバーパターンです。",
    "## Portal UI — Sidebar Layout (17 Sections)",
    "## ポータル UI — サイドバーレイアウト（17 セクション）",
    "## Portal-UI — Seitenleisten-Layout (17 Bereiche)",
    "## UI del Portal — Diseño de la barra lateral (17 secciones)",
    "## Interface du portail — Disposition de la barre latérale (17 sections)",
    "## 포털 UI — 사이드바 레이아웃 (17개 섹션)",
    "## 门户 UI — 侧边栏布局（17 个部分）",
    "## 入口 UI — 側邊欄佈局（17 個部分）",
    "サイドバーナビゲーション（4 グループ × 17 セクション）で構成されています。",
]


def _sections_rule(drift):
    return next(c for c in drift.COUNT_CLAIMS if c["name"] == "sidebar-sections")


@pytest.mark.parametrize("line", SECTION_PHRASINGS)
def test_every_locale_phrasing_is_understood(drift, line):
    """The number is found in all eight locales, not just English.

    A pattern that reads "17 sections" and not "17개 섹션" would report PASS on
    seven of the eight READMEs while they said 16, which is the same silence as
    having no check.
    """
    rule = _sections_rule(drift)
    match = rule["pattern"].search(line)
    assert match, line
    assert next(g for g in match.groups() if g) == "17"


@pytest.mark.parametrize("line", SECTION_PHRASINGS)
def test_a_stale_number_is_reported_in_every_locale(drift, line, tmp_path, monkeypatch):
    stale = line.replace("17", "13")
    doc = tmp_path / "docs" / "ja"
    doc.mkdir(parents=True)
    (doc / "example.md").write_text(stale, encoding="utf-8")
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "COUNT_GLOBS", ["docs/ja/*.md"])
    monkeypatch.setattr(drift, "COUNT_CLAIMS", [{**_sections_rule(drift), "count": lambda: 17}])

    findings = drift.check_count_claims()

    assert len(findings) == 1, findings
    assert "says 13" in findings[0].detail
    assert "has 17" in findings[0].detail


def test_the_count_comes_from_the_sidebar_not_a_constant(drift):
    """The expected number is read from `NAV_ITEMS`, so it cannot itself go stale.

    A hardcoded 17 here would turn the next section anyone adds into a false
    failure, and the fix for a false failure is usually to delete the check.
    """
    counted = _sections_rule(drift)["count"]()
    nav = (drift.PORTAL / "src" / "App.tsx").read_text()
    assert counted == nav.count('", icon: "')
    assert counted >= 17


def test_a_zero_count_is_reported_rather_than_passing(drift, monkeypatch):
    """If the reader stops matching the implementation, say so.

    Counting zero means the pattern that reads `App.tsx` has been outrun by a
    refactor. Comparing every document against zero would flag all of them; not
    comparing at all would report PASS forever. Neither is a useful answer, so
    the broken reader is what gets reported.
    """
    monkeypatch.setattr(drift, "COUNT_CLAIMS", [{**_sections_rule(drift), "count": lambda: 0}])

    findings = drift.check_count_claims()

    assert len(findings) == 1
    assert "counted zero" in findings[0].detail


def test_exempt_markers_are_honoured_in_the_repository(drift, tmp_path, monkeypatch):
    """A correction sheet quotes the stale number on purpose."""
    doc = tmp_path / "docs" / "ja"
    doc.mkdir(parents=True)
    (doc / "corrections.md").write_text(
        "<!-- drift-exempt-file: quotes the before text for search-and-replace -->\n4 グループ × 13 セクション\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "COUNT_GLOBS", ["docs/ja/*.md"])
    monkeypatch.setattr(drift, "COUNT_CLAIMS", [{**_sections_rule(drift), "count": lambda: 17}])

    assert drift.check_count_claims() == []


def test_a_published_article_gets_no_exemption(published, drift):
    """The same marker must not silence a live article.

    A file may quote a false number to correct it. An article asserting one to
    its readers is a finding whatever the intent, so `count_findings` takes text
    and never sees a marker.
    """
    text = "<!-- drift-exempt-file: does not apply here -->\n4 groups × 13 sections. Same pattern.\n"
    findings = published.count_findings(text, {"label": "Part 1 (EN)", "url": "https://example.com"})
    assert len(findings) == 1
    assert "says 13" in findings[0]


def test_the_published_checker_shares_the_repository_table(published, drift):
    """One table, both checks.

    The rules were copied once before and the copies diverged, which is how two
    articles kept a claim the repository had already corrected.

    Asserted against the source rather than by object identity: the fixtures here
    load each script as a fresh module, so the two `COUNT_CLAIMS` names refer to
    equal-but-distinct lists no matter how the import is written. Identity would
    fail on a correct file, which is worse than not testing it.
    """
    source = (SCRIPTS / "check_published_articles.py").read_text()
    assert "COUNT_CLAIMS," in source, "the table must be imported"
    assert "COUNT_CLAIMS = " not in source, "a second copy would drift from the first"
    assert [c["name"] for c in published.COUNT_CLAIMS] == [c["name"] for c in drift.COUNT_CLAIMS]


def test_a_correct_published_number_is_left_alone(published):
    text = "4 groups × 17 sections. Same sidebar pattern as Google Drive and Box."
    assert published.count_findings(text, {"label": "Part 1 (EN)", "url": "https://x"}) == []


# The endpoint count deliberately has no rule. These are the sentences that made
# one unworkable: each is correct, and each sits a number next to the word
# "endpoint". If someone adds that rule later, this test tells them what it has
# to survive.
ENDPOINT_SENTENCES_THAT_ARE_CORRECT = [
    "| Azure AD (Entra ID) | OIDC | Documented | Use v2.0 endpoint |",
    "S3 AP にはパブリック S3 エンドポイント経由でアクセスします。",
    "The file-browsing Lambda runs OUTSIDE VPC and reaches 3 endpoints.",
]


@pytest.mark.parametrize("line", ENDPOINT_SENTENCES_THAT_ARE_CORRECT)
def test_no_rule_claims_the_endpoint_count(drift, line):
    for claim in drift.COUNT_CLAIMS:
        assert not claim["pattern"].search(line), (claim["name"], line)


# --------------------------------------------------------------------------
# Pattern and test-file counts
#
# Five of these were stale at once and had been for months: FlexCache said 7
# with 10 directories on disk, edge said 1 with 2, five of the six operations
# patterns were annotated "(planned)" while all six were built, and the coverage
# line said 126 test files with 229 present. Nobody wrote anything false — the
# repository grew.
#
# The reason no check caught it is duller than the drift: `AGENTS.md` was not in
# `COUNT_GLOBS`, so the file where every one of these numbers lives was the one
# file the count check never opened.
# --------------------------------------------------------------------------

# Each count is written twice in the same file, in opposite orders: the summary
# sentence leads with the number, the directory tree trails it in parentheses.
# Both forms are kept here because matching only the parenthesised one left the
# summary line — the line most readers actually read — unchecked.
COUNT_PHRASINGS = {
    "flexcache-patterns": (
        10,
        "**10 FlexCache/FlexClone patterns**",
        "│   ├── flexcache/                    # FlexCache/FlexClone patterns (10)",
    ),
    "genai-patterns": (
        2,
        "**2 GenAI patterns**",
        "│   ├── genai/                        # GenAI patterns (2)",
    ),
    "event-driven-patterns": (
        2,
        "**2 event-driven patterns**",
        "│   ├── event-driven/                 # Event-driven patterns (2)",
    ),
    "edge-patterns": (
        2,
        "**2 edge delivery patterns**",
        "│   └── edge/                         # CDN/edge delivery patterns (2)",
    ),
    "operations-patterns": (
        6,
        "**6 operations optimization patterns (OPS1-OPS6)**",
        "├── operations/             # Operational optimization patterns (6, all built)",
    ),
    "pytest-files": (265, "~4,503 Python tests across 265 files", None),
    "vitest-files": (28, "~353 vitest tests across 28 files", None),
}

_COUNT_CASES = [
    pytest.param(name, line, id=f"{name}/{label}")
    for name, (_, *forms) in sorted(COUNT_PHRASINGS.items())
    for label, line in zip(("number-first", "number-last"), forms, strict=True)
    if line
]


def _claim(drift, name: str):
    return next(c for c in drift.COUNT_CLAIMS if c["name"] == name)


@pytest.mark.parametrize(("name", "line"), _COUNT_CASES)
def test_both_orders_of_a_count_are_understood(drift, name, line):
    """Number-first and number-last phrasings of the same count both match."""
    match = _claim(drift, name)["pattern"].search(line)
    assert match, line
    stated = next(g for g in match.groups() if g)
    assert int(stated) == _claim(drift, name)["count"](), (
        f"{name}: the phrasing matched but the number read from it disagrees with disk"
    )


@pytest.mark.parametrize(("name", "line"), _COUNT_CASES)
def test_a_stale_count_is_reported(drift, name, line, tmp_path, monkeypatch):
    """The value that was actually committed, made stale again, is a finding.

    The expected number is pinned before `ROOT` moves, because the counters read
    the repository through it — pointing `ROOT` at an empty directory would make
    every counter return zero and report a broken reader instead of a stale
    claim, which is a different finding and would leave this untested.
    """
    expected = _claim(drift, name)["count"]()
    stale = line.replace(str(expected), str(expected + 3), 1)
    assert stale != line, "the fixture no longer contains the number it claims to"

    (tmp_path / "AGENTS.md").write_text(stale, encoding="utf-8")
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    monkeypatch.setattr(drift, "COUNT_GLOBS", ["AGENTS.md"])
    monkeypatch.setattr(drift, "COUNT_CLAIMS", [{**_claim(drift, name), "count": lambda n=expected: n}])

    findings = drift.check_count_claims()
    assert len(findings) == 1, findings
    assert f"says {expected + 3}" in findings[0].detail
    assert f"has {expected}" in findings[0].detail


@pytest.mark.parametrize("name", sorted(COUNT_PHRASINGS))
def test_a_category_rule_ignores_the_other_categories(drift, name):
    """Seven rules, not one.

    A single `(\\d+) patterns` rule would compare every category against
    whichever number it read first, and a single `across (\\d+) files` rule would
    hold the pytest and vitest file counts to the same total. Both would report a
    mismatch on correct prose, and the usual fix for a check that cries wolf is
    to delete it. So each subject is matched on its own name, and this pins that.
    """
    rule = _claim(drift, name)["pattern"]
    for other, (_, *forms) in COUNT_PHRASINGS.items():
        if other == name:
            continue
        for line in filter(None, forms):
            assert not rule.search(line), f"the {name} rule read a {other} sentence: {line}"


@pytest.mark.parametrize("name", sorted(COUNT_PHRASINGS))
def test_the_expected_count_is_read_from_disk(drift, name):
    """No rule may hardcode its expected number.

    A literal here would turn the next pattern anyone adds into a failure that
    is not their fault, and the usual repair for a failure that is not your
    fault is to remove the assertion. Counting the directories means adding a
    pattern updates the check by itself; only the prose then needs a human.
    """
    counted = _claim(drift, name)["count"]()
    assert counted == COUNT_PHRASINGS[name][0] or name in {"pytest-files", "vitest-files"}, (
        f"{name}: disk says {counted}, AGENTS.md says {COUNT_PHRASINGS[name][0]}"
    )
    assert counted > 0


@pytest.mark.parametrize(
    ("name", "glob"),
    [
        ("flexcache-patterns", "solutions/flexcache/*/template.yaml"),
        ("genai-patterns", "solutions/genai/*/template.yaml"),
        ("event-driven-patterns", "solutions/event-driven/*/template.yaml"),
        ("edge-patterns", "solutions/edge/*/template.yaml"),
        ("operations-patterns", "operations/*/template.yaml"),
    ],
)
def test_a_pattern_is_counted_by_its_template(drift, name, glob):
    """One deployable template is one pattern, which is what the prose counts.

    Counting directories instead would include `docs/`, and counting README
    files would miss a pattern that has no README yet.
    """
    assert _claim(drift, name)["count"]() == len(list(drift.ROOT.glob(glob)))


def test_the_test_file_counts_exclude_the_suites_that_cannot_run_here(drift):
    """`e2e/` needs deployed stacks and `load/` needs live infrastructure.

    Counting them would make the coverage line describe tests that no one can
    run from a checkout, which is the kind of number that reads as reassurance
    and is not.
    """
    counted = _claim(drift, "pytest-files")["count"]()
    tracked = [p for p in drift.tracked_files() if p.rpartition("/")[2].startswith("test_") and p.endswith(".py")]
    excluded = [path for path in tracked if {"e2e", "load"} & set(path.split("/"))]

    assert excluded, "the exclusion stopped applying to anything; confirm the suites still exist"
    assert counted == len(tracked) - len(excluded)


def test_only_committed_files_are_counted(drift):
    """A file CI cannot see must not raise the number a document has to match.

    The first version walked the working tree and counted
    `.private/test_s3ap_write.py`, which is gitignored. AGENTS.md was corrected
    to 229 to match a laptop, and CI — seeing 228 — failed. A count that differs
    between a checkout and the pipeline is not a count of anything, so the source
    of truth is what git tracks.
    """
    tracked = drift.tracked_files()
    assert tracked, "git reported nothing; the counter has no source"
    assert not [path for path in tracked if path.startswith(".private/")], (
        ".private is gitignored, so nothing under it may appear here"
    )


def test_agents_md_is_checked(drift):
    """The file every one of these numbers lives in.

    Its absence from this list is the whole reason five counts could go stale
    together without a single failure.
    """
    assert "AGENTS.md" in drift.COUNT_GLOBS


@pytest.mark.parametrize("name", sorted(COUNT_PHRASINGS))
def test_a_zero_count_is_reported_as_a_broken_reader(drift, name, monkeypatch):
    """A directory that stops matching must fail loudly, not silently pass.

    If `solutions/flexcache` is renamed, the counter returns zero. Comparing
    every document against zero would flag all of them; skipping the comparison
    would report PASS forever. Neither tells anyone what happened, so the reader
    is what gets named.
    """
    monkeypatch.setattr(drift, "COUNT_CLAIMS", [{**_claim(drift, name), "count": lambda: 0}])
    findings = drift.check_count_claims()
    assert len(findings) == 1
    assert "counted zero" in findings[0].detail


def test_the_repository_agrees_with_its_own_counts(drift):
    """Guards the fix: five of these numbers were wrong when the rules landed."""
    findings = drift.check_count_claims()
    assert not findings, [f"{f.location}: {f.detail}" for f in findings]


# --------------------------------------------------------------------------
# System Manager reachability
#
# The comparison in the published Part 2 articles and in the capability map was
# written against on-premises ONTAP, where any network that reaches the cluster
# management LIF can open the System Manager web UI. FSx for ONTAP's management
# endpoint offers SSH and the REST API; System Manager is reached only through
# the vendor SaaS, which covers FSx for ONTAP in its SaaS-connected mode alone.
# So "VPN to System Manager" described a path that does not exist, in four
# languages, for months.
#
# The hard part of this rule is what it must NOT match. "Follows System
# Manager's card navigation" and "System Manager-equivalent operations" are
# about design and familiarity, they are true, and a rule that flags them
# would be turned off within a week.
# --------------------------------------------------------------------------

# Verbatim from the repository and the two posts before the correction.
SM_SHIPPED_STALE = [
    "ONTAP System Manager は強力な Web UI ですが、アクセスするには VPN 経由で管理 LIF に接続する必要があります。",
    "ONTAP System Manager is a powerful Web UI, but accessing it requires a VPN connection to the",
    "| ARP 脅威の確認と封じ込め | System Manager にVPN接続 → Security パネル → 手動ブロック |",
    "| Check ARP threats and contain | VPN to System Manager → Security panel → manual block |",
    "| **ランサムウェア対策の可視化** | ONTAP ARP は動作するが確認に System Manager + VPN |",
    "| **Ransomware visibility** | ONTAP ARP runs but checking needs System Manager + VPN |",
    "Node replacement, ONTAP upgrades and disk/shelf management remain with System Manager",
    "ノードの交換、ONTAP のアップグレード、ディスク・シェルフの管理は System Manager と ONTAP CLI の担当範囲です",
    "the moment you wanted to know something about the storage layer, you had to go back to ONTAP System Manager or the CLI.",
    "ストレージ側の状態を知りたくなったら ONTAP System Manager や CLI に戻る必要がありました",
    "Storage administrators can check recent alerts directly in the portal without accessing ONTAP System Manager or CLI.",
    "ストレージ管理者が ONTAP System Manager や CLI にアクセスしなくても、ポータル上で直近のアラートを確認できます。",
    "| Using ONTAP System Manager daily | Provide visibility to non-storage-admin team members |",
    "| ONTAP System Manager を日常利用中 | ストレージ管理者以外のメンバーへの可視性提供 |",
    "> **Storage operations note**: Your existing ONTAP System Manager workflows (volume creation,",
    "既存の ONTAP System Manager ワークフロー（ボリューム作成、スナップショット管理等）はそのまま維持できます",
]

# Correct sentences that sit close to the rule's subject. Every one of these
# shipped alongside the stale ones and must survive.
SM_CORRECT = [
    "- ONTAP System Manager 相当の管理操作は AppSync + Lambda 経由でブラウザから実行できます",
    "ONTAP System Manager-equivalent admin operations can be executed from a browser",
    "管理者がログインして最初に見るのは、4 枚のカードで構成されるヘルスダッシュボードです。ONTAP System Manager の「ダッシュボードファースト」パターンを踏襲しました。",
    'The first thing admins see after login is a 4-card health dashboard. This follows ONTAP System Manager\'s "dashboard first" pattern.',
    "各パネルはカード形式のグリッドで表示され、クリックすると詳細画面に遷移します。System Manager のカード型ナビゲーションを踏襲しています。",
    "Each panel displays as a card grid, clicking navigates to the detail view. Follows System Manager's card-based navigation.",
    "ブラウザから ONTAP System Manager と同等の操作感でキャッシュボリュームを管理できます。",
    "The experience mirrors ONTAP System Manager - accessible from any browser with Cognito authentication.",
    " * UI inspired by ONTAP System Manager's card-based navigation:",
    " * System Manager equivalent: Storage > Volumes > Anti-Ransomware",
    "Storage administration equivalent to ONTAP System Manager.",
    "ONTAP System Manager 相当のストレージ管理をファイルポータルの Web UI から提供します。",
    # The corrected replacements themselves.
    "ONTAP CLI / REST API の管理エンドポイントは VPC 内から到達します",
    "| **Ransomware visibility** | ONTAP ARP runs but checking needs the ONTAP CLI / REST API |",
    "ONTAP のバージョン管理、ノード、ディスク・シェルフは AWS が運用します。",
    "The ONTAP version, the nodes and the disks and shelves are operated by AWS.",
]


def _sm_rule(drift):
    return next(r for r in drift.CONTRADICTIONS if r["name"] == "system-manager-vpn")


@pytest.mark.parametrize("line", SM_SHIPPED_STALE)
def test_the_shipped_system_manager_claims_are_caught(drift, line):
    assert _sm_rule(drift)["claim"].search(line), line


@pytest.mark.parametrize("line", SM_CORRECT)
def test_design_and_equivalence_phrasings_are_left_alone(drift, line):
    """A true sentence about System Manager must not fire the rule.

    These describe where the UI took its layout from, and that the same
    operations are available. Both are accurate. Flagging them would make the
    check something to be silenced rather than read.
    """
    assert not _sm_rule(drift)["claim"].search(line), line


def test_the_rule_is_disabled_if_the_portal_stops_calling_ontap(drift):
    """The rule only stands while the code that disproves it is present.

    Each contradiction names a marker in a handler. If the portal ever stops
    talking to the ONTAP REST API, this claim is no longer contradicted by
    anything and the rule retires itself rather than becoming a rule nobody can
    explain.
    """
    handler_path, marker = _sm_rule(drift)["disproved_by"]
    handler = drift.PORTAL / handler_path
    assert handler.exists(), handler
    assert marker in handler.read_text()
    assert _sm_rule(drift) in drift.active_contradictions()


def test_the_repository_carries_the_sources_for_this_claim(drift):
    """The position is only usable if a reader can check it.

    A rule that says "this is false" without a citable reason is an assertion.
    Both language versions of the interfaces document must exist and must cite
    the AWS announcement and the vendor's deployment-mode table.
    """
    for name in ("ja", "en"):
        doc = drift.ROOT / "docs" / name / "fsx-ontap-management-interfaces.md"
        assert doc.exists(), doc
        text = doc.read_text()
        assert "aws.amazon.com/about-aws/whats-new/2023/12" in text, name
        assert "concept-modes" in text, name
