# ファイルポータル — PoC から本番への移行ガイド

> DemoMode での評価から、本番 FSx for ONTAP 接続への移行手順。

## 概要

本ガイドでは、DemoMode（通常の S3 バケット利用）から本番デプロイ（FSx for ONTAP 接続）への移行手順を説明します。DemoMode は UI とワークフローの評価用に設計されています。本番モードでは ONTAP 管理機能、ファイルレベルのアクセス制御、データ保護機能が有効になります。

---

## 前提条件

| コンポーネント | バージョン | 確認方法 |
|---------|---------|-------|
| Node.js | 20.x 以上 | `node --version` |
| npm | 10.x 以上 | `npm --version` |
| AWS CLI | 2.x | `aws --version` |
| Amplify CLI | 最新版 | `npx ampx --version` |
| FSx for ONTAP | ファイルシステム稼働中 | コンソールまたは `aws fsx describe-file-systems` |
| SVM | 管理 LIF を持つ SVM が 1 つ以上 | `aws fsx describe-storage-virtual-machines` |
| S3 Access Point | ボリュームにアタッチ済み | `aws fsx describe-data-repository-associations` |

---

## 移行チェックリスト

### 1. ネットワーク設定

| 項目 | アクション | 確認 |
|------|--------|------|
| VPC ID | FSx コンソール → ネットワーク&セキュリティからコピー | `portal-config.ts` → `vpcId` |
| サブネット ID | FSx ENI と同じサブネット | `portal-config.ts` → `vpcSubnetIds` |
| セキュリティグループ | FSx の SG（デフォルトで全トラフィックエグレス許可） | `portal-config.ts` → `vpcSecurityGroupIds` |
| 接続テスト | VPC 内 Lambda が ONTAP 管理 LIF (443) に到達可能 | デプロイ → 管理パネルで確認 |

```typescript
// portal-config.ts — 本番値の設定例
export const portalConfig = {
  region: "ap-northeast-1",
  vpcId: "vpc-0xxxxxxxxxxxxxxxxx",           // ← 自環境の VPC
  vpcSubnetIds: ["subnet-0xxxxxxxxxxxxxxxxx"], // ← FSx ENI と同じサブネット
  vpcSecurityGroupIds: ["sg-0xxxxxxxxxxxxxxxxx"], // ← FSx の SG
  // ...
};
```

> **なぜ同じサブネットか？** VPC Lambda が ONTAP 管理 LIF へのネットワークパスを必要とするためです。FSx ENI と同じサブネットに配置するのが最もシンプルです。サブネットが異なる場合も、ルーティングと SG ルールで TCP 443 が許可されていれば動作します。

### 2. S3 Access Point

| 項目 | アクション | 確認 |
|------|--------|------|
| S3 AP エイリアス | Internet-origin の S3 AP エイリアスをコピー | `portal-config.ts` → `s3ApAlias` |
| ネットワークオリジン | `Internet` であること（`VPC` ではない） | `aws fsx describe-data-repository-associations` |
| ファイルシステム ID | ポータルアクセス用の UNIX ユーザー/グループ | ボリューム上の UID/GID パーミッションを確認 |

```typescript
  s3ApAlias: "your-ap-alias-xxxxxxxx-s3alias", // ← Internet-origin S3 AP
```

> **Internet-origin vs VPC**: ファイルブラウジング用 Lambda は VPC 外で動作します（Cold Start 高速化のため）。S3 AP にはパブリック S3 エンドポイント経由でアクセスします。VPC-origin AP を使う場合は Lambda を VPC 内に配置し NAT Gateway が必要になり、コストとレイテンシが増加します。

### 3. ONTAP 認証情報

| 項目 | アクション |
|------|--------|
| シークレット作成 | `aws secretsmanager create-secret --name portal/ontap-credentials --secret-string '{"username":"fsxadmin","password":"...","managementIp":"..."}'` |
| ARN 設定 | `portal-config.ts` → `ontapSecretArn` |
| IAM | Lambda 実行ロールに `secretsmanager:GetSecretValue` を付与 |

