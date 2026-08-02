# Tamperproof Snapshot 設計ガイド

> FSx for ONTAP の Snapshot Locking（Tamperproof Snapshot）の設計・運用を正しく理解するためのドキュメント。

## 概要: 3 つのレイヤー

Tamperproof Snapshot には **3 つの独立した制御レイヤー** があります。混同しやすいため、明確に区別します。

```
┌──────────────────────────────────────────────────────────────────┐
│ レイヤー 1: ボリューム設定 (snapshot_locking_enabled)            │
│                                                                   │
│  「このボリューム上の Snapshot をロックできるようにする」         │
│  ⚠️ 一度 ON にしたら OFF にできない（不可逆）                    │
│  ⚠️ ON にしただけでは何もロックされない                          │
├──────────────────────────────────────────────────────────────────┤
│ レイヤー 2: Snapshot ポリシー (retention_period)                  │
│                                                                   │
│  「新規 Snapshot を撮る際に自動でロック期間を付与するか」        │
│  ✅ 自由に変更可能（ポリシー作成/削除/変更/アタッチ/デタッチ）  │
│  ✅ retention_period を付けなければ自動ロックされない            │
├──────────────────────────────────────────────────────────────────┤
│ レイヤー 3: 個別 Snapshot のロック (expiry_time)                  │
│                                                                   │
│  「既存の特定 Snapshot に保持期間を設定する」                    │
│  ⚠️ 一度設定したら延長のみ可能（短縮・解除不可）                │
│  ✅ ロックしていない Snapshot は通常通り削除可能                 │
└──────────────────────────────────────────────────────────────────┘
```

## 詳細: 各レイヤーの有効化/無効化

### レイヤー 1: ボリュームの `snapshot_locking_enabled`

| 操作 | 可否 | API | 備考 |
|------|:---:|-----|------|
| 有効化 (false → true) | ✅ | `PATCH /api/storage/volumes/{uuid}` `{"snapshot_locking_enabled": true}` | ポータル UI の「🔓 Tamperproof 有効化」ボタン |
| 無効化 (true → false) | ❌ | 同 API に `false` → **400 Bad Request** | 不可逆。設計上の仕様 |

**なぜ不可逆か**: 無効化を許可すると、既にロックされた Snapshot の保護が無意味になる。FSI/公共セクターの不変性要件では「管理者すら解除できない」ことが保証の根幹。

**注意**: これは「ロック**できる**ようにする」設定であり、「今後の全 Snapshot を自動ロックする」設定**ではない**。

### レイヤー 2: Snapshot ポリシー

| 操作 | 可否 | 備考 |
|------|:---:|------|
| ポリシー作成 | ✅ | スケジュール (hourly/daily/weekly) + 保持数 + retention_period (任意) |
| ポリシー削除 | ✅ | ボリュームに割当中でなければ削除可能 |
| ポリシー変更 | ✅ | スケジュール/保持数/retention_period の変更 |
| ボリュームへのアタッチ | ✅ | `PATCH /api/storage/volumes/{uuid}` に `snapshot_policy.name` |
| ボリュームからのデタッチ | ✅ | 別ポリシー（例: `none`）に変更 |
| retention_period の有無 | ✅ | 付けなければ新規 Snapshot は自動ロックされない |

**ポイント**: `snapshot_locking_enabled = true` のボリュームでも、ポリシーに `retention_period` を付けなければ新規 Snapshot は**ロックされない**。ロックはオプトイン。

### レイヤー 3: 個別 Snapshot のロック

| 操作 | 可否 | API | 備考 |
|------|:---:|-----|------|
| ロック設定（expiry_time 付与）| ✅ | `PATCH /api/storage/volumes/{uuid}/snapshots/{snap_uuid}` `{"expiry_time": "ISO8601"}` | ポータル「🔒 ロック」ボタン |
| ロック延長（expiry_time 延長）| ✅ | 同 API でより後の日時を指定 | 既存 expiry_time より前の日時は拒否される |
| ロック短縮 | ❌ | 400 Bad Request | 短縮は不可 |
| ロック解除 | ❌ | — | expiry_time を削除する API なし |
| ロック前の Snapshot 削除 | ✅ | `DELETE /api/storage/volumes/{uuid}/snapshots/{snap_uuid}` | ロックしていなければ通常削除可能 |

## 運用パターン

### パターン A: 手動ロック（推奨: 初期導入時）

1. ボリュームで Tamperproof を有効化（一度だけ）
2. 通常の Snapshot ポリシーで定期 Snapshot を撮る（retention_period なし）
3. 重要な Snapshot のみ手動でロック（ポータル UI の「🔒 ロック」ボタン）

**メリット**: 全 Snapshot がロックされないため、ストレージ容量管理が容易。重要なものだけ保護。

