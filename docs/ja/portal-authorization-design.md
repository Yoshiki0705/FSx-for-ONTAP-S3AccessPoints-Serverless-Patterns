# ポータル認可設計 — ロールベースアクセス制御

> 🌐 言語: **日本語** | [English](../en/portal-authorization-design.md)

FSx for ONTAP ファイルポータルの認可モデルを定義します。ユーザーロールがファイル操作・AI 処理・データ保護管理の各機能にどのようにマッピングされるかを記載。

---

## 設計原則

1. **デフォルトは最小権限**: 新規ユーザーは Viewer。管理機能には明示的なグループ所属が必要。
2. **データアクセスとインフラ管理の分離**: ファイル閲覧 (S3 AP) とストレージ管理 (ONTAP REST API) は分離。
3. **多層防御**: Cognito グループ → AppSync resolver → バックエンド Lambda IAM の 3 層で認可。
4. **監査可能**: 全管理操作はログ記録 (CloudTrail + DynamoDB 監査)。

---

## ロール定義

| ロール | Cognito グループ | 権限 | 用途 |
|--------|---------------|------|------|
| **Viewer** | (デフォルト — グループなし) | ファイル閲覧、プレビュー、ダウンロード、AI Q&A、検索 | エンドユーザー、アナリスト |
| **Contributor** | `contributor` | Viewer + アップロード、タグ、お気に入り、コメント | チームメンバー、コンテンツ作成者 |
| **Storage Admin** | `storage-admin` | Contributor + Snapshot 管理、Lock 設定、ARP 制御 | ストレージエンジニア、プラットフォームチーム |
| **Audit** | `auditor` | Viewer + 監査証跡の参照、コンプライアンスレポート | コンプライアンス担当、セキュリティチーム |

---

## 権限マトリクス

### 閲覧とファイル操作

| 操作 | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| ファイル一覧・閲覧 | ✅ | ✅ | ✅ | ✅ |
| プレビュー (Presigned URL) | ✅ | ✅ | ✅ | ✅ |
| ダウンロード | ✅ | ✅ | ✅ | ✅ |
| 共有リンク生成 | ✅ | ✅ | ✅ | ❌ |
| アップロード | ❌ | ✅ | ✅ | ❌ |
| 削除 (ゴミ箱へ移動) | ❌ | ✅ | ✅ | ❌ |
| リネーム | ❌ | ✅ | ✅ | ❌ |
| ゴミ箱から復元 | ❌ | ✅ | ✅ | ❌ |

### AI と処理

| 操作 | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| AI Q&A (Bedrock) | ✅ | ✅ | ✅ | ❌ |
| セマンティック検索 | ✅ | ✅ | ✅ | ✅ |
| 処理ジョブの実行 | ❌ | ✅ | ✅ | ❌ |
| ジョブ結果・履歴の参照 | ✅ | ✅ | ✅ | ✅ |
| 分析 (Athena SQL) | ❌ | ✅ | ✅ | ✅ |

### Data Protection (参照)

| 操作 | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| Snapshot 一覧表示 | ✅ | ✅ | ✅ | ✅ |
| ARP/AI 状態表示 | ❌ | ❌ | ✅ | ✅ |
| SnapLock 設定表示 | ❌ | ❌ | ✅ | ✅ |
| S3 Object Lock 状態表示 | ❌ | ❌ | ✅ | ✅ |
| 監査証跡の参照 | ❌ | ❌ | ✅ | ✅ |

### Data Protection (更新) — Storage Admin のみ

| 操作 | API | バックエンド |
|-----------|-----|---------|
| Snapshot 手動作成 | ONTAP REST: `POST /storage/volumes/{uuid}/snapshots` | VPC Lambda |
| Snapshot 削除 | ONTAP REST: `DELETE /storage/volumes/{uuid}/snapshots/{uuid}` | VPC Lambda |
| Snapshot ポリシー更新 | ONTAP REST: `PATCH /storage/snapshot-policies/{uuid}` | VPC Lambda |
| ARP 有効化/無効化 | ONTAP REST: `PATCH /storage/volumes/{uuid}` (anti_ransomware.state) | VPC Lambda |
| ARP 疑いの承認 | ONTAP REST: `DELETE /security/anti-ransomware/suspects/{uuid}` | VPC Lambda |
| SnapLock Retention 更新 | ONTAP REST: `PATCH /storage/volumes/{uuid}` (snaplock.retention) | VPC Lambda |
| S3 Object Lock 設定 | AWS S3: `PutObjectLockConfiguration` | 標準 Lambda |
| Object Retention 設定 | AWS S3: `PutObjectRetention` | 標準 Lambda |
| Legal Hold 設定 | AWS S3: `PutObjectLegalHold` | 標準 Lambda |

