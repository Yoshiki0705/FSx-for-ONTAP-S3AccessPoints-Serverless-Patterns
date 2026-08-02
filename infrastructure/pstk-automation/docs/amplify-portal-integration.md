# PSTK × Amplify Portal 統合方針

> 重複 UI を作らず、既存 Portal の機能拡張として PSTK 相当の操作を実装する方針

---

## 方針決定の経緯

当初「ONTAP Automation」という独立ページを Portal に追加する設計だったが、
既存の `ResourceManagement` コンポーネントを精査した結果、提案機能の **約 80%** が既に実装済みと判明。

**結論**: 独立ページではなく、既存パネルへの機能追加 + 未実装カテゴリの追加で対応する。

---

## 既存 Portal カバレッジ（実装済み）

| PSTK カテゴリ | Portal パネル | ファイル |
|-------------|-------------|---------|
| CIFS/SMB 共有 | `CifsShareManager` | `src/components/admin/CifsShareManager.tsx` |
| ボリューム | `VolumeManager` | `src/components/admin/VolumeManager.tsx` |
| スナップショット | `SnapshotAdminManager` | `src/components/admin/SnapshotAdminManager.tsx` |
| エクスポートポリシー | `ExportPolicyManager` | `src/components/admin/ExportPolicyManager.tsx` |
| Qtree | `QtreeManager` | `src/components/admin/QtreeManager.tsx` |
| QoS | `QosPolicyManager` | `src/components/admin/QosPolicyManager.tsx` |
| SnapLock | `SnaplockManager` | `src/components/admin/SnaplockManager.tsx` |
| クォータ | `QuotaManager` | `src/components/admin/QuotaManager.tsx` |
| ARP/ランサムウェア | `ArpAdminManager` | `src/components/admin/ArpAdminManager.tsx` |
| ストレージ効率 | `EfficiencyPanel` | `src/components/admin/EfficiencyPanel.tsx` |

---

## 今回追加した機能

### ローカルユーザ/グループ管理 (localUsers)

**PSTK 等価**: `New-NcCifsLocalUser`, `New-NcCifsLocalGroup`, `Add-NcCifsLocalGroupMember` 等

| レイヤー | ファイル | 変更内容 |
|---------|---------|---------|
| Backend | `functions/resource-management/handler.py` | 9 アクション追加 (listLocalUsers, createLocalUser, deleteLocalUser, listLocalGroups, createLocalGroup, deleteLocalGroup, listGroupMembers, addGroupMember, removeGroupMember) |
| Frontend | `src/components/admin/LocalUserManager.tsx` | 新規コンポーネント（Users/Groups タブ、CRUD、メンバー管理） |
| Integration | `src/components/ResourceManagement.tsx` | `localUsers` パネルを Access Control カテゴリに追加 |
| i18n | 8 locale files | `lu*` キー 36 個追加 (ja/en/ko/zh-CN/zh-TW/fr/de/es) |

**UI の配置**:
```
Resource Management → Access Control (🔐)
├── エクスポートポリシー
├── SMB 共有
├── ローカルユーザ  ← 新規追加
└── QoS ポリシー
```

---

## 今後の追加候補 (Phase 2-3)

| カテゴリ | 優先度 | 追加先 | 実装内容 |
|---------|:------:|--------|---------|
| CIFS 共有 ACL 編集 | Phase 2 | `CifsShareManager` 拡張 | ACE 追加/削除 UI |
| FlexClone (独立) | Phase 2 | Storage カテゴリ新パネル | 任意スナップからクローン + 分割 |
| FPolicy | Phase 3 | Protection カテゴリ新パネル | ポリシー/イベント設定 |
| Vscan | Phase 3 | Protection カテゴリ新パネル | スキャナプール設定 |
| SnapMirror 状態 | Phase 3 | Protection カテゴリ新パネル | レプリケーション状態可視化 |
| ネームマッピング | Phase 3 | Access Control 新パネル | win↔unix マッピングルール |
| CIFS セッション監視 | Phase 3 | Monitoring 新カテゴリ | リアルタイム接続ユーザ |

---

## PSTK EC2 環境との棲み分け

| 利用シーン | 推奨手段 |
|-----------|---------|
| 日常の単発操作（共有作成、ユーザ追加等） | **Portal UI** |
| 数十〜数百件のバルク作成 | **EC2 PSTK** (CSV ループ) |
| オンプレからの共有設定一括移行 | **EC2 PSTK** (CIM + PSTK 併用) |
| 既存 PowerShell スクリプトの移行 | **EC2 PSTK** (コマンド互換) |
| CI/CD パイプライン統合 | **REST API** (Python/curl) |
| AD PowerShell + ONTAP 同時操作 | **EC2 PSTK** (同一セッション) |
| モバイル/外出先からの緊急操作 | **Portal UI** |

**テンプレート**: `infrastructure/pstk-automation/template.yaml` (EC2 mode)

---

## 技術的詳細

### API 呼び出しパターン（フロントエンド）

```typescript
// ローカルユーザ一覧取得
const response = await (client.queries as any).adminQuery({
  action: "listLocalUsers",
  params: JSON.stringify({}),
});
const data = parseResponse<{ users: LocalUser[]; error?: string }>(response);

// ユーザ作成
const response = await (client.mutations as any).adminMutation({
  action: "createLocalUser",
  params: JSON.stringify({
    name: "testuser1",
    password: "P@ssw0rd123",
    fullName: "Test User 1",
    description: "Engineering team",
  }),
});
```

### ONTAP REST API エンドポイント

| action | HTTP | Endpoint |
|--------|------|----------|
| `listLocalUsers` | GET | `/api/protocols/cifs/local-users?svm.name={svm}` |
| `createLocalUser` | POST | `/api/protocols/cifs/local-users` |
| `deleteLocalUser` | DELETE | `/api/protocols/cifs/local-users/{svm_uuid}/{sid}` |
| `listLocalGroups` | GET | `/api/protocols/cifs/local-groups?svm.name={svm}` |
| `createLocalGroup` | POST | `/api/protocols/cifs/local-groups` |
| `deleteLocalGroup` | DELETE | `/api/protocols/cifs/local-groups/{svm_uuid}/{sid}` |
| `listGroupMembers` | GET | `/api/protocols/cifs/local-groups/{svm_uuid}/{sid}/members` |
| `addGroupMember` | POST | `/api/protocols/cifs/local-groups/{svm_uuid}/{sid}/members` |
| `removeGroupMember` | DELETE | `/api/protocols/cifs/local-groups/{svm_uuid}/{sid}/members/{name}` |

### 認可

- Cognito グループ: `storage-admin` 必須（`adminQuery` / `adminMutation` エンドポイント経由）
- ONTAP 認証: Lambda が Secrets Manager から `fsxadmin` 認証情報を取得

---

## 関連ドキュメント

- [PSTK 操作カタログ](pstk-action-catalog.md) — 全 60+ コマンドレット一覧
- [PSTK ↔ Portal マッピング](pstk-portal-mapping.md) — 対応表
- [Portal IMPLEMENTATION.md](../../../solutions/amplify-portal/docs/IMPLEMENTATION.md) — Portal 設計意図
