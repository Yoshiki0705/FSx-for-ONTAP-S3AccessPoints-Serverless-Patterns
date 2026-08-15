#!/usr/bin/env python3
"""PreToolUse guard: stop irreversible retention operations before they execute.

## Why this file is tracked

An agent created a SnapLock audit-log volume on a verification file system.
Unexpired WORM audit logs block deletion of the volume, then the SVM, then the
*file system*, for a minimum of six months with no early exit short of closing
the AWS account. Nothing in the response indicated a problem: the create returned
success, and the later `DeleteVolume` also returned success while silently
reverting the volume from DELETING back to CREATED.

Prose in a steering file did not prevent it, because the prose was not re-read at
the moment the command was typed. A PreToolUse hook runs at exactly that moment.

**The guard has to be a tracked file.** `.kiro/` is gitignored here, so a guard
living only there does not exist for a collaborator, for a fresh clone, or for
CI — and a hook pointing at `$HOME` silently protects one machine. That is not
hypothetical: in the sibling repository the executing copy was the `$HOME` one
and it allowed 10 of the 26 cases the tracked copy documented. Two copies drift,
and the one that drifts is the one nobody can review in a pull request.

`.kiro/hooks/irreversible-ops-guard.json` therefore invokes **this** path,
resolved through `git rev-parse --show-toplevel`.

## What this repository specifically exposes

The Amplify portal ships mutating actions that reach ONTAP and S3 directly:
`enableSnapshotLocking`, `lockSnapshot`, `putS3ObjectLockRetention`,
`updateSnaplockRetention`, and `createVolume` carrying `snaplockType`. Those
action names are matched here alongside the CLI and REST shapes, because an agent
driving the portal's dispatch endpoint sends the action name, not an AWS CLI
string.

The read-only twins — `getSnapLockConfig`, `getSnapshotLockingStatus`,
`getSnapshotsWithLockStatus`, `getS3ObjectLockStatus` — must stay allowed.
Blocking a read is not a safe default: an agent that cannot see the current
retention state guesses at it, and guessing is what this guard exists to stop.

## Contract

Per kiro.dev/docs/hooks/actions.md:

    exit 0 + empty stdout                     -> allow
    exit 0 + permissionDecision "ask" on stdout -> prompt the human first
    exit 2 + stderr                           -> BLOCK, stderr goes to the agent
    any other non-zero                        -> warning only, does NOT block

Only 0 and 2 are ever returned. A malformed event returns 0: failing closed on
unparseable input would block all work, which gets the hook disabled.

## Verifying it

    python3 scripts/guard_irreversible_ops.py --selftest

and `scripts/tests/test_guard_irreversible_ops.py` runs the same corpus under
pytest, including the assertion that this file covers every category the global
copy covers when both are present.
"""

from __future__ import annotations

import json
import re
import sys

# Separator between a key and its value. It has to tolerate every shape the same
# setting arrives in: `--flag VALUE`, `--flag=VALUE`, `"key": "VALUE"`, and the
# backslash-escaped quoting produced when a JSON payload is nested inside a shell
# string inside the event JSON.
SEP = r"[\s\\\"':=]{0,8}"

