# ポータル認可設計 — ロールベースアクセス制御

> 🌐 言語: **日本語** | [English](../en/portal-authorization-design.md)

FSx for ONTAP ファイルポータルの認可モデルを定義します。ユーザーロールがファイル操作・AI 処理・データ保護管理の各機能にどのようにマッピングされるかを記載。

---

## 設計原則

1. **デフォルトは最小権限**: 新規ユーザーは Viewer。管理機能には明示的なグループ所属が必要。
2. **データアクセスとインフラ管理の分離**: ファイル閲覧 (S3 AP) とストレージ管理 (ONTAP REST API) は分離。
3. **多層防御**: Cognito グループ → AppSync resolver → Lambda IAM の 3 層で認可。
4. **監査可能**: 全管理操作はログ記録 (CloudTrail + DynamoDB)。

---

## ロール定義

| ロール | Cognito グループ | 権限 | 用途 |
|--------|---------------|------|------|
| **Viewer** | (デフォルト) | 閲覧、プレビュー、ダウンロード、AI Q&A | エンドユーザー、アナリスト |
| **Contributor** | `contributor` | Viewer + アップロード、タグ、お気に入り | チームメンバー |
| **Storage Admin** | `storage-admin` | 全権限 (Snapshot 管理、Lock 設定、ARP 制御) | ストレージエンジニア |
| **Auditor** | `auditor` | 閲覧 + 監査証跡 + コンプライアンスレポート | コンプライアンス担当 |

---

## Data Protection 権限マトリクス

| 操作 | Viewer | Contributor | Storage Admin | API |
|------|:---:|:---:|:---:|---|
| Snapshot 一覧表示 | ✅ | ✅ | ✅ | ONTAP REST GET |
| Snapshot 手動作成 | ❌ | ❌ | ✅ | ONTAP REST POST |
| Snapshot 削除 | ❌ | ❌ | ✅ | ONTAP REST DELETE |
| ARP 状態表示 | ❌ | ❌ | ✅ | ONTAP REST GET |
| ARP 有効化/無効化 | ❌ | ❌ | ✅ | ONTAP REST PATCH |
| SnapLock 設定表示 | ❌ | ❌ | ✅ | ONTAP REST GET |
| SnapLock Retention 変更 | ❌ | ❌ | ✅ | ONTAP REST PATCH |
| S3 Object Lock 表示 | ❌ | ❌ | ✅ | AWS S3 GET |
| S3 Object Lock 設定変更 | ❌ | ❌ | ✅ | AWS S3 PUT |

---

## Cognito グループ設定

```bash
USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

aws cognito-idp create-group --group-name storage-admin --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name contributor --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name auditor --user-pool-id $USER_POOL_ID

aws cognito-idp admin-add-user-to-group \
  --user-pool-id $USER_POOL_ID \
  --username "admin@example.com" \
  --group-name storage-admin
```

---

## セキュリティ上の注意

- **Storage Admin は高特権**: ARP 無効化（保護解除）、Snapshot 削除（データ損失）、Retention 変更（コンプライアンスリスク）が可能。慎重に割り当てること。
- **SnapLock Compliance モードの変更は不可逆**: 一度設定した Retention は短縮できない。UI で明示的な警告ダイアログを表示。
- **ARP 無効化にはクーリング期間**: ONTAP は完全無効化前に学習を一時停止する。UI で状態遷移を明確に表示。
- **全管理操作を監査**: Data Protection の mutation は全て監査証跡に記録（Lambda handler 内で強制）。

---

## 関連ドキュメント

- [S3 AP 認可モデル](../s3ap-authorization-model.md)
- [CONFIDENTIAL ガードレール (F-2)](../../solutions/amplify-portal/README.md)
- [デプロイ運用手順書](./portal-deployment-runbook.md)
