# PSTK ↔ Amplify Portal ↔ ONTAP REST API マッピング

> PowerShell Toolkit (PSTK) の各操作が、Amplify Portal のどの UI パネルに対応し、
> バックエンドのどの REST API アクションで実装されているかの完全な対応表。

---

## 概要

Amplify Portal (`solutions/amplify-portal/`) は ONTAP REST API を Python Lambda 経由で直接呼び出しており、
PSTK を経由していない。しかし、PSTK で実行可能な操作の大部分は Portal UI で同等に実行可能。

**ユーザにとっての意味**: PSTK か REST API かの技術的違いを意識する必要はない。
Portal UI から操作できる機能は、PSTK スクリプトで同じことをバッチ化した場合と同じ結果になる。

---

## カバレッジ概要

| カテゴリ | PSTK Cmdlets | Portal UI | ステータス |
|---------|:---:|:---:|:---:|
| CIFS/SMB 共有 | 10 | ✅ `CifsShareManager` | **実装済み** |
| ローカルユーザ/グループ | 10 | 🆕 `LocalUserManager` | **新規追加** |
| ボリューム | 10 | ✅ `VolumeManager` | **実装済み** |
| スナップショット | 7 | ✅ `SnapshotAdminManager` | **実装済み** |
| エクスポートポリシー | 7 | ✅ `ExportPolicyManager` | **実装済み** |
| Qtree | 4 | ✅ `QtreeManager` | **実装済み** |
| QoS ポリシー | 4 | ✅ `QosPolicyManager` | **実装済み** |
| SnapLock | 3 | ✅ `SnaplockManager` | **実装済み** |
| クォータ | 4 | ✅ `QuotaManager` | **実装済み** |
| ストレージ効率 | 2 | ✅ `EfficiencyPanel` | **実装済み** |
| ARP/ランサムウェア | 5 | ✅ `ArpAdminManager` | **実装済み** |
| FlexClone | 3 | ⚠️ スナップからのみ | Phase 2 候補 |
| FPolicy | 6 | ❌ | Phase 3 候補 |
| Vscan | 5 | ❌ | Phase 3 候補 |
| SnapMirror | 3 | ❌ | Phase 3 候補 |
| ネームマッピング | 3 | ❌ | Phase 3 候補 |
| DNS/ネームサービス | 3 | ❌ | 低優先 |
| ネットワーク (LIF) | 3 | ❌ (読取のみ) | 低優先 |
| パフォーマンス | 3 | ⚠️ StorageDashboard | CloudWatch 推奨 |

---

## 詳細マッピング表

### 1. CIFS/SMB 共有管理 ✅ 実装済み

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `Get-NcCifsShare` | 共有一覧表示 | `listCifsShares` | `GET /protocols/cifs/shares` |
| `Add-NcCifsShare` | 「共有作成」ボタン | `createCifsShare` | `POST /protocols/cifs/shares` |
| `Remove-NcCifsShare` | 「共有削除」ボタン | `deleteCifsShare` | `DELETE /protocols/cifs/shares/{..}` |
| `Set-NcCifsShare` | 暗号化トグル | `updateCifsShare` | `PATCH /protocols/cifs/shares/{..}` |
| `Get-NcCifsShareAcl` | ACL 列表示 | (listCifsShares に含む) | `fields=acls` |
| `Add-NcCifsShareAcl` | — (Phase 2: ACL 編集UI) | — | `POST .../acls` |
| `Remove-NcCifsShareAcl` | — (Phase 2) | — | `DELETE .../acls/{..}` |
| `Get-NcCifsServer` | StorageDashboard | (内部使用) | `GET /protocols/cifs/services` |
| `Get-NcCifsSession` | — (Phase 3: セッション監視) | — | `GET /protocols/cifs/sessions` |

**Portal パネル**: `src/components/admin/CifsShareManager.tsx`  
**カテゴリ**: Access Control (🔐)

---

