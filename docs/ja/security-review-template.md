# セキュリティレビューテンプレート — ファイルポータル

> 🌐 **Language / 言語**: 日本語 | [English](../en/security-review-template.md)

> 本番デプロイ前に CISO / セキュリティチームの承認を得るための、1 ページのサインオフ文書です。

---

## プロジェクト情報

| 項目 | 内容 |
|-------|-------|
| アプリケーション名 | FSx for ONTAP File Portal |
| 環境 | ☐ サンドボックス / ☐ ステージング / ☐ 本番 |
| レビュー実施日 | YYYY-MM-DD |
| レビュー担当者の役割 | （例: セキュリティアーキテクト、CISO） |
| スタック名 | `amplify-<project>-<env>-<hash>` |
| リージョン | ap-northeast-1 |

---

## 実装済みのセキュリティ統制

| 統制 | 状態 | エビデンス |
|---------|:---:|---------|
| **認証**：Cognito User Pool（メール + パスワード、または外部 IdP） | ☐ | User Pool ID: |
| **認可**：AppSync のスキーマレベルのグループ認可（`storage-admin`） | ☐ | スキーマファイル: `amplify/data/resource.ts` |
| **保存時の暗号化**：FSx for ONTAP の KMS、DynamoDB SSE、S3 SSE-S3 | ☐ | AWS 管理 |
| **転送時の暗号化**：HTTPS（AppSync、S3 AP）、TLS 1.2 以上 | ☐ | AWS が強制 |
| **シークレット管理**：ONTAP 資格情報を Secrets Manager で管理 | ☐ | Secret ARN: |
| **ネットワーク分離**：VPC Lambda をプライベートサブネットに配置、パブリック IP なし | ☐ | VPC ID: |
| **IAM 最小権限**：特定のリソース ARN に限定 | ☐ | `backend.ts` のインラインポリシーを確認 |
| **ログ**：CloudWatch Logs（Lambda）、CloudTrail（S3 データイベント） | ☐ | ログ保持期間: 日 |
| **監視**：CloudWatch アラーム（Lambda エラー、レイテンシ） | ☐ | アラーム ARN: |
| **データ分類**：PHI パスを AI 処理から除外 | ☐ | FileExplorer.tsx の `isPhiPath()` |
| **Object Lock**：保持ポリシーを設定した S3 出力バケット | ☐ | バケット: |

---

## 残存リスク

| リスク | 発生可能性 | 影響 | 緩和策 | 受容? |
|------|:---:|:---:|-----------|:---:|
| Lambda の SG が FSx の SG を共有（広範なアウトバウンド） | 中 | 低 | 本番チェックリストで分離を推奨 | ☐ |
| IAM の `resources: ["*"]`（サンドボックスの既定値） | 高（サンドボックス） | 中 | チェックリストに従い特定 ARN に限定 | ☐ |
| GraphQL Introspection が有効 | 低 | 低 | 本番では AppSync コンソールで無効化 | ☐ |
| AppSync エンドポイントに WAF なし | 中 | 中 | レート制限付きの AWS WAF を追加 | ☐ |
| Cognito MFA が未強制（既定値） | 中 | 高 | Cognito 設定で MFA を有効化 | ☐ |
| クロスリージョン推論（Bedrock） | 低 | 中 | 単一リージョンの推論プロファイルに固定 | ☐ |

---

## 受け入れ基準

サインオフの前に、次を確認してください。

- [ ] 上記の「状態」チェックボックスがすべてチェック済み（統制を検証済み）
- [ ] 「受容?」の残存リスクがすべて明示的に受容済み、または緩和済み
- [ ] [GETTING-STARTED.md](../../solutions/amplify-portal/docs/GETTING-STARTED.md) の本番チェックリスト（13 項目）に従っている
- [ ] `CDK_NAG=1` の実行で、新規の未抑制の検出事項が発生しない
- [ ] ペネトレーションテストが予定済み（または理由を付して免除）
- [ ] インシデント対応 runbook をレビュー済み（[ARP 分離ガイド](./arp-ai-isolation-demo-guide.md)）
- [ ] S3 AP 経由でアクセス可能なすべてのボリュームにデータ分類ポリシーを適用済み

---

## サインオフ

| 役割 | 氏名 | 日付 | 署名 |
|------|------|------|-----------|
| セキュリティレビュー担当 | | | |
| システムオーナー | | | |
| CISO（必要な場合） | | | |

---

## 参考資料

- [本番チェックリスト](../../solutions/amplify-portal/docs/GETTING-STARTED.md#本番移行チェックリスト)
- [認可モデル](./portal-authorization-model.md)
- [外部 IdP セットアップ](./external-idp-setup.md)
- [Well-Architected レビュー](./well-architected-review.md)