# --------------------------------------------------------------------------
# Tier 1 — BLOCK.
#
# Each of these creates a retention lock that cannot be shortened or removed, and
# several make a PARENT resource undeletable. No agent should reach them without
# an explicit human decision, so the answer is "no", not "are you sure".
#
# Categories are kept aligned with the global copy at
# ~/.kiro/hooks/scripts/guard_irreversible_ops.py. This file may ADD but must not
# narrow: test_covers_every_global_block_category enforces that when both exist.
# --------------------------------------------------------------------------
BLOCK: list[tuple[str, str, str]] = [
    (
        r"snaplock[-_\s]*log[-_\s]*create|audit[-_]?log[-_]?volume" + SEP + r"(true|yes)",
        "SnapLock 監査ログボリュームの作成",
        "6 か月以上、ボリューム → SVM → ファイルシステムの削除を連鎖的にブロックします。"
        "AWS API には監査ログの保持期間を指定するフィールドが存在せず、既定の 6 か月が適用されます。"
        "満了前の削除経路はアカウント閉鎖以外にありません（AWS サポートでも不可）。",
    ),
    (
        r"-X\s*POST[^|;&]{0,200}snaplock/audit-logs|snaplock/audit-logs[^|;&]{0,200}-d\s",
        "ONTAP REST による SnapLock 監査ログ設定の作成",
        "AWS API 経由と同じ結果になります（監査ログボリュームが 6 か月ロックされ、"
        "親リソースの削除を連鎖的にブロックする）。REST 経由でも保持期間の既定は変わりません。",
    ),
    (
        r"create[-_]snaplock[-_]?configuration|"
        r"snaplock[-_]?type" + SEP + r"(compliance|enterprise)|"
        r"\"SnaplockType\"\s*:\s*\"(COMPLIANCE|ENTERPRISE)\"|"
        # ONTAP REST shape: {"snaplock": {"type": "compliance"}}
        r"snaplock[\"'\\\s]*:[^{]{0,8}\{[^{}]{0,160}type" + SEP + r"(compliance|enterprise)",
        "SnapLock ボリュームの作成",
        "snaplock.type は作成時のみ指定可能で、後から変更も解除もできません。"
        "未満了の WORM ファイルは親リソースの削除をブロックします。",
    ),
    (
        r"privileged[-_]?delete" + SEP + r"permanently_disabled",
        "PrivilegedDelete=PERMANENTLY_DISABLED",
        "終端状態です。enterprise モードが compliance 相当になり、以後 privileged delete が永久に使えません。",
    ),
    (
        r"snapshot[-_]?locking[-_]?enabled" + SEP + r"true|"
        # The portal's own mutating action name. An agent driving the dispatch
        # endpoint sends this, not a CLI string, so matching only CLI shapes
        # would leave the portal path unguarded.
        r"\"?action\"?" + SEP + r"[\"']?enableSnapshotLocking",
        "Snapshot locking の有効化",
        "Compliance ボリュームでは不可逆です（無効化は 400 Bad Request）。"
        "新規ロックを止めるにはポリシーの retention_period を外す必要があります。",
    ),
    (
        r"-snaplock-expiry-time\b|modify-snaplock-expiry-time\b|"
        r"snaplock_expiry_time" + SEP + r"[\"']?\d|"
        r"\"?action\"?" + SEP + r"[\"']?lockSnapshot",
        "Snapshot の SnapLock expiry 設定",
        "expiry_time は延長のみ可能で、短縮も解除もできません。"
        "未満了のロック済み Snapshot があるボリュームは削除できません。",
    ),
    (
        r"snapshot\s+policy\s+create[^|;&]{0,300}retention[-_]period|"
        r"snapmirror\s+policy\s+add-rule[^|;&]{0,300}retention[-_]period",
        "ロック付き Snapshot ポリシー / SnapMirror 保持ルール",
        "retention_period を持つポリシーは以後の Snapshot をロックします。"
        "retention は keep 数を上書きするため、hourly × 長期保持で 1,023 個の上限に達すると"
        "新規 Snapshot が作成できなくなり、待つ以外の復旧手段がありません。"
        "retention × 頻度 < 1,023 を先に計算してください。",
    ),
    (
        r"object[-_]?lock[-_]?mode" + SEP + r"compliance|"
        r"(?:retention|object[-_]?lock)[^|;&]{0,120}?[\"'\\]mode[\"'\\]" + SEP + r"compliance|"
        r"object[-_]?lock[-_]?enabled[-_]?for[-_]?bucket",
        "S3 Object Lock COMPLIANCE モード",
        "保持期間の短縮も解除もできません。ルートアカウントでも不可です。"
        "GOVERNANCE モードで足りるか再検討してください。",
    ),
    (
        r"\bput-object-lock-configuration\b|ObjectLockEnabled" + SEP + r"Enabled|"
        r"\"?action\"?" + SEP + r"[\"']?putS3ObjectLockRetention",
        "S3 Object Lock のバケット有効化 / 保持期間の設定",
        "バケットに対して一度有効化すると解除できません。COMPLIANCE の保持期間は短縮もできません。"
        "オブジェクト単位なら GOVERNANCE で足りるか、そもそもバージョニングとライフサイクルで"
        "足りるかを先に検討してください。",
    ),
    (
        r"\b(?:initiate|complete)-vault-lock\b",
        "S3 Glacier Vault Lock",
        "complete-vault-lock は終端操作です。ロックポリシーは以後変更も削除もできません。"
        "initiate 後 24 時間の InProgress の間だけ abort-vault-lock で中止できます。",
    ),
    (
        r"\bput-backup-vault-lock-configuration\b|changeable[-_]?for[-_]?days",
        "AWS Backup Vault Lock",
        "ChangeableForDays を過ぎると compliance モードのロックは解除できず、"
        "保持期間内のリカバリポイントは削除できません。Vault ごと消すこともできません。",
    ),
    (
        r"\block-snapshot\b|\"?operation_?name\"?\W*[:=]\W*[\"']?LockSnapshot",
        "EBS スナップショットのロック",
        "compliance モードでは CoolOffPeriod 経過後にロック解除も期間短縮もできません。"
        "governance モードで足りるかを先に確認してください。",
    ),
]

