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

#### `retention_period` 付きポリシーはレイヤー 3 の「繰り返し版」

ポリシーへの `retention_period` は、レイヤー 3 の手動ロックとは影響範囲が違います。手動ロックは選んだ 1 個の Snapshot だけですが、ポリシーは**以降スケジュールが撮るすべての Snapshot を、誰も見ていない状態で自動的にロックし続けます**。設定は 1 回でも、結果は繰り返しです。

| 観点 | レイヤー 3（手動ロック） | レイヤー 2（ポリシー保持期間） |
|------|------------------------|------------------------------|
| 対象 | 選んだ 1 個 | スケジュールが撮る以降すべて |
| 実行者 | 操作した人 | スケジュール（無人） |
| 停止 | 対象外（そもそも 1 回） | 保持期間の削除 / 別ポリシーへ変更 / デタッチ |
| すでに発生したロック | 満了まで解除不可 | 同じ（停止してもロック済みは残る） |

**保持数は上限として機能しなくなります**。ロック済み Snapshot は世代交換で削除できないため、`count` を超えて満了まで蓄積し、その分の容量を消費します。これはコンプライアンスの問題ではなく容量の問題として現れます。

**ポリシー自体は元に戻せます**。保持期間の削除、別ポリシーへの変更、デタッチのいずれでも新規ロックは止まります。止められないのは、すでにロックされた Snapshot です。

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

## SnapLock ボリュームは上記 3 レイヤーとは別物

ここまでは **Snapshot** のロックです。**ボリューム自体を SnapLock にする**のは別の仕組みで、影響範囲が広く、取り消せる範囲も違います。名前が似ているため取り違えやすいので、区別します。

| | Snapshot ロック（レイヤー 1〜3） | SnapLock ボリューム |
|---|---|---|
| 対象 | Snapshot | ボリューム上の**ファイル**（WORM） |
| 設定タイミング | 後から有効化できる | **作成時のみ**。後から付与も解除も不可 |
| 種別変更 | — | 不可（`compliance` ⇄ `enterprise` も不可） |
| 削除をブロックする範囲 | その Snapshot のみ | ボリューム → **SVM → ファイルシステム**まで連鎖 |
| ONTAP フィールド | `snapshot_locking_enabled` / `expiry_time` | `snaplock.type` / `snaplock.retention` |

### 削除ロックは親リソースまで連鎖する

未満了の WORM ファイル（または未満了の監査ログ）が 1 つでも残っていると、次のすべてが削除できません。

```
未満了の WORM ファイル / 監査ログ
        ↓ ブロック
   ボリューム            ← DELETE が失敗（ONTAP エラー 525057）
        ↓ ブロック
   SVM
        ↓ ブロック
   ファイルシステム      ← 満了まで課金が続く
```

`compliance` では保持期間満了まで**誰も**削除できません（アカウント管理者も、AWS も）。`enterprise` は特権削除が**有効な場合に限り**削除できますが、`PrivilegedDelete=PERMANENTLY_DISABLED` は終端状態で、これを設定すると `compliance` と同じ扱いになります。

### 監査ログボリュームの保持期間

SnapLock 監査ログボリューム（`snaplock.is_audit_log = true`）は、上記の連鎖ブロックを**最短 6 か月**発生させます。

| 項目 | 内容 |
|---|---|
| 最小保持期間 | 6 か月（[AWS ドキュメント記載](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snaplock-delete-volume.html)。より短い値が拒否されるかは未検証） |
| `enterprise` で作成した場合 | 同じくブロックする（種別による例外はない） |
| AWS API での保持期間指定 | **手段がない**（下記） |
| 保持期間満了前の削除 | 不可。AWS サポート経由でも不可。アカウント閉鎖以外の経路は存在しない |

**AWS API には監査ログ保持期間を指定するフィールドがありません。** `CreateSnaplockConfiguration` は `SnaplockType` / `AuditLogVolume` / `AutocommitPeriod` / `PrivilegedDelete` / `RetentionPeriod` / `VolumeAppendModeEnabled` の 6 つで、`RetentionPeriod` はボリューム上の WORM ファイル用です。監査ログ側の保持期間は ONTAP CLI の `snaplock log create -retention-period` でのみ指定できます。

つまり **AWS API だけで監査ログボリュームを作ると、既定の 6 か月が適用され、それを選ぶ余地がありません**。ボリューム側の `RetentionPeriod` を 0 にしていても関係ありません（縛っているパラメータが別）。

