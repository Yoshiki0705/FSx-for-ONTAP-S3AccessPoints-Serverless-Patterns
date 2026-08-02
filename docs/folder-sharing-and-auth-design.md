# フォルダー共有 + 認証連携 設計ガイド

> ファイルポータルのフォルダー共有機能と AD/OIDC 認証統合の設計ドキュメント。

## 概要: 2つの共有方式

| 方式 | 対象 | 認証 | 有効期限 | 実装状態 |
|------|------|:---:|:---:|:---:|
| **案 A: フォルダーリンク** | 社内（認証済みユーザー） | ✅ 必要 | なし（常時有効） | ✅ 実装済み |
| **案 B: ZIP + Presigned URL** | 外部（認証不要） | ❌ 不要 | 最大 1 時間 | 📋 設計完了・次セッション実装 |

---

## 案 A: フォルダーリンク（実装済み）

### 仕組み

URL に `?path=` パラメータを付与し、ポータルの特定フォルダーに直接遷移する。

```
https://portal.example.com/#files?path=claims/photos/2026/05/
```

### 操作方法

1. ファイルブラウザでフォルダーに移動
2. 「📂🔗 フォルダリンクをコピー」ボタンをクリック
3. クリップボードにコピーされた URL を共有相手に送信
4. 受信者は URL をクリック → Cognito 認証 → 該当フォルダーに直接遷移

### セキュリティ

- **認証必須**: Cognito にサインインしていないユーザーはアクセス不可
- **パス制御なし**: URL を知っていれば認証済みユーザーは誰でもアクセス可能
- **将来拡張**: Cognito グループベースのパスアクセス制御（RBAC）を追加可能

---

## 案 B: ZIP 生成 + Presigned URL（設計）

### アーキテクチャ

```
User clicks "Download Folder as ZIP"
  → AppSync Mutation (startFolderDownload)
  → Step Functions State Machine
    → Lambda 1: List objects in prefix (S3 AP ListObjectsV2)
    → Lambda 2: Stream objects → ZIP → S3 temp bucket
    → Lambda 3: Generate Presigned URL for ZIP file
  → AppSync Subscription → UI shows download link
```

### コンポーネント

| コンポーネント | 説明 |
|--------------|------|
| `FolderDownload.tsx` | UI: フォルダーのダウンロードボタン + 進捗表示 |
| `folder-download/handler.py` | Lambda: S3 AP ListObjectsV2 → ZIP 生成 → S3 保存 |
| `template.yaml` (追加リソース) | S3 バケット（ZIP 一時保存、1日 TTL）+ Step Functions |

### 制限事項

- **最大フォルダーサイズ**: ~500MB（Lambda 15分タイムアウト + `/tmp` 10GB）
- **大容量フォルダー**: ECS Fargate タスクにフォールバック（Phase 2）
- **ZIP 有効期限**: Presigned URL と同じ（最大 1 時間）
- **同時ダウンロード**: Step Functions の並列数で制御

### ONTAP REST API

ZIP 生成には S3 AP 経由のファイルアクセスが必要:
```python
# フォルダー内ファイル一覧
s3.list_objects_v2(Bucket=s3ap_alias, Prefix=folder_prefix)

# 各ファイルをストリーム取得 → ZIP に追加
for obj in objects:
    body = s3.get_object(Bucket=s3ap_alias, Key=obj["Key"])["Body"]
    zip_file.writestr(obj["Key"], body.read())
```

### 実装タスク（次セッション）

- [ ] `functions/folder-download/handler.py` — ZIP 生成 Lambda
- [ ] S3 バケット（zip-temp）定義を template.yaml に追加
- [ ] `FolderDownload.tsx` — UI コンポーネント
- [ ] AppSync mutation + subscription 定義
- [ ] DemoMode 対応（ONTAP 未接続時のモック）

---

## AD/OIDC 認証連携（設計）

### 現状

- 現在のポータルは **Cognito メール/パスワード認証のみ**
- Amplify Gen2 の `auth` リソースでデフォルト設定

### 目標

[FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) と同等の認証柔軟性を持たせる:

| モード | IdP | 用途 |
|--------|-----|------|
| メール/パスワード | Cognito 直接 | PoC・デモ（現状） |
| AD Federation (SAML) | AWS Managed AD / Self-managed AD | エンタープライズ |
| OIDC Federation | Keycloak / Okta / Auth0 / Entra ID | マルチ IdP |
| SAML + OIDC ハイブリッド | AD + OIDC 同時 | 段階的移行 |

### Amplify Gen2 での実装方針

Amplify Gen2 では `defineAuth()` で外部 IdP を追加できる:

```typescript
// amplify/auth/resource.ts
import { defineAuth } from "@aws-amplify/backend";

export const auth = defineAuth({
  loginWith: {
    email: true,
    externalProviders: {
      oidc: [{
        name: "EntraID",
        clientId: secret("OIDC_CLIENT_ID"),
        clientSecret: secret("OIDC_CLIENT_SECRET"),
        issuerUrl: "https://login.microsoftonline.com/{tenant-id}/v2.0",
        scopes: ["openid", "profile", "email"],
        attributeMapping: {
          email: "email",
          fullname: "name",
          custom: {
            "custom:groups": "groups",
          },
        },
      }],
      saml: [{
        name: "ActiveDirectory",
        metadata: {
          metadataContent: "...", // or metadataType: "URL"
        },
      }],
      callbackUrls: ["http://localhost:5173/", "https://portal.example.com/"],
      logoutUrls: ["http://localhost:5173/", "https://portal.example.com/"],
    },
  },
});
```

### Post-Authentication Trigger（権限自動取得）

RAG プロジェクトの `Identity Sync Lambda` パターンを流用:

```
OIDC/SAML Sign-in → Cognito Post-Auth Trigger → Identity Sync Lambda
  → AD (LDAP/SSM) or OIDC Claims → DynamoDB user-access table
  → 次回 API 呼び出し時に権限情報を使用
```

### 実装タスク（次セッション）

- [ ] `amplify/auth/resource.ts` に OIDC/SAML 設定を追加
- [ ] `portal-config.ts` に認証モード設定を追加（フィーチャーフラグ）
- [ ] サインイン画面に IdP ボタンを動的表示
- [ ] Post-Authentication Trigger Lambda 実装
- [ ] Cognito グループ ↔ ONTAP ACL マッピング（オプション）
- [ ] ドキュメント: 認証モード別セットアップガイド

### 参考実装

- [FSx-for-ONTAP-Agentic-Access-Aware-RAG: auth-and-user-management.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG/blob/main/docs/auth-and-user-management.md)
- パターン C (OIDC + LDAP)、パターン D (OIDC Claims Only)、パターン E (SAML + OIDC ハイブリッド) が直接参考になる

---

## 関連ドキュメント

- [Portal Tabs Guide](../solutions/amplify-portal/docs/portal-tabs-guide.md) — 共有リンク操作ガイド
- [Tamperproof Snapshot Design](tamperproof-snapshot-design.md) — データ保護設計
- [Portal Authorization Model](en/portal-authorization-model.md) — 現在の認可モデル