# --------------------------------------------------------------------------
# Tier 2 — ASK.
#
# Either destructive-but-legitimate, or the payload is opaque to this guard so a
# Tier 1 pattern could be hiding inside it. An opaque payload is the case worth
# dwelling on: a guard that cannot read the input must not report "allow", or its
# silence means two different things.
# --------------------------------------------------------------------------
ASK: list[tuple[str, str]] = [
    (
        r"\bfsx\b.{0,40}\bdelete[-_](file[-_]?system|storage[-_]?virtual[-_]?machine|volume)|"
        r"\"?operation_?name\"?\W*[:=]\W*[\"']?Delete(FileSystem|StorageVirtualMachine|Volume)|"
        r"\"?action\"?" + SEP + r"[\"']?deleteVolume",
        "FSx のファイルシステム / SVM / ボリュームの削除はデータ損失を伴います。"
        "未満了 WORM や監査ログがある場合、成功を返しながら無言で削除されないことがあります"
        "（数十秒後の Lifecycle で判定してください。フラグを足して再試行しないこと）。",
    ),
    (
        r"\bfsx\b.{0,40}\bcreate-volume\b.{0,200}--cli-input-json|\bcreate-volume\b.{0,200}\bfile://",
        "create-volume の payload が外部ファイルにあり、このガードから中身が読めません。"
        "SnaplockConfiguration が含まれていないか確認してください（含まれていれば不可逆です）。",
    ),
    (
        r"expiry[-_]?time.{0,80}(snapshot|POST|PATCH)|snapshots?/.{0,80}expiry[-_]?time",
        "Snapshot のロック（expiry_time）は延長のみ可能で、短縮も解除もできません。",
    ),
    (
        r"\"?action\"?" + SEP + r"[\"']?(updateSnaplockRetention|updateRetentionPolicy)",
        "保持期間の変更は延長方向にしか効かないことがあります。"
        "現在値を読んでから、短縮になっていないか確認してください。",
    ),
    (
        r"\"?action\"?" + SEP + r"[\"']?deleteFileForever",
        "deleteFileForever はバージョンを含めて完全に削除します。復旧経路はありません。",
    ),
]

# Reads must never be blocked. The ONTAP CLI puts the object before the verb, so
# `volume snapshot show -fields snaplock-expiry-time` is a read that a
# verb-first pattern would send into a BLOCK rule.
ALLOW_READ_ONLY = re.compile(
    r"""(?xi)
    ^\s*(?:\S*\s+)?(?:aws\s+[\w-]+\s+)?(?:describe|list|get|head|show)[-_a-z]*\b
  | ^\s*(?:volume|vserver|snapmirror|snaplock|security)\s+[\w\s-]*?\bshow\b
    """
)

# The portal's read-only action names. `getSnapLockConfig` contains "snaplock"
# and `getSnapshotsWithLockStatus` contains "lock", so without this they would be
# matched by the BLOCK patterns above and reading the retention state would
# become impossible.
ALLOW_ACTIONS = re.compile(
    r"\"?action\"?" + SEP + r"[\"']?(?:get|list|describe)[A-Za-z0-9_]*",
    re.IGNORECASE,
)