### パターン B: 自動ロック（推奨: コンプライアンス環境）

1. ボリュームで Tamperproof を有効化
2. Snapshot ポリシーに `retention_period` を設定（例: P30D）
3. 新規 Snapshot は自動的に 30 日間ロックされる

**メリット**: 人的操作なしで全 Snapshot が保護される。FISC/NARA/SEC 17a-4 要件に適合。

### パターン C: ロック運用の停止

Tamperproof を有効化した後でも、**新規ロックを停止**できます:

1. ポリシーから `retention_period` を削除 → 新規 Snapshot は自動ロックされなくなる
2. 手動ロックボタンを押さない → 個別ロックも発生しない
3. 既にロック済みの Snapshot は保持期間満了まで残る（これは変更不可）

**注意**: `snapshot_locking_enabled` 自体は OFF にできないが、**実質的に新規ロックを止める**ことは可能。

### パターン D: Tamperproof 運用の完全停止フロー（ポータル UI 手順）

以下の手順で、Tamperproof による新規ロックを完全に停止し、不要なポリシーを削除できます:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: ポリシーのデタッチ（ボリュームから外す）                │
│                                                                   │
│   リソース管理 → スナップショット管理 → Tamperproof タブ         │
│   → 対象ボリュームを選択 → 状態確認                              │
│   → 「適用ポリシー」ドロップダウンで "none" を選択               │
│                                                                   │
│   効果: 新規 Snapshot が撮られなくなる                            │
│   代替: retention_period なしのポリシーに変更すれば              │
│         Snapshot は撮るがロックしない                             │
├─────────────────────────────────────────────────────────────────┤
│ Step 2: ポリシーの削除（不要になった場合）                       │
│                                                                   │
│   リソース管理 → スナップショット管理 → ポリシータブ             │
│   → 対象ポリシーの「削除」ボタンをクリック                       │
│                                                                   │
│   注意: ボリュームに割当中のポリシーは削除不可。                 │
│   先に Step 1 でデタッチが必要。                                  │
├─────────────────────────────────────────────────────────────────┤
│ Step 3: 既存ロック済み Snapshot の扱い                            │
│                                                                   │
│   ⚠️ 既にロックされた Snapshot は変更不可:                       │
│   - 保持期間の短縮: 不可                                         │
│   - 削除: 不可（満了まで待つ）                                   │
│   - 保持期間の延長: 可能                                         │
│                                                                   │
│   → 保持期間が満了すれば自動的に通常 Snapshot に戻り、          │
│     削除可能になる                                                │
└─────────────────────────────────────────────────────────────────┘
```

**結論**: `snapshot_locking_enabled` は OFF にできないが、ポリシーのデタッチ/変更により **実質的に Tamperproof の運用を完全に停止**できる。既存ロックのみが満了まで残る。

## ポータル UI での対応

| UI 場所 | 操作 | レイヤー |
|---------|------|---------|
| スナップショット画面 → 「🔒 ロック」ボタン | 個別 Snapshot をロック | レイヤー 3 |
| スナップショット画面 → ロックダイアログ内「🔓 Tamperproof 有効化」| ボリューム機能を ON | レイヤー 1 |
| リソース管理 → スナップショット管理 → Tamperproof タブ | ボリューム機能を ON | レイヤー 1 |
| リソース管理 → スナップショット管理 → ポリシータブ | ポリシー管理 | レイヤー 2 |

## ONTAP REST API リファレンス

```bash
# レイヤー 1: ボリュームで Tamperproof 有効化
PATCH /api/storage/volumes/{vol_uuid}
Body: {"snapshot_locking_enabled": true}

# レイヤー 2: ポリシー作成（retention_period 付き = 自動ロック）
POST /api/storage/snapshot-policies
Body: {
  "name": "tamperproof-daily",
  "svm": {"name": "svm1"},
  "copies": [{
    "schedule": {"name": "daily"},
    "count": 30,
    "retention_period": "P30D"
  }]
}

# レイヤー 2: ポリシーをボリュームに割当
PATCH /api/storage/volumes/{vol_uuid}
Body: {"snapshot_policy": {"name": "tamperproof-daily"}}

# レイヤー 3: 個別 Snapshot をロック
PATCH /api/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}
Body: {"expiry_time": "2027-01-27T00:00:00Z"}
```

## 関連ドキュメント

- [Portal Tabs Guide](../solutions/amplify-portal/docs/portal-tabs-guide.md) — UI 操作ガイド
- [ONTAP Integration Notes](ontap-integration-notes.md) — ONTAP REST API 全般
- [Incident Response Playbook](incident-response-playbook.md) — ランサムウェア復旧手順
- [AGENTS.md](../AGENTS.md) — 「S3 Access Point Critical Knowledge」セクション
