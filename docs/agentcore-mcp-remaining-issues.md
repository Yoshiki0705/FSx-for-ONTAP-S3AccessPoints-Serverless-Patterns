# AgentCore MCP Gateway × Amazon Quick — 残課題トラッカー

> **最終更新**: 2026-07-20
> **検証バージョン**: Quick Desktop v0.1000.1495 / Quick Web (ap-northeast-1) / AgentCore Gateway GA (us-east-1)

---

## サマリー

| カテゴリ | Open | Resolved | Workaround |
|---------|:----:|:--------:|:----------:|
| Quick Web コンソール | 1 | 0 | — |
| Quick Desktop | 1 | 0 | ✅ Import 方式 |
| AgentCore Gateway 認証 | 1 | 0 | ✅ NONE auth |
| Lambda / バックエンド | 0 | 3 | — |

---

## Open Issues

### ISSUE-1: Quick Web コンソール MCP connector 作成 Step 2 UI バグ

| 項目 | 内容 |
|------|------|
| **ステータス** | 🔴 Open — AWS サポートケース起票済み |
| **重大度** | Medium（回避策あり） |
| **発見日** | 2026-07-19 |
| **Support Case** | filed with AWS Support (tracked internally) |
| **re:Post** | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |

**症状**: Connectors → Create for your team → Model Context Protocol → Step 2 (Authenticate) で「Fix highlighted fields to proceed.」エラーが表示されるが、赤枠のフィールドは存在しない。

**影響**: Web コンソールから MCP コネクタを作成できない。Chat Agent に MCP ツールをリンクできない。

**根本原因**: クライアントサイドのフォームバリデーションバグ。Create and continue 押下時にバックエンドへの HTTP リクエストが送信されない（Network タブで確認済み）。

**回避策**: Quick Desktop の Import 方式で MCP サーバーを追加する。

**解決に必要なアクション**: AWS Quick チームによるコンソール UI 修正。

---

### ISSUE-2: Quick Desktop MCP サーバー追加が永続化されない（Local / Remote 方式）

| 項目 | 内容 |
|------|------|
| **ステータス** | 🔴 Open — AWS サポートケース起票済み |
| **重大度** | Medium（回避策あり） |
| **発見日** | 2026-07-20 |
| **Support Case** | filed with AWS Support (tracked internally) |
| **Community** | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |

**症状**: + Create → MCP server → Local/Remote → Test connection 成功（「Connected — 3 tools available」）→ + Add MCP → 確認ダイアログ → Add server → **MCP SERVERS セクションに表示されない（0 件のまま）**。

**影響**: Local / Remote 方式での MCP サーバー追加ができない。

**バージョン**: v0.1000.1495 (Build 6475741731)

**回避策**: **Import 方式**（JSON ファイルから読み込み）で追加すると正常に永続化される。

**解決に必要なアクション**: AWS Quick Desktop チームによるサーバー永続化ロジック修正。

---

### ISSUE-3: AgentCore Gateway CUSTOM_JWT 認証 + Quick Desktop で 403 Forbidden

| 項目 | 内容 |
|------|------|
| **ステータス** | 🟡 Investigation needed |
| **重大度** | High（本番環境への影響大） |
| **発見日** | 2026-07-20 |

**症状**: CUSTOM_JWT 認証の Gateway に対して、Cognito ID Token を Bearer ヘッダーで送信すると 403 Forbidden。JWT の `aud` claim と Gateway の `allowedAudience` は一致。

**影響**: 認証付き Gateway を Quick Desktop から利用できない。PoC は NONE auth で動作するが、本番環境には認証が必須。

**調査済み事項**:
- JWT claims 確認: `aud`, `iss`, `sub` 全て正しい
- Gateway の RFC 9728 メタデータ: 正常に返却
- 401 → 403 遷移: トークンは認識されるが認可で拒否

**仮説**:
1. CUSTOM_JWT Gateway のデフォルト認可ポリシーが全ツール呼び出しを拒否
2. `allowedClients` / `allowedAudience` だけでなく、明示的な認可ルール（policy）の設定が必要
3. `customClaims` マッピングが未設定のため、権限判定に失敗

**次のアクション**:
- AgentCore Gateway のポリシー設定（`Use an AgentCore Gateway with Policy`）を調査
- AWS ドキュメント参照: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/use-gateway-with-policy.html

**暫定回避策**: `authorizerType: NONE` + VPC / Security Group でネットワークレベル保護。

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

## 本番化ブロッカー

以下が解決するまで、本番環境での Quick + AgentCore MCP 連携は**PoC フェーズ**にとどめることを推奨:

| # | ブロッカー | 影響 | 解決パス |
|---|-----------|------|---------|
| 1 | CUSTOM_JWT 認証の 403 問題 | 認証なし Gateway を使わざるを得ない | ISSUE-3 の調査 |
| 2 | Web コンソール MCP UI バグ | Agent にツールをリンクできない | AWS 修正待ち |
| 3 | Desktop MCP 永続化バグ | Import のみが動作 | AWS 修正待ち |
| 4 | `CreateActionConnector` API に MCP Type なし | API 経由の回避策なし | API 拡張待ち |

---

## 次のアクション

- [ ] AWS サポートからの回答を待機（2 件のケース）
- [ ] CUSTOM_JWT Gateway + Policy の設定を調査・検証
- [ ] Quick Desktop の次バージョンで MCP 永続化バグが修正されるか確認
- [ ] Web コンソール UI 修正後に Agent リンクの E2E テスト実施
- [ ] 本番認証パターン（VPC + CUSTOM_JWT + Policy）の設計ドキュメント作成

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