def scan(subject: str) -> tuple[int, str]:
    """Classify a serialized tool input.

    Args:
        subject: The JSON-serialized ``tool_input`` of a PreToolUse event.

    Returns:
        ``(2, message)`` to block, ``(0, message)`` to ask, ``(0, "")`` to allow.
    """
    for pattern, label, why in BLOCK:
        if re.search(pattern, subject, re.IGNORECASE | re.DOTALL):
            return 2, (
                f"BLOCKED: {label}\n\n"
                f"{why}\n\n"
                "この操作は不可逆で、実行後に検証しても復旧できません。続行するには:\n"
                "  1. 影響範囲（どのリソースが、いつまで削除不能になるか、その間の月額）を提示する\n"
                "  2. アカウント所有者の明示的な承認を得る\n"
                "  3. 検証環境では実行しない（削除できないファイルシステムは長期の請求になります）\n\n"
                "参考: AGENTS.md の「Irreversible Operations」節、"
                "docs/agent/pitfalls-snaplock.md、scripts/guard_irreversible_ops.py"
            )
    for pattern, why in ASK:
        if re.search(pattern, subject, re.IGNORECASE | re.DOTALL):
            return 0, why
    return 0, ""


def classify(tool_input: dict[str, object]) -> tuple[int, str]:
    """Apply the read-only allowances, then the rules.

    Args:
        tool_input: The ``tool_input`` mapping from a PreToolUse event.

    Returns:
        Same convention as :func:`scan`.
    """
    subject = json.dumps(tool_input, ensure_ascii=False)

    command = tool_input.get("command", "")
    if isinstance(command, str) and command and ALLOW_READ_ONLY.match(command):
        return 0, ""

    # A read-only action name allows only when no mutating shape is also present,
    # so a chained payload cannot smuggle a write past a leading `get`.
    if ALLOW_ACTIONS.search(subject):
        code, _ = scan(subject)
        if code == 0:
            return 0, ""

    return scan(subject)


def _selftest() -> int:
    """Run the block/ask/allow corpus and report.

    Returns:
        0 when every case behaves as declared, 1 otherwise.
    """
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
    try:
        from test_guard_irreversible_ops import ALLOW_CASES, ASK_CASES, BLOCK_CASES
    except ImportError:
        print("selftest needs scripts/tests/test_guard_irreversible_ops.py", file=sys.stderr)
        return 1

    failures = 0
    for label, payload, expected in (
        *[(c[0], c[1], 2) for c in BLOCK_CASES],
        *[(c[0], c[1], 1) for c in ASK_CASES],
        *[(c[0], c[1], 0) for c in ALLOW_CASES],
    ):
        code, message = classify(payload)
        actual = 2 if code == 2 else (1 if message else 0)
        status = "ok  " if actual == expected else "FAIL"
        if actual != expected:
            failures += 1
        print(f"{status}  [{('allow', 'ask', 'block')[expected]}] {label}")
    total = len(BLOCK_CASES) + len(ASK_CASES) + len(ALLOW_CASES)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    """Read a PreToolUse event from stdin and emit the hook decision.

    Args:
        argv: Command-line arguments; ``--selftest`` runs the corpus instead.

    Returns:
        2 to block, otherwise 0.
    """
    if "--selftest" in argv:
        return _selftest()

    # Run by hand with no piped input, json.load blocks on the terminal forever
    # with no indication why. Kiro always supplies stdin, so this only affects
    # someone verifying the guard — which is exactly when a silent hang is most
    # confusing.
    if sys.stdin.isatty():
        print(
            "This is a PreToolUse hook: it expects a JSON event on stdin.\n"
            '  echo \'{"tool_input":{"command":"aws fsx describe-file-systems"}}\' '
            "| python3 scripts/guard_irreversible_ops.py\n"
            "To verify block/ask/allow behaviour:\n"
            "  python3 scripts/guard_irreversible_ops.py --selftest",
            file=sys.stderr,
        )
        return 0

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never fail closed: that would block all work
    if not isinstance(event, dict):
        return 0

    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}

    code, message = classify(tool_input)

    if code == 2:
        print(message, file=sys.stderr)
        return 2

    if message:
        json.dump(
            {
                "hookSpecificOutput": {
                    "permissionDecision": "ask",
                    "permissionDecisionReason": message,
                }
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