### 2. ローカルユーザ/グループ 🆕 新規追加

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `Get-NcCifsLocalUser` | ユーザ一覧 | `listLocalUsers` | `GET /protocols/cifs/local-users` |
| `New-NcCifsLocalUser` | 「ユーザ作成」ボタン | `createLocalUser` | `POST /protocols/cifs/local-users` |
| `Remove-NcCifsLocalUser` | 「削除」ボタン | `deleteLocalUser` | `DELETE /protocols/cifs/local-users/{..}` |
| `Set-NcCifsLocalUser` | パスワード変更 | `updateLocalUser` | `PATCH /protocols/cifs/local-users/{..}` |
| `Get-NcCifsLocalGroup` | グループ一覧 | `listLocalGroups` | `GET /protocols/cifs/local-groups` |
| `New-NcCifsLocalGroup` | 「グループ作成」ボタン | `createLocalGroup` | `POST /protocols/cifs/local-groups` |
| `Remove-NcCifsLocalGroup` | 「削除」ボタン | `deleteLocalGroup` | `DELETE /protocols/cifs/local-groups/{..}` |
| `Get-NcCifsLocalGroupMember` | メンバー一覧展開 | `listGroupMembers` | `GET .../members` |
| `Add-NcCifsLocalGroupMember` | 「メンバー追加」 | `addGroupMember` | `POST .../members` |
| `Remove-NcCifsLocalGroupMember` | 「メンバー削除」 | `removeGroupMember` | `DELETE .../members/{..}` |

**Portal パネル**: `src/components/admin/LocalUserManager.tsx` (新規)  
**カテゴリ**: Access Control (🔐)  
**追加先**: `ResourceManagement.tsx` の panels 配列に `localUsers` を追加

---

### 3. ボリューム管理 ✅ 実装済み

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `Get-NcVol` | ボリューム一覧 | `listVolumes` | `GET /storage/volumes` |
| `New-NcVol` | 「ボリューム作成」 | `createVolume` | `POST /storage/volumes` |
| `Remove-NcVol` | 「削除」ボタン | `deleteVolume` | `PATCH (offline) + DELETE` |
| `Set-NcVolSize` | 「リサイズ」ボタン | `resizeVolume` | `PATCH /storage/volumes/{uuid}` |
| `Mount-NcVol` | — (作成時に自動) | (createVolume 内) | `nas.path` 指定 |
| `Get-NcVolSpace` | 使用率バー表示 | (listVolumes に含む) | `fields=space` |

**Portal パネル**: `src/components/admin/VolumeManager.tsx`  
**カテゴリ**: Storage (🗄️)

---

### 4. スナップショット管理 ✅ 実装済み

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `Get-NcSnapshot` | スナップショット一覧 | `listSnapshots` | `GET /storage/volumes/{uuid}/snapshots` |
| `New-NcSnapshot` | 「作成」ボタン | `createSnapshot` | `POST .../snapshots` |
| `Remove-NcSnapshot` | 「削除」ボタン | `deleteSnapshot` | `DELETE .../snapshots/{uuid}` |
| `Restore-NcSnapshotVolume` | 「クローン」ボタン | `cloneFromSnapshot` | `POST /storage/volumes` (clone) |
| `Get-NcSnapshotPolicy` | ポリシータブ | `listSnapshotPolicies` | `GET /storage/snapshot-policies` |
| `Set-NcSnapshotPolicy` | ポリシー割当 | `assignSnapshotPolicy` | `PATCH /storage/volumes/{uuid}` |

**Portal パネル**: `src/components/admin/SnapshotAdminManager.tsx`  
**カテゴリ**: Protection (🛡️)

---

### 5. エクスポートポリシー ✅ 実装済み

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `Get-NcExportPolicy` | ポリシー一覧 | `listExportPolicies` | `GET /protocols/nfs/export-policies` |
| `New-NcExportPolicy` | 「ポリシー作成」 | `createExportPolicy` | `POST /protocols/nfs/export-policies` |
| `Remove-NcExportPolicy` | 「削除」ボタン | `deleteExportPolicy` | `DELETE .../export-policies/{id}` |
| `Get-NcExportRule` | ルール展開表示 | `getExportPolicyRules` | `GET .../rules` |
| `New-NcExportRule` | 「ルール追加」 | `createExportPolicyRule` | `POST .../rules` |
| `Remove-NcExportRule` | 「ルール削除」 | `deleteExportPolicyRule` | `DELETE .../rules/{index}` |

