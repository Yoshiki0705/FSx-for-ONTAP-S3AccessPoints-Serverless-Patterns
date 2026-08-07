# 外部 IdP セットアップ — SAML / OIDC フェデレーション

> 🌐 言語: **日本語** | [English](../en/external-idp-setup.md)

> ファイルポータルを組織の ID プロバイダー（AD FS、Okta、Azure AD など）と接続します

## 概要

ポータルは認証に Amazon Cognito User Pool を使用します。既定では、ユーザーは Cognito に直接メールアドレスとパスワードでサインアップします。エンタープライズおよびパブリックセクターでの導入では、SAML 2.0 または OIDC を介して外部 ID プロバイダー（IdP）とフェデレーションできます。

```
User → Cognito Hosted UI → External IdP (SAML/OIDC) → Cognito → AppSync
                                                              ↓
                                                     Group claim → storage-admin
```

## 前提条件

| 項目 | 必須 |
|------|:---:|
| Cognito User Pool（sandbox でデプロイ済み） | ✅ |
| 外部 IdP の構成済み（AD FS / Okta / Azure AD / Google Workspace） | ✅ |
| Cognito のカスタムドメイン（本番） | 推奨 |

## Step 1: Cognito コンソールで IdP を構成する

### Option A: SAML 2.0（AD FS、Okta）

1. IdP 側で新しい SAML アプリケーションを作成します。
   - **ACS URL**: `https://<cognito-domain>.auth.<region>.amazoncognito.com/saml2/idpresponse`
   - **Entity ID**: `urn:amazon:cognito:sp:<user-pool-id>`
   - **Name ID**: メールアドレス
   - **属性**: `groups` クレームを IdP のグループにマッピングします

2. IdP の SAML メタデータ XML をダウンロードします

3. Cognito コンソール → User Pool → Sign-in Experience → Federated sign-in で次を行います。
   - Add identity provider → SAML
   - メタデータ XML をアップロードします
   - 属性をマッピングします。
     - `email` → Cognito の `email`
     - `groups` → Cognito の `custom:groups`（または IdP からグループへのマッピングを使用）

### Option B: OIDC（Azure AD、Google Workspace）

1. Azure AD / Google Workspace で OAuth アプリケーションを登録します。
   - **Redirect URI**: `https://<cognito-domain>.auth.<region>.amazoncognito.com/oauth2/idpresponse`
   - **Scopes**: `openid email profile`
   - Client ID と Client Secret を記録します

2. Cognito コンソール → Federated sign-in で次を行います。
   - Add identity provider → OpenID Connect
   - プロバイダー名: `AzureAD`（または `GoogleWorkspace`）
   - 手順 1 の Client ID / Secret
   - Issuer URL: `https://login.microsoftonline.com/<tenant-id>/v2.0`
   - 属性マッピング: `email`、`name`、`groups`

## Step 2: IdP のグループを Cognito グループにマッピングする

ポータルは管理者アクセスに `storage-admin` の Cognito グループを使用します。お使いの IdP のグループをマッピングしてください。

| IdP グループ | Cognito グループ | ポータルのアクセス範囲 |
|-----------|--------------|---------------|
| `StorageAdmins` / `IT-Infrastructure` | `storage-admin` | 管理者権限すべて（ONTAP 操作） |
| `AllUsers` / `Everyone` | （認証済みユーザー） | 読み取り + AI 処理 |

### Lambda トリガーによるグループの自動割り当て

Cognito の Pre Token Generation Lambda トリガーを追加します。

```python
def handler(event, context):
    """Map IdP groups to Cognito groups in the token."""
    idp_groups = event["request"]["groupConfiguration"].get("groupsToOverride", [])

    # Map IdP group names to Cognito group names
    GROUP_MAPPING = {
        "StorageAdmins": "storage-admin",
        "IT-Infrastructure": "storage-admin",
        "NAS-Admins": "storage-admin",
    }

    cognito_groups = []
    for idp_group in idp_groups:
        if idp_group in GROUP_MAPPING:
            cognito_groups.append(GROUP_MAPPING[idp_group])

    event["response"]["claimsOverrideDetails"] = {
        "groupOverrideDetails": {
            "groupsToOverride": cognito_groups,
        }
    }
    return event
```

