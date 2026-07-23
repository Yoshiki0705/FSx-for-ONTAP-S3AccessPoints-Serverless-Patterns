# AgentCore MCP Gateway × Amazon Quick — 残課題トラッカー

> **最終更新**: 2026-07-22
> **検証バージョン**: Quick Desktop v0.1000.1495 / Quick Web (ap-northeast-1) / AgentCore Gateway GA (us-east-1)

---

## サマリー

| カテゴリ | Open | Resolved | Workaround |
|---------|:----:|:--------:|:----------:|
| Quick Web コンソール | 0 | 1 | — |
| Quick Desktop | 0 | 1 | ✅ Import 方式 |
| AgentCore Gateway 認証 | 0 | 1 | ✅ Policy Engine + allowedClients |
| Lambda / バックエンド | 0 | 3 | — |
| **API 制約（新規判明）** | **1** | 0 | ⚠️ コンソール経由のみ |

---

## Resolved Issues

### ISSUE-1: Quick Web コンソール MCP connector 作成 Step 2 UI バグ

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ Resolved (2026-07-21) |
| **重大度** | Medium |
| **発見日** | 2026-07-19 |
| **解決日** | 2026-07-20（再現しなくなった）|
| **Support Case** | filed with AWS Support — resolved |
| **re:Post** | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |

**症状**: Connectors → Create for your team → Model Context Protocol → Step 2 (Authenticate) で「Fix highlighted fields to proceed.」エラーが表示されるが、赤枠のフィールドは存在しない。

**根本原因（AWS 確認済み）**: Step 2 から「Previous」で Step 1 に戻ると OAuth フィールドがクリアされ、その状態で「作成して続行」をクリックするとバリデーションエラーが発生する。re:Post にも同一報告あり。

**解決**: 2026-07-20 に再試行したところ正常に作成可能。「Previous」を使わずに一度ウィザードを閉じてやり直すことで回避可能。

---

### ISSUE-2: Quick Desktop MCP サーバー追加が永続化されない（Local / Remote 方式）

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ Resolved (2026-07-21) |
| **重大度** | Medium |
| **発見日** | 2026-07-20 |
| **解決日** | 2026-07-20（再現しなくなった）|
| **Support Case** | filed with AWS Support — resolved |
| **Community** | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |

**症状**: + Create → MCP server → Local/Remote → Test connection 成功 → Add server → MCP SERVERS に表示されない。

**根本原因**: 不明。Quick Desktop はプレビュー版のため不安定性あり。AWS サポートでも同事象を確認できず。

**解決**: 2026-07-20 に再試行したところ正常に永続化。Quick Desktop の自動アップデートまたはバックエンド側の状態変化と推定。

**再発時の情報収集手順**（AWS サポート推奨）:
- 検証時間 (JST)
- 事象発生時の画面動画
- `~/Library/Logs/quickwork` のログ
- Quick Desktop アカウント ID (Manage plan → My account)
- ブラウザの Connectors で MCP 作成可能か確認

**引き続き推奨される回避策**: Import 方式（JSON ファイル）が最も安定。

---

## Known Constraints (API 制約)

### CONSTRAINT-1: MCP コネクタは API 作成不可（コンソール経由のみ）

| 項目 | 内容 |
|------|------|
| **ステータス** | ⚠️ Current Limitation (2026-07-22 確認) |
| **確認方法** | AWS サポートによる検証 + `CreateActionConnector` API ドキュメント確認 |

**詳細**: `CreateActionConnector` API の `Type` パラメータに MCP に相当する値がない。`MODEL_CONTEXT_PROTOCOL` を指定すると `InvalidParameterValueException` が返却される。

**影響**:
- IaC（CloudFormation / CDK）での MCP コネクタ作成が不可
- CI/CD パイプラインでのコネクタ自動セットアップが不可
- コネクタ設定の Git 管理・再現が困難

**回避策**:
1. Quick Web コンソールから手動作成（一度作成すれば永続）
2. Quick Desktop の Import 方式（JSON ファイルで設定を管理可能）
3. AgentCore Gateway 自体は CloudFormation / CDK で作成可能（コネクタのみ手動）

**本番運用への影響**: コネクタ作成は初回セットアップ時のみ必要。Gateway の Lambda ターゲットや認証設定は IaC で管理可能なため、実運用上の大きな障壁にはならない。

**今後の期待**: Amazon Quick が GA になるタイミングで `CreateActionConnector` API が MCP タイプをサポートする可能性あり。

---

## Pending Verification

### CASE-3: AgentCore MCP Gateway ap-northeast-1 (Tokyo) リージョンデプロイ