```typescript
  ontapSecretArn: "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:portal/ontap-credentials-XXXXXX",
```

> **セキュリティに関する補足**: 認証情報を `portal-config.ts` に直接記載しないでください。必ず Secrets Manager を使用してください。このファイルは Git にコミットされるため、シークレット値を含めてはいけません。

### 4. 認証設定

| 項目 | アクション |
|------|--------|
| MFA | Cognito User Pool 設定で TOTP を有効化 |
| 管理者グループ | `storage-admin` グループを作成し、管理者ユーザーを追加 |
| (任意) SSO | エンタープライズ IdP 用に SAML/OIDC フェデレーションを設定 |

デプロイ後（`npx ampx sandbox` または `git push`）:
1. Cognito コンソールでユーザーをサインアップ
2. ユーザーを `storage-admin` グループに追加
3. ポータルにサインイン → 管理パネルが表示される

### 5. 監査証跡

| 項目 | アクション |
|------|--------|
| CloudTrail | S3 AP ARN に対する S3 データイベントを有効にした Trail を作成 |
| Glue Crawler | CloudTrail の S3 バケットを指すクローラーを作成 |
| Athena | テーブルがクエリ可能か確認 |
| Lambda 環境変数 | `ATHENA_AUDIT_DATABASE`、`ATHENA_AUDIT_TABLE`、`ATHENA_AUDIT_OUTPUT` を設定 |

### 6. コスト確認

本番運用前に月額コストを見積もり:

| リソース | 概算 | 備考 |
|----------|------|------|
| FSx for ONTAP | ~$194+/月 | 128 MBps 最小構成 |
| VPC Lambda (Admin) | ~$5/月 | 呼び出し頻度は低い |
| CloudTrail S3 データイベント | ~$10–50/月 | ファイルアクセス量に比例 |
| Athena クエリ | $5/TB スキャン | 監査クエリは通常少量 |
| Secrets Manager | $0.40/シークレット/月 | ONTAP 認証情報 1 件 |
| Cognito | 無料枠 (50K MAU) | 社内チーム利用では通常無料 |

---

## デプロイ

```bash
# portal-config.ts に本番値を設定した後:
npx ampx sandbox  # まずサンドボックスでテスト

# 検証完了後:
git add amplify/portal-config.ts
git commit -m "feat: connect portal to production FSx for ONTAP"
git push origin main  # Amplify Hosting が自動デプロイ
```

---

## 確認

デプロイ後、各レイヤーを検証:

| チェック | 方法 | 期待結果 |
|---------|------|---------|
| ファイルブラウジング | All Files に遷移 | ボリュームの内容が表示される |
| 管理パネル | サイドバーの Resources をクリック | ボリューム/ARP/スナップショットのデータが表示 |
| EMS Events | Events パネルを開く | 最近の ONTAP イベントが表示 |
| Audit Log | Audit タブでクエリ実行 | CloudTrail イベントが返される |
| AI 処理 | ファイル選択 → AI 実行 | Step Functions ワークフローが完了 |

---

## ロールバック

| 状況 | ロールバック方法 |
|------|------|
| フロントエンド UI の問題 | Amplify Hosting コンソール → 前のビルドを再デプロイ |
| Lambda 関数の問題 | `git revert` + `git push`（自動デプロイ） |
| ONTAP 設定変更の問題 | ONTAP REST API で直接復元（export-policy, name-mapping 等） |
| Cognito 設定変更 | 手動復元（CDK スタックのロールバックは不可） |

> **重要**: ONTAP の一部操作（SnapLock 有効化等）は不可逆です。本番ボリュームで実行する前に、必ず DemoMode または非本番ボリュームで検証してください。

---

## 関連ドキュメント

- [Getting Started Guide](../../solutions/amplify-portal/docs/GETTING-STARTED.md)
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md)
- [Security Review](../../solutions/amplify-portal/docs/SECURITY-REVIEW.md)
- [スケーリングガイド](./portal-scaling-guide.md)
- [DemoMode ガイド](../demo-mode-guide.md)
