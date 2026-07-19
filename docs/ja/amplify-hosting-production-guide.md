# 本番 Amplify Hosting デプロイガイド

FSx for ONTAP ファイルポータルを、ブランチベース CI/CD・カスタムドメイン・エンタープライズ認証付きの本番 Web アプリケーションとしてデプロイする手順。

---

## 前提条件

| 項目 | 要件 |
|---|---|
| Amplify ポータル | `solutions/amplify-portal/` がローカルで動作すること（`npm run dev`） |
| GitHub リポジトリ | Fork またはクローン（push 権限あり） |
| FSx for ONTAP S3 AP | AVAILABLE、Internet origin |
| カスタムドメイン（任意） | Route53 ホストゾーンまたは外部 DNS |

---

## Step 1: 環境変数の設定

```bash
cp solutions/amplify-portal/amplify/portal-config.example.ts \
   solutions/amplify-portal/amplify/portal-config.ts
```

自環境のパラメータを設定:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",
  // 取得: aws fsx describe-s3-access-point-attachments --query '...Alias'
  s3ApAlias: "your-ap-alias-ext-s3alias",

  // 取得: aws stepfunctions list-state-machines --query '...stateMachineArn'
  stateMachineArn: "arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc1-workflow",
  stateMachineResourceScope: "arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc*",

  // 本番: 特定の S3 AP ARN にスコープ
  s3ApResourceArns: [
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name",
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name/object/*",
  ],
};
```

フロントエンド機能を有効化（`src/portal-settings.ts`）:

```typescript
export const portalSettings = {
  processingEnabled: true,
  fileListingEnabled: true,
};
```

---

## Step 2: Amplify Hosting に接続

### コンソールから

1. [Amplify コンソール](https://console.aws.amazon.com/amplify/) → **アプリを作成** → **Web アプリをホスト**
2. **GitHub** → 認証 → リポジトリ選択
3. ブランチ: `main`
4. ビルド設定は `amplify/` ディレクトリから自動検出
5. **保存してデプロイ**

### CLI から

```bash
cd solutions/amplify-portal
npx ampx pipeline-deploy --branch main --app-id <YOUR_APP_ID>
```

---

## Step 3: 環境変数（Amplify コンソール）

| 変数 | 値 | 確認方法 |
|---|---|---|
| `AMPLIFY_PORTAL_REGION` | `ap-northeast-1` | FSx for ONTAP と同じリージョン |
| `AMPLIFY_PORTAL_S3AP_ALIAS` | `your-ap-alias-ext-s3alias` | `aws fsx describe-s3-access-point-attachments` |
| `AMPLIFY_PORTAL_SFN_ARN` | `arn:aws:states:...` | `aws stepfunctions list-state-machines` |

設定場所: Amplify コンソール → アプリ設定 → 環境変数

---

## Step 4: カスタムドメイン（任意）

### Route53 の場合

1. Amplify コンソール → ドメイン管理 → ドメインを追加
2. Route53 ホストゾーンを選択
3. サブドメイン設定: `portal.example.com` → `main`
4. SSL 証明書は自動プロビジョニング

### 外部 DNS の場合

1. ドメイン名を入力
2. Amplify が提供する CNAME レコードを DNS に追加
3. 所有権検証 → 証明書プロビジョニング待ち

---

## Step 5: エンタープライズ認証（Cognito）

### SAML 連携（Okta, Azure AD 等）

`amplify/auth/resource.ts` に追加:

```typescript
externalProviders: {
  saml: {
    name: "CorporateSSO",
    metadata: {
      metadataContent: "https://your-idp.example.com/metadata.xml",
    },
    attributeMapping: {
      email: { attributeName: "email" },
      fullname: { attributeName: "displayName" },
    },
  },
  callbackUrls: ["https://portal.example.com/"],
  logoutUrls: ["https://portal.example.com/"],
},
```

---

## Step 6: 本番チェックリスト

| 項目 | アクション |
|---|---|
| IAM 最小権限 | `s3ApResourceArns` を特定 AP ARN にスコープ |
| SFn スコープ | `stateMachineResourceScope` を特定パターンにスコープ |
| Cognito MFA | MFA 有効化（推奨） |
| カスタムドメイン | HTTPS + Route53/外部 DNS |
| WAF（任意） | CloudFront に AWS WAF アタッチ |
| モニタリング | Lambda エラーの CloudWatch アラーム |
| コスト通知 | AWS Budgets でアラート設定 |

---

## コスト見積もり（本番、100 ユーザー）

| リソース | 月額 |
|---|---|
| Amplify Hosting | ~$5 |
| Cognito | 無料枠内（50K MAU 無料） |
| AppSync | ~$4 |
| Lambda | ~$2 |
| DynamoDB | ~$1 |
| **合計** | **~$12/月** |

> FSx for ONTAP のコストは別途（既存インフラ）。ポータルの追加コストは最小。

---

## ブランチベース環境

```
main   → 本番バックエンド（Cognito, AppSync, Lambda, DynamoDB）
dev    → 開発バックエンド（別の Cognito プール、別の DynamoDB）
feat/* → プレビュー環境（PR 作成時に自動デプロイ）
```

---

## トラブルシューティング

| 問題 | 原因 | 解決策 |
|---|---|---|
| ビルド失敗 "Cannot find module" | `portal-config.ts` 未作成 | `.example.ts` からコピーして設定 |
| ListFiles で AccessDenied | S3 AP alias 未設定 or IAM 不足 | `AMPLIFY_PORTAL_S3AP_ALIAS` 環境変数を確認 |
| Presigned URL エラー | Lambda に S3:GetObject 権限なし | `s3ApResourceArns` に AP ARN + `/object/*` を含めること |
| Cognito "redirect_mismatch" | コールバック URL 不一致 | auth 設定の `callbackUrls` を更新 |

---

## 関連ドキュメント

- [ローカル開発セットアップ](../../solutions/amplify-portal/README.md)
- [Storage Browser デモガイド](./storage-browser-demo-guide.md)
- [S3 AP 互換性ノート](../s3ap-compatibility-notes.en.md)