| 項目 | 内容 |
|------|------|
| **ステータス** | 🟡 Pending Customer Action（検証中） |
| **ケース番号** | 178449261200987 |
| **起票日** | 2026-07（Feature Request） |
| **AWS 回答日** | 2026-07-22 |

**経緯**: 当初、AgentCore MCP Gateway を us-east-1 にデプロイしていた（ワークショップ手順と Web Search Tool ドキュメントに従った結果）。Feature Request として ap-northeast-1 対応を問い合わせた。

**AWS サポート回答（Ifra M.）**:
- us-east-1 制約はワークショップ手順と Web Search Tool ドキュメントに起因するもので、AgentCore Gateway + Lambda targets 自体にリージョン制限はない
- **ap-northeast-1 でのデプロイをテストしてほしい**
- テスト結果を共有すればさらにサポート可能

**次のアクション**:
- [ ] `scripts/deploy-agentcore-mcp.sh` を ap-northeast-1 向けに実行
- [ ] Gateway + Lambda targets が ap-northeast-1 で正常動作するか確認
- [ ] Quick Desktop から ap-northeast-1 Gateway に接続テスト
- [ ] 結果をサポートケースに返信

**影響（成功した場合）**:
- クロスリージョンデータ転送（us-east-1 → ap-northeast-1）が不要になる
- データレジデンシー要件を満たせる（ファイル内容が東京リージョン外に出ない）
- レイテンシ改善（同一リージョン内完結）

---

### ISSUE-3: AgentCore Gateway CUSTOM_JWT 認証 + Quick Desktop で 403 Forbidden

| 項目 | 内容 |
|------|------|
| **ステータス** | ✅ **Resolved** (2026-07-20) |
| **重大度** | High（本番環境への影響大） |
| **発見日** | 2026-07-20 |

**症状**: CUSTOM_JWT 認証の Gateway に対して、Cognito ID Token を Bearer ヘッダーで送信すると 403 Forbidden。JWT の `aud` claim と Gateway の `allowedAudience` は一致。

**根本原因（3 つの設定不足の複合）**:

1. **Policy Engine 未設定**: CUSTOM_JWT Gateway はデフォルトで全ツール呼び出しを deny。Policy Engine + Cedar ポリシーの作成・接続が必要
2. **`allowedAudience` と client_credentials トークンの不一致**: Cognito `client_credentials` フローのトークンには `aud` claim が含まれない。`allowedAudience` を削除して `allowedClients` のみで認証する
3. **Gateway Service Role の権限不足**: Policy Engine 連携に `bedrock-agentcore:AuthorizeAction`, `PartiallyAuthorizeActions`, `GetPolicyEngine` 等が必要

**修正手順**:

```bash
# 1. Policy Engine 作成
aws bedrock-agentcore-control create-policy-engine --name eda_mcp_policy --region us-east-1

# 2. Cedar ポリシー追加（IGNORE_ALL_FINDINGS で PoC 用 permit-all）
aws bedrock-agentcore-control create-policy \
  --policy-engine-id <engine-id> \
  --name permit_all_poc \
  --definition '{"cedar":{"statement":"permit(principal, action, resource is AgentCore::Gateway);"}}' \
  --validation-mode IGNORE_ALL_FINDINGS \
  --region us-east-1

# 3. Gateway Service Role に bedrock-agentcore:* 権限追加
aws iam put-role-policy --role-name <gateway-role> --policy-name PolicyEngineAccess \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock-agentcore:*","Resource":"arn:aws:bedrock-agentcore:<region>:<account>:*"}]}'

# 4. Gateway 更新（allowedAudience 削除 + Policy Engine 接続）
aws bedrock-agentcore-control update-gateway \
  --gateway-identifier <gateway-id> \
  --name <gateway-name> \
  --role-arn <role-arn> \
  --authorizer-type CUSTOM_JWT \
  --authorizer-configuration '{"customJWTAuthorizer":{
    "discoveryUrl":"https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration",
    "allowedClients":["<client-id>"],
    "allowedScopes":["<scope1>","<scope2>"]
  }}' \
  --policy-engine-configuration '{"arn":"<policy-engine-arn>","mode":"ENFORCE"}'

# 5. M2M トークン取得（Cognito client_credentials）
curl -X POST "https://<domain>.auth.<region>.amazoncognito.com/oauth2/token" \
  -H "Authorization: Basic <base64(client_id:secret)>" \
  -d "grant_type=client_credentials&scope=<scope1>+<scope2>"

# 6. 動作確認
curl -X POST "https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp" \
  -H "Authorization: Bearer <token>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# → 3 tools returned ✅
```

**検証結果** (2026-07-20):
- `tools/list`: ✅ 3 ツール正常表示
- `tools/call` (list_files): ✅ FSx for ONTAP S3 AP のファイル一覧取得成功