## Step 3: Amplify の認証設定を更新する

`amplify/auth/resource.ts` に外部プロバイダーを追加します。

```typescript
import { defineAuth } from "@aws-amplify/backend";

export const auth = defineAuth({
  loginWith: {
    email: true,
    externalProviders: {
      saml: {
        name: "CorporateADFS",
        metadata: {
          metadataContent: "https://adfs.example.com/FederationMetadata/2007-06/FederationMetadata.xml",
          metadataType: "URL",
        },
        attributeMapping: {
          email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
          preferredUsername: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        },
      },
      // OR for OIDC:
      // oidc: [{
      //   name: "AzureAD",
      //   clientId: "<client-id>",
      //   clientSecret: "<client-secret>",  // Use Secrets Manager in production
      //   issuerUrl: "https://login.microsoftonline.com/<tenant-id>/v2.0",
      //   attributeMapping: { email: "email", preferredUsername: "name" },
      // }],
      callbackUrls: ["http://localhost:5173/", "https://your-domain.com/"],
      logoutUrls: ["http://localhost:5173/", "https://your-domain.com/"],
    },
  },
  groups: ["storage-admin"],
});
```

## Step 4: フロントエンドのサインインを更新する

ポータルのサインインページは Amplify UI の `<Authenticator>` を使用しています。フェデレーションサインインを使う場合は、プロバイダーのボタンを追加します。

```typescript
// In App.tsx or auth wrapper
import { signInWithRedirect } from "aws-amplify/auth";

// Add button to sign-in page
<button onClick={() => signInWithRedirect({ provider: "CorporateADFS" })}>
  Sign in with Corporate SSO
</button>
```

## セキュリティに関する考慮事項

- **トークンの検証**: AppSync は Cognito が発行した JWT トークンを検証します。フェデレーションされたトークンには IdP のソース情報が含まれます。
- **グループクレーム**: SAML アサーションまたは OIDC トークンにグループメンバーシップが含まれるよう、IdP 側で設定してください。
- **MFA**: MFA は IdP 側で構成します（フェデレーションユーザーでは Cognito の MFA はバイパスされます）。
- **セッションの有効期間**: Cognito のトークン有効期間は設定可能です（既定: アクセストークン 1 時間、リフレッシュトークン 30 日）。

## 本ガイドが記載している IdP 構成

> ここに挙げたのは本ガイドが手順を記載している構成であり、実際に構築して
> 確認を取った構成ではありません。全行の状態が「ドキュメント化済み」なのはそのためです。
> 実際の IdP で構成を完了された場合は、該当行の状態と使用バージョンを更新いただけると
> 後続の方の役に立ちます。

| IdP | プロトコル | 状態 | 備考 |
|-----|----------|:---:|-------|
| AD FS（Windows Server 2019 以降） | SAML 2.0 | ドキュメント化済み | 標準的な SAML アプリ登録 |
| Okta | SAML 2.0 / OIDC | ドキュメント化済み | 両プロトコルに対応 |
| Azure AD（Entra ID） | OIDC | ドキュメント化済み | v2.0 エンドポイントを使用 |
| Google Workspace | OIDC | ドキュメント化済み | Admin Console のカスタム SAML アプリ |
| AWS IAM Identity Center | SAML 2.0 | ドキュメント化済み | カスタム SAML アプリケーション |

## 参考リンク

- [Amplify Gen2: External login providers](https://docs.amplify.aws/gen2/build-a-backend/auth/concepts/external-identity-providers/)
- [Cognito User Pool SAML federation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-saml-idp.html)
- [Cognito User Pool OIDC federation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-oidc-idp.html)