---

## 実装アーキテクチャ

```
                     Cognito User Pool
                    ┌─────────────────┐
                    │ Groups:         │
                    │ - contributor   │
                    │ - storage-admin │
                    │ - auditor       │
                    └────────┬────────┘
                             │ JWT (cognito:groups claim)
                             ▼
                    ┌─────────────────┐
                    │ AppSync API     │
                    │                 │
                    │ Query (viewer)  │──→ allow.authenticated()
                    │ Mutation (write)│──→ allow.groups(["storage-admin"])
                    │ Audit queries   │──→ allow.groups(["storage-admin","auditor"])
                    └────────┬────────┘
                             │
               ┌─────────────┴──────────────┐
               ▼                             ▼
    ┌──────────────────┐          ┌──────────────────┐
    │ VPC Lambda        │          │ Standard Lambda   │
    │ (ONTAP REST API)  │          │ (AWS S3 API)      │
    │                   │          │                   │
    │ IAM Role:         │          │ IAM Role:         │
    │ - SecretsManager  │          │ - s3:Put*Lock*    │
    │ - VPC access      │          │ - s3:Put*Retention│
    └──────────────────┘          └──────────────────┘
```

---

## AppSync 認可パターン

### 参照系（認証済みユーザー全員）

```typescript
listSnapshots: a.query()
  .authorization((allow) => [allow.authenticated()])
```

### 更新系（storage-admin のみ）

```typescript
createSnapshot: a.mutation()
  .authorization((allow) => [allow.groups(["storage-admin"])])

updateArpState: a.mutation()
  .authorization((allow) => [allow.groups(["storage-admin"])])
```

### 監査系（storage-admin + auditor）

```typescript
queryAuditLog: a.query()
  .authorization((allow) => [
    allow.groups(["storage-admin", "auditor"]),
  ])
```

---

## Cognito グループ設定

```bash
USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

# グループ作成
aws cognito-idp create-group --group-name storage-admin --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name contributor --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name auditor --user-pool-id $USER_POOL_ID

# ユーザーをグループに追加
aws cognito-idp admin-add-user-to-group \
  --user-pool-id $USER_POOL_ID \
  --username "admin@example.com" \
  --group-name storage-admin
```

---

## ロール別の UI 挙動

| 要素 | Viewer | Contributor | Storage Admin |
|---------|--------|-------------|---------------|
| サイドバー: 閲覧セクション | ✅ 全項目 | ✅ 全項目 | ✅ 全項目 |
| サイドバー: アップロード | 非表示 | ✅ 表示 | ✅ 表示 |
| サイドバー: AI 処理 | 結果参照のみ | ✅ 実行 + 参照 | ✅ フルアクセス |
| サイドバー: Data Protection | Snapshot (参照) | Snapshot (参照) | ✅ 参照・更新とも可 |
| サイドバー: 管理 | 非表示 | 非表示 | ✅ 表示 |
| ファイル: アップロード/削除/リネーム | 無効 | ✅ 有効 | ✅ 有効 |
| Data Protection: 「Snapshot 作成」ボタン | 非表示 | 非表示 | ✅ 表示 |
| Data Protection: 「ARP 有効化」トグル | 非表示 | 非表示 | ✅ 表示 |
| Lock: 「Retention 更新」フォーム | 非表示 | 非表示 | ✅ 表示 |

---

## セキュリティ上の注意

- **Storage Admin は高特権**: ARP 無効化（保護解除）、Snapshot 削除（データ損失）、Retention 変更（コンプライアンスリスク）が可能。慎重に割り当てること。
- **SnapLock Compliance モードの変更は不可逆**: 一度設定した Retention は短縮できない。UI で明示的な警告を伴う確認ダイアログを表示すること。
- **ARP 無効化にはクーリング期間**: ONTAP は完全無効化前に学習のため ARP を一時停止する。UI で状態遷移を明確に表示すること。
- **全管理操作を監査**: Data Protection の mutation は全て監査証跡に記録する（誰が・何を・いつ）。Lambda handler 内で強制。

---

## 関連ドキュメント

- [S3 AP 認可モデル](../s3ap-authorization-model.md) — S3 AP File System Identity + IAM の二層構造
- [CONFIDENTIAL ガードレール (F-2)](../../solutions/amplify-portal/README.md) — データ分類に基づく AI ブロック
- [Cognito グループ → S3 AP ルーティング (A-1)](../../solutions/amplify-portal/README.md) — チーム単位のファイル分離