**本番向けの注意**:
- `permit(principal, action, resource is AgentCore::Gateway)` は PoC 用（全許可）
- 本番では `principal == AgentCore::OAuthUser::"<specific-sub>"` や `when { context.scopes.contains("admin") }` で制限する
- `validationMode: IGNORE_ALL_FINDINGS` は本番では使用しない

---

## Resolved Issues

### RESOLVED-1: Lambda の AgentCore 入力フォーマット不一致

| 項目 | 内容 |
|------|------|
| **解決日** | 2026-07-19 |
| **根本原因** | Lambda handler が `event.toolName` を参照していたが、AgentCore は `context.client_context.custom['bedrockAgentCoreToolName']` にツール名を渡す |

**修正**: handler.py を AgentCore フォーマットに対応（`context.client_context.custom` からツール名を取得、event はフラットなパラメータ辞書として処理）。

---

### RESOLVED-2: AgentCore Gateway がクロスリージョン Lambda を呼べない

| 項目 | 内容 |
|------|------|
| **解決日** | 2026-07-19 |
| **根本原因** | Gateway (us-east-1) から Lambda (ap-northeast-1) への呼び出しは非対応 |

**修正**: Lambda を Gateway と同じ us-east-1 にデプロイ。S3 AP はどのリージョンからもアクセス可能（Internet-origin AP）。

---

### RESOLVED-3: Quick Web コネクタのツール検出で `listTools` のみ表示

| 項目 | 内容 |
|------|------|
| **解決日** | 2026-07-19（根本原因特定） |
| **根本原因** | AWS_IAM Gateway で Web コネクタ作成時、Quick の OAuth トークンと Gateway の IAM 認証が不一致。Gateway は `tools/list` のメタ情報のみ返却 |

**修正**: CUSTOM_JWT または NONE auth の Gateway に切り替え。ツール検出は正常動作（curl で 3 ツール確認済み）。

---

### RESOLVED-4: AgentCore Gateway は us-east-1 のみという前提は誤り

| 項目 | 内容 |
|------|------|
| **解決日** | 2026-07-21 |
| **根本原因** | Workshop が us-east-1 を使用していたのは簡便性のためであり、リージョン制約ではなかった |

**修正**: ap-northeast-1 で Gateway + Lambda Target をデプロイし、E2E 動作確認。`tools/list` で 3 ツール返却、`tools/call` でファイル一覧取得成功。AWS サポートも ap-northeast-1 での利用可能性を Lab 環境で確認。

**影響**: クロスリージョンレイテンシーが排除され、アーキテクチャが簡素化。

---

## 本番化ブロッカー

以下が解決するまで、本番環境での Quick + AgentCore MCP 連携は**PoC フェーズ**にとどめることを推奨:

| # | ブロッカー | 影響 | 解決パス |
|---|-----------|------|---------|
| ~~1~~ | ~~CUSTOM_JWT 認証の 403 問題~~ | ~~認証なし Gateway を使わざるを得ない~~ | ✅ **解決済み** (Policy Engine + allowedClients) |
| 2 | Web コンソール MCP UI バグ | Agent にツールをリンクできない | AWS 修正待ち |
| 3 | Desktop MCP 永続化バグ | Import のみが動作 | AWS 修正待ち |
| 4 | `CreateActionConnector` API に MCP Type なし | API 経由の回避策なし | API 拡張待ち |

---

## 次のアクション

- [x] ~~CUSTOM_JWT Gateway + Policy の設定を調査・検証~~ → **解決済み (2026-07-20)**
- [ ] AWS サポートからの回答を待機（2 件のケース: Web UI バグ, Desktop 永続化）
- [ ] Quick Desktop の次バージョンで MCP 永続化バグが修正されるか確認
- [ ] Web コンソール UI 修正後に Agent リンクの E2E テスト実施
- [ ] 本番認証パターンの Cedar ポリシーを scope/claim ベースに強化
- [ ] Quick Desktop から CUSTOM_JWT Gateway への接続検証（mcp-remote + Bearer token）

---

## 参考リンク

| リソース | URL |
|---------|-----|
| AgentCore Gateway Policy | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/use-gateway-with-policy.html |
| Quick MCP Integration docs | https://docs.aws.amazon.com/quick/latest/userguide/mcp-integration.html |
| Quick Desktop Connectors | https://docs.aws.amazon.com/quick/latest/userguide/connections-desktop.html |
| re:Post (Web UI bug) | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |
| Community (Desktop bug) | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |
| Community (mcp-remote workaround) | https://community.amazonquicksight.com/t/tip-connecting-remote-mcp-servers-to-amazon-quick-stdio-proxy-method-tried-and-tested/52790 |