### 診断上の落とし穴: `AuditLogVolume: False` は「削除できる」を意味しない

SVM レベルの監査ログ指定は ONTAP REST API で解除できます（アンマウント後に `DELETE /api/storage/snaplock/audit-logs/{svm.uuid}`）。解除すると AWS API の `DescribeVolumes` は `AuditLogVolume: False` を返すようになります。それでも**削除できません**。

ブロックしているのは指定ではなく、**すでにファイルに適用された保持期間**です。監査ログとして書かれたファイルには作成時に最短 6 か月の保持が付き、指定を解除してもその保持は残ります。したがって指定を外す操作は削除の前提を 1 つも変えません。

2 つのフィールドの役割も分けて理解する必要があります。AWS サポートの回答によれば、現在の指定を表す正しいフィールドは AWS API の `AuditLogVolume` です。ONTAP の `snaplock.is_audit_log` は「その SVM の監査ログボリュームとして過去に一度でも設定された」ことを示す履歴マークで、読み取り専用のまま false に戻りません。**削除可否の判断に使えるのはどちらでもなく**、`DescribeVolumes` の `LifecycleTransitionReason.Message`（`Cannot delete the volume because it contains unexpired log files.`）と、ONTAP の `volume snaplock show -vserver <svm> -volume <vol> -instance` が返す Expiry Time です。

さらに AWS API の `DeleteVolume` は、この状況で**エラーを返しません**。`DELETING` に遷移した後、無言で `CREATED` に戻ります。`BypassSnaplockEnterpriseRetention=true` や `SkipFinalBackup=true` を付けても同じです。成功したように見えて何も起きていないため、レスポンスではなく数十秒後の `Lifecycle` で判断する必要があります。

### 事前チェック（作成前に必ず）

SnapLock ボリューム、特に監査ログボリュームを作る前に、以下を確認してください。

- [ ] このファイルシステムを**今後 6 か月削除しない**ことが確定しているか
- [ ] 検証用ファイルシステムに作ろうとしていないか（検証用こそ消せなくなると困る）
- [ ] 監査ログが本当に必要か。SnapLock ボリュームの利用自体には監査ログは必須ではない
- [ ] 必要な場合、保持期間を ONTAP CLI で明示指定できる経路があるか
- [ ] 同一 SVM・同一ファイルシステムに、消せなくなると困る他のボリュームが載っていないか

## ポータル UI での対応

| UI 場所 | 操作 | レイヤー |
|---------|------|---------|
| スナップショット画面 → 「🔒 ロック」ボタン | 個別 Snapshot をロック | レイヤー 3 |
| スナップショット画面 → ロックダイアログ内「🔓 Tamperproof 有効化」| ボリューム機能を ON | レイヤー 1 |
| リソース管理 → スナップショット管理 → Tamperproof タブ | ボリューム機能を ON | レイヤー 1 |
| リソース管理 → スナップショット管理 → ポリシータブ | ポリシー管理 | レイヤー 2 |
| リソース管理 → スナップショット管理 → ポリシー作成の「保持期間」| **以降すべての Snapshot を自動ロック** | レイヤー 2 |
| リソース管理 → ボリューム管理 → 作成フォームの SnapLock 設定 | **SnapLock ボリュームの作成** | 別（上記セクション） |
| リソース管理 → SnapLock 管理 → 既定保持期間の変更 | WORM ファイルの既定保持期間 | 別（上記セクション） |

不可逆な操作、および削除ロックを発生させる操作は、実行前に確認ダイアログが出ます。ダイアログは入力値から「何がいつまで削除できなくなるか」を具体的な日付で示し、取り消せない項目を明示します。詳細は [ポータル実装ガイド](../solutions/amplify-portal/docs/IMPLEMENTATION.md) を参照してください。

ポリシーの保持期間は、個々のロックがチェックボックス相当であるにもかかわらず**キーワード入力**を求めます。1 回の操作ではなく、無人でロックを作り続ける常設の指示だからです。保持期間が空欄のポリシーは不可逆な結果を持たないため、確認なしでそのまま作成されます。

確認はブラウザ側の話なので、Lambda 側でも `acknowledgeIrreversible=true` を要求します。AppSync を直接呼ぶ経路にダイアログは存在しません。ガードは入力検証の**後**に走るため、値が不正な場合はフラグではなく値の問題が返ります。

なお、ポータルには**監査ログボリュームを作成する経路はありません**。監査ログボリュームは削除ロックの影響が最大（最短 6 か月、ファイルシステムまで連鎖）で、かつ AWS API に保持期間の指定手段がないため、GUI からは作成できないようにしています。必要な場合は ONTAP CLI で保持期間を明示して作成してください。

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

