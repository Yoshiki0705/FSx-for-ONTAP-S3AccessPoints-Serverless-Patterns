"""Tests for the measured-false claim rule in `check_portal_drift.py`.

The claim the rule guards is that FPolicy can stand in for the S3 event
notifications FSx for ONTAP S3 Access Points do not offer. It was measured false
on 2026-08-26 against ONTAP 9.18.1P3D1: nine data-plane calls through an access
point produced zero notifications, a `mandatory` synchronous policy with a
responding engine blocked nothing, and the same volume's NFSv3 control produced
three. Both UNIX + NFS and WINDOWS + SMB behaved the same way. Structurally, an
FPolicy event accepts only `cifs`, `nfsv3` and `nfsv4` for `protocol`; `s3` is
rejected with HTTP 400.

The cases below are the sentences that actually shipped, and the corrected
sentences that replaced them. A rule that catches the first set and leaves the
second alone is the whole requirement -- a rule firing on the corrected text
would push an editor back towards the wording that was wrong, and the corrected
wording contains both "FPolicy" and "S3 access point" precisely because it has to
name the distinction.

The scan-range test matters as much as the pattern tests. The pre-existing
`CONTRADICTIONS` scan reads `docs/ja/*.md` and `docs/en/*.md`, and every one of
the shipped occurrences was somewhere else: `docs/*.md` at the top level, an
`infrastructure/` README, and a CloudFormation parameter description.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
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


# Verbatim from the files as they stood before the correction, with the path each
# came from. The paths are listed so the range test below has real evidence for
# which globs would have had to match.
SHIPPED_FALSE = {
    "ja-user-guide-alternative": "| S3 Event Notifications | ✅ Supported | ❌ Not supported (代替: FPolicy) |",
    "en-user-guide-alternative": (
        "| S3 Event Notifications | ✅ Supported | ❌ Not supported (alternative: FPolicy) |"
    ),
    "ja-user-guide-faq": "| S3 Event Notifications は使えますか？ | **いいえ**。FPolicy または EventBridge Scheduler を使用 |",
    "en-user-guide-faq": "| Can I use S3 Event Notifications? | **No**. Use FPolicy or EventBridge Scheduler |",
    "ja-design-equivalent": "| イベント駆動処理 | S3 Event Notification 非対応 | FPolicy + EventBridge で同等機能を実現 |",
    "en-design-equivalent": (
        "| Event-driven processing | S3 Event Notification unsupported | "
        "FPolicy + EventBridge for equivalent functionality |"
    ),
    "ja-collection-readme": (
        "| **S3 Event Notification 非対応** | PutObject トリガーの Lambda は使えない | "
        "FPolicy + EventBridge でイベント駆動を実現 |"
    ),
    "en-collection-readme": (
        "| **S3 Event Notification unsupported** | Can't use PutObject-triggered Lambda | "
        "FPolicy + EventBridge for event-driven |"
    ),
    "ja-compatibility-pairing": "| イベント駆動ファイル処理 | ✅ (FPolicy + S3 AP) | △ (FPolicy + NFS mount) |",
    "en-compatibility-pairing": "| Event-driven file processing | ✅ (FPolicy + S3 AP) | △ (FPolicy + NFS mount) |",
    "en-enforcement-boundary": (
        "Enforcement boundaries remain ONTAP file-level ACL + FPolicy + S3 AP access point policy + IAM."
    ),
    "ja-enforcement-pairing": (
        "| FSx for ONTAP 直アクセス + 強制ガバナンス（現時点） | "
        "Snowflake External Table / Athena + ONTAP ACL/FPolicy | S3 Annotations とは独立 |"
    ),
    # Hard-wrapped at about 80 columns, which is how prose in this repository is
    # written. Neither line carries the claim on its own, so a line-only matcher
    # reports clean on it -- the reason `scan_text` also reads unwrapped
    # paragraphs.
    "en-prose-wrapped": (
        "Because native notifications are absent, the repository ships an\n"
        "FPolicy + EventBridge for event-driven ingestion, which covers the same ground.\n"
    ),
    # Verbatim from the published posts. These are the phrasings the first version
    # of the rule missed entirely: it was written against the table rows in `docs/`,
    # and all four articles said the same thing in prose. The corpus in
    # `check_published_articles.py` also had to grow -- it listed only the
    # file-portal series, so it reported PASS over every one of these.
    "published-ja-part4-tldr": (
        "S3 Access Points はネイティブのイベント通知をサポートしていません。Phase 10〜12 では "
        "ONTAP の FPolicy 機能を使って「ファイルが書き込まれたら即座に処理を起動する」"
        "Event-Driven パイプラインを実装しました。"
    ),
    "published-en-phase13-trigger": (
        "Trigger strategy matters. Because native S3AP event notifications are not available, "
        "the repository provides POLLING (simplest), EVENT_DRIVEN (FPolicy-based, near-real-time; "
        "not native S3 bucket notifications), and HYBRID modes. Default is POLLING."
    ),
    "published-en-phase10-answer": (
        "The answer is ONTAP FPolicy — a mature notification framework that predates S3 Access Points by over a decade."
    ),
    "published-en-phase10-interim": (
        "The FPolicy implementation is not a replacement for native S3AP notifications — it is "
        "evidence of customer demand and an interim event-driven pattern."
    ),
}

# The wording that replaced each of the above. Every one of these names FPolicy
# and the access point in the same sentence, because stating the distinction is
# the correction; a rule keyed on co-occurrence rather than on the assertion would
# fire on all of them.
CORRECTED = {
    "ja-user-guide-alternative": (
        "| S3 Event Notifications | ✅ Supported | ❌ Not supported "
        "(代替: EventBridge Scheduler ポーリング。FPolicy は AP 経由の操作を検知しない) |"
    ),
    "en-user-guide-alternative": (
        "| S3 Event Notifications | ✅ Supported | ❌ Not supported (alternative: EventBridge "
        "Scheduler polling. FPolicy does not see operations through the access point) |"
    ),
    "ja-user-guide-faq": (
        "| S3 Event Notifications は使えますか？ | **いいえ**。EventBridge Scheduler を使用。"
        "FPolicy が使えるのは書き込みが NFS / SMB 経由の場合のみ（AP 経由の書き込みは通知されない） |"
    ),
    "en-user-guide-faq": (
        "| Can I use S3 Event Notifications? | **No**. Use EventBridge Scheduler. FPolicy applies "
        "only where writes arrive over NFS or SMB (a write through the access point raises no "
        "notification) |"
    ),
    "ja-design-equivalent": (
        "| イベント駆動処理 | S3 Event Notification 非対応 | EventBridge Scheduler ポーリング。"
        "FPolicy + EventBridge が使えるのは**書き込みが NFS / SMB 経由で届く場合のみ**"
        "（AP 経由の書き込みは通知されない。実測 2026-08-26） |"
    ),
    "en-design-equivalent": (
        "| Event-driven processing | S3 Event Notification unsupported | EventBridge Scheduler "
        "polling. FPolicy + EventBridge applies **only where writes arrive over NFS or SMB** "
        "(a write through the access point raises no notification; measured 2026-08-26) |"
    ),
    "ja-collection-readme": (
        "| **S3 Event Notification 非対応** | PutObject トリガーの Lambda は使えない | "
        "EventBridge Scheduler ポーリング。**FPolicy は AP 経由の PutObject を検知しない**ため"
        "代替にならない（実測 2026-08-26 / ONTAP 9.18.1P3D1） |"
    ),
    "en-collection-readme": (
        "| **S3 Event Notification unsupported** | Can't use PutObject-triggered Lambda | "
        "EventBridge Scheduler polling. **FPolicy does not see a PutObject through the access "
        "point**, so it is not a substitute (measured 2026-08-26, ONTAP 9.18.1P3D1) |"
    ),
    "ja-compatibility-pairing": (
        "| イベント駆動ファイル処理 | △ (EventBridge Scheduler ポーリング。"
        "**FPolicy は S3 AP 経由の操作を検知しない** — 実測 2026-08-26 / ONTAP 9.18.1P3D1) | "
        "✅ (FPolicy + NFS/SMB) |"
    ),
    "en-compatibility-pairing": (
        "| Event-driven file processing | △ (EventBridge Scheduler polling. **FPolicy does not "
        "see operations through the S3 access point** — measured 2026-08-26, ONTAP 9.18.1P3D1) | "
        "✅ (FPolicy + NFS/SMB) |"
    ),
    "en-enforcement-boundary": (
        "Enforcement boundaries remain the ONTAP file-level ACL + S3 AP access point policy + "
        "IAM. **FPolicy does not count towards that boundary**: operations through an S3 access "
        "point raise no notification."
    ),
    "ja-enforcement-pairing": (
        "| FSx for ONTAP 直アクセス + 強制ガバナンス（現時点） | Snowflake External Table / "
        "Athena + ONTAP ACL（FPolicy は NFS / SMB 経路のみ） | S3 Annotations とは独立 |"
    ),
    "en-prose-wrapped": (
        "Because native notifications are absent, the repository ships EventBridge Scheduler\n"
        "polling. FPolicy is not a substitute: a write through the access point raises no\n"
        "notification.\n"
    ),
    # The qualifier has to sit in the same paragraph as the claim. `scan_text` reads a
    # paragraph at a time, so a correction appended at the end of an article is out of
    # the lookahead's reach -- which is deliberate: an article whose body still tells
    # the reader to use FPolicy is a finding even with a note at the bottom.
    "published-ja-part4-tldr": (
        "S3 Access Points はネイティブのイベント通知をサポートしていません。Phase 10〜12 では "
        "ONTAP の FPolicy 機能を使って「ファイルが書き込まれたら即座に処理を起動する」"
        "Event-Driven パイプラインを実装しました。**ただしこれが成立するのは、書き込みが "
        "NFS / SMB 経由で届く場合だけです**（下記の訂正）。"
    ),
    "published-en-phase13-trigger": (
        "Trigger strategy matters. Because native S3AP event notifications are not available, "
        "the repository provides POLLING (simplest), EVENT_DRIVEN (FPolicy-based, near-real-time; "
        "not native S3 bucket notifications), and HYBRID modes. Default is POLLING. "
        "**EVENT_DRIVEN applies only where writes arrive over NFS or SMB**: measured on "
        "2026-08-26 against ONTAP 9.18.1P3D1, operations through an S3 access point raise no "
        "FPolicy notification."
    ),
    # No corrected counterpart is asserted for these two: the sentence has to be
    # rewritten rather than qualified, because "the answer is FPolicy" and "an interim
    # pattern" have no true reading for the access point path. The replacement text is
    # in docs/errata-fpolicy-s3ap-coverage.md, and neither phrase survives it.
    "published-en-phase10-answer": (
        "The answer, where writes arrive over NFS or SMB, is ONTAP FPolicy — a mature "
        "notification framework that predates S3 Access Points by over a decade."
    ),
    "published-en-phase10-interim": (
        "The FPolicy implementation is not a replacement for native S3AP notifications, and on "
        "the access point path it is not an interim one either: those operations raise no "
        "notification at all."
    ),
}

# Sentences that are true about FPolicy and must never match. Each states what
# FPolicy does cover, which is the NFS / SMB path.
TRUE_ABOUT_FPOLICY = [
    "FPolicy detects NFS/SMB-side file operations.",
    "FPolicy は NFS / SMB のファイル操作を検知します。",
    "| **FPolicy** | ファイルアクセスイベント通知と監査設定 | `/protocols/fpolicy` |",
    "ONTAP version | 9.14.1+ (S3 Access Point support); 9.15.1+ for FPolicy mandatory mode",
    "EVENT_DRIVEN mode requires an FPolicy external engine reachable from the SVM.",
]


@pytest.mark.parametrize("case", sorted(SHIPPED_FALSE))
def test_rule_catches_what_shipped(drift, case):
    hits = drift.scan_text(SHIPPED_FALSE[case], drift.MEASURED_FALSE)
    assert hits, f"{case}: the rule does not catch text that shipped"


@pytest.mark.parametrize("case", sorted(CORRECTED))
def test_rule_leaves_the_correction_alone(drift, case):
    hits = drift.scan_text(CORRECTED[case], drift.MEASURED_FALSE)
    assert not hits, f"{case}: the rule fires on the corrected wording: {hits}"


def test_every_shipped_case_has_a_correction():
    """A case with no corrected counterpart proves only half of the rule."""
    assert set(SHIPPED_FALSE) == set(CORRECTED)


@pytest.mark.parametrize("sentence", TRUE_ABOUT_FPOLICY)
def test_true_statements_do_not_match(drift, sentence):
    assert not drift.scan_text(sentence, drift.MEASURED_FALSE)


def test_repository_is_clean(drift):
    """No tracked document currently carries the claim."""
    assert drift.check_measured_false_claims() == []


def test_scan_reaches_beyond_the_older_doc_globs(drift):
    """The corpus must include the paths where the claim actually lived.

    `CONTRADICTIONS` reads `DOC_GLOBS`, which covers `docs/ja/`, `docs/en/`, the
    portal docs and `drafts/`. Every shipped occurrence of this claim was outside
    all four. Asserting the file types rather than a fixed list of paths, so the
    test does not have to be edited when a document moves.
    """
    covered = {path.resolve() for glob in drift.DOC_GLOBS for path in ROOT.glob(glob)}
    must_reach = [
        ROOT / "docs" / "s3-bucket-user-guide.md",
        ROOT / "docs" / "design-considerations.md",
        ROOT / "docs" / "s3ap-compatibility-notes.md",
        ROOT / "docs" / "trigger-mode-decision-guide.md",
        ROOT / "infrastructure" / "s3ap-data-collection" / "README.md",
        ROOT / "solutions" / "edge" / "content-delivery" / "template.yaml",
    ]
    for path in must_reach:
        assert path.exists(), f"{path} moved; update this test with its new home"
        assert path.resolve() not in covered, (
            f"{path.relative_to(ROOT)} is now inside DOC_GLOBS, so this test no longer "
            "demonstrates the range gap it was written for"
        )


def test_empty_corpus_fails_rather_than_passing(drift, monkeypatch):
    """A scan that could not run must say so, not report a clean tree.

    `git ls-files` returns nothing outside a work tree, and `tracked_files`
    converts that into an empty list. Every scan built on it then finds no
    findings, which is indistinguishable from success.
    """
    monkeypatch.setattr(drift, "tracked_files", lambda: [])
    with pytest.raises(SystemExit):
        drift.check_measured_false_claims()


def test_missing_evidence_fails_rather_than_passing(drift, monkeypatch):
    """A guard that cannot find the measurement it cites has not run."""
    broken = [dict(rule, evidence="docs/does-not-exist.md") for rule in drift.MEASURED_FALSE]
    monkeypatch.setattr(drift, "MEASURED_FALSE", broken)
    with pytest.raises(SystemExit):
        drift.check_measured_false_claims()