**Portal パネル**: `src/components/admin/ExportPolicyManager.tsx`  
**カテゴリ**: Access Control (🔐)

---

### 6. FlexClone ⚠️ 部分実装

| PSTK Cmdlet | Portal UI 操作 | Lambda action | REST API |
|-------------|---------------|---------------|----------|
| `New-NcClone` | スナップからのクローン | `cloneFromSnapshot` | `POST /storage/volumes` |
| `Get-NcClone` | — (Phase 2) | — | `GET /storage/volumes?clone.is_flexclone=true` |
| `Split-NcClone` | — (Phase 2) | — | `PATCH .../clone.split_initiated=true` |

**現状**: スナップショットパネルから「クローン」ボタンで FlexClone 可能。独立した FlexClone パネル（任意のスナップ選択 + 分割操作）は Phase 2。

---

### 7-14. 未実装カテゴリ (Phase 2-3 候補)

| カテゴリ | 優先度 | Portal 追加時の配置先 | 理由 |
|---------|:------:|---------------------|------|
| FlexClone (独立) | Phase 2 | Storage カテゴリ | 開発環境プロビジョニング需要 |
| FPolicy | Phase 3 | Protection カテゴリ | 専門的。DLP/監査向け |
| Vscan | Phase 3 | Protection カテゴリ | Sophos/CrowdStrike 連携向け |
| SnapMirror 状態 | Phase 3 | Protection カテゴリ | DR 状態可視化 |
| ネームマッピング | Phase 3 | Access Control | マルチプロトコル環境限定 |
| CIFSセッション監視 | Phase 3 | Monitoring | リアルタイムユーザ確認 |

---

## PSTK 専用ユースケース (Portal では代替不可)

以下のユースケースは、バッチ処理や既存スクリプト互換の観点から EC2 PSTK 環境が適する:

| ユースケース | 理由 |
|-------------|------|
| オンプレからの共有設定一括移行 | 現行サーバーへの CIM セッション + FSx for ONTAP への PSTK 接続を同一スクリプトで実行 |
| 数百ユーザの一括バルク作成 (CSV) | CLI/スクリプトのループ処理が効率的 |
| 既存 PSTK スクリプトのそのままの移行 | コマンド互換性を活かす |
| スケジュール実行 (タスクスケジューラ) | EC2 上で定期実行 |
| 他システム連携 (AD PowerShell + ONTAP PSTK) | 同一 PS セッション内で複数システム操作 |

これらのケースには `infrastructure/pstk-automation/` の EC2 テンプレートを使用する。

---

## architecture/pstk-automation/ テンプレートの位置づけ

```
┌─────────────────────────────────────────────────────────────────┐
│ ユーザのアクセスパターン                                           │
├───────────────────────────────┬─────────────────────────────────┤
│ Web UI (ブラウザ)              │ スクリプト/バッチ (CLI)           │
│                               │                                 │
│ Amplify Portal                │ EC2 Windows (PSTK)              │
│ ├─ ResourceManagement         │ ├─ 対話的操作 (RDP/SSM)          │
│ │  ├─ VolumeManager           │ ├─ バッチスクリプト              │
│ │  ├─ CifsShareManager        │ ├─ 一括移行ツール               │
│ │  ├─ LocalUserManager 🆕     │ └─ 定期実行タスク               │
│ │  ├─ ExportPolicyManager     │                                 │
│ │  ├─ SnapshotAdminManager    │  infrastructure/pstk-automation │
│ │  └─ ...                     │  └─ template.yaml (EC2 mode)    │
│ │                             │                                 │
│ └─ Python Lambda              │  PowerShell Toolkit             │
│    └─ ONTAP REST API ──────┐ │     └─ ONTAP REST API ────┐    │
│                             │ │                            │    │
└─────────────────────────────┼─┴────────────────────────────┼────┘
                              │                              │
                              ▼                              ▼
                    ┌─────────────────────────────┐
                    │ FSx for ONTAP               │
                    │ Management Endpoint (HTTPS) │
                    └─────────────────────────────┘
```

**結論**: Portal と PSTK は同じ FSx for ONTAP 管理エンドポイントに対して異なるクライアント手法でアクセスするだけ。機能的には等価。UI ユーザには Portal、スクリプト派には PSTK EC2 を提供する。