## 実測で判明した挙動（2026-08、ONTAP 9.18.1P3D1）

調べ直さずに済むように、実測した事実と設計判断をここに残します。手順の再実行は不要です。

### 保持期間付き Snapshot ポリシーを割り当てても、ロック状態の表示は変わらない

`retentionPeriod` を持つスケジュールでポリシーを作り、ボリュームに割り当てても、
`getSnapshotLockingStatus` は `snapshotLockingEnabled: false` のままで、変わるのは
`snapshotPolicy` だけです。**「ロック機能は無効」と表示されている状態で、割り当て済みポリシーは
「取得する Snapshot を毎回ロックする」と言っている**、という食い違った読み方ができます。

状態パネルだけを見て「何もロックされない」と判断しないでください。判断には
`snapshotPolicy` に紐づくポリシーの `retentionPeriod` も読む必要があります。UI がこの 2 つを
別のパネルに置いている限り、運用者は片方だけを見ます。

作成時の承認フラグは効いていて、拒否メッセージも具体的です（「このポリシーが取る Snapshot は
毎回 P1D ロックされ、満了前に削除も短縮もできない」）。**未確認**: スケジュールが発火して
生成された Snapshot が実際にロックされるか。日次スケジュールの発火を待っていません。

### S3 Object Lock: 2 つのモードはエラーメッセージで区別できない

同じ「保持 1 日」で書いたオブジェクトに対する削除の挙動です。

| 操作 | GOVERNANCE | COMPLIANCE |
|---|---|---|
| bypass 無しの削除 | `AccessDenied ... object protected by object lock` | 同じ文面 |
| `BypassGovernanceRetention=true` の削除 | **成功** | `AccessDenied ... object protected by object lock` |
| 既定保持ルールの差し替え | 可能 | 可能（既存オブジェクトの保持は残る） |

**エラー文面が同一なので、失敗の理由からモードは分かりません。** 切り分けには
`get-object-lock-configuration` でバケットの既定ルールを、`head-object` で対象オブジェクトの
`ObjectLockMode` を読みます。「bypass を付けたのに消えない」を権限問題として調べ始めると
時間を失います。最初に読むのはモードです。

なお `put_object_retention` に**同じ**満了日時を渡すと受理されます。これは短縮ではないので
正常な挙動で、「短縮できた」と誤読しないでください。短縮の検証には過去日時を渡す必要があります。

### ガードの設計判断: 有効化はブロック、既定ルールは確認

不可逆操作ガードは当初 `putS3ObjectLockRetention` を無条件にブロックし、その文面で
「GOVERNANCE で足りるか再検討してください」と勧めていました。**勧めた選択肢を取る手段が
存在しない**状態で、GOVERNANCE を使う検証が実行できませんでした。

現在は 2 つを分けています。

- **バケットへの Object Lock 有効化はブロック**。解除できないため
- **既定保持ルールの設定は確認（ask）**。ルールは上書きでき、GOVERNANCE で書かれた
  オブジェクトは `s3:BypassGovernanceRetention` を持つ呼び出し元が即削除できるため
- **厳格なモードはブロックのまま**。モード名を見る別ルールが先に評価される

BLOCK を ASK より先に評価する順序が、この分離を成立させています。ASK に到達した時点で
厳格モードのパターンには当たっていないことが確定するためです。

一般化すると、**ガードは「不可逆」と「破壊的だが復旧可能」を別の段に置く必要があります。**
同じ段に入れると、安全な代替手段を勧めながらその手段を塞ぐ状態になり、利用者はガードを
無効化する方向に動きます。

> ガードはシェルコマンドの文字列を見るため、`COMPLIANCE` という語を含む**ソース編集**の
> コマンドもブロックします。編集は専用の編集ツールで行えば通ります（本来それが正しい手段
> でもあります）。ガードが「AWS への呼び出し」と「その語を含むファイル編集」を区別できて
> いない点は既知です。

## 関連ドキュメント

- [Portal Tabs Guide](../solutions/amplify-portal/docs/portal-tabs-guide.md) — UI 操作ガイド
- [ONTAP Integration Notes](ontap-integration-notes.md) — ONTAP REST API 全般
- [Incident Response Playbook](incident-response-playbook.md) — ランサムウェア復旧手順
- [AGENTS.md](../AGENTS.md) — 「S3 Access Point Critical Knowledge」セクション
