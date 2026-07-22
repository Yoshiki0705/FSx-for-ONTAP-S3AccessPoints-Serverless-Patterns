# Amazon Quick Desktop × AgentCore MCP Gateway セットアップガイド

> ⚠️ **本ドキュメントの構成は PoC 専用です。** Gateway 認証が NONE（認証なし）のため、本番データへの接続には使用しないでください。本番環境では CUSTOM_JWT + Authorization Policy、または VPC 内配置 + Security Group を適用してください。

> **対象読者**: FSx for ONTAP 上の EDA/業務データを Amazon Quick から MCP 経由で分析したい SA / エンジニア
>
> **Workshop**: [FSx for ONTAP S3 Access Points Workshop (Module 09)](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore)
>
> **検証済みバージョン**: Quick Desktop v0.1000.1495 / AgentCore Gateway 2026-07 GA

---

## 概要

Amazon Quick Desktop アプリから AgentCore MCP Gateway 経由で、FSx for ONTAP S3 Access Point 上のファイルをリアルタイムに読み取り・検索できます。

```
Quick Desktop (MCP Client, stdio via mcp-remote)
    ↓ HTTP Streamable
AgentCore MCP Gateway (ap-northeast-1, NONE auth — PoC)
    ↓ Lambda Invoke (同一リージョン)
MCP Tools Lambda (list_files / read_file / search_files)
    ↓ S3 API
FSx for ONTAP S3 Access Point (ap-northeast-1)
    ↓
NFS/SMB ボリューム（EDA シミュレーションログ等）
```

---

## クイックスタート（5 分）

```bash
# 1. デプロイ（CloudFormation + Gateway + Lambda）
./scripts/deploy-agentcore-mcp.sh \
  --s3ap-alias <your-ap-xxxxx-ext-s3alias> \
  --s3ap-name <your-ap-name> \
  --stack-name agentcore-mcp-eda

# 2. Quick Desktop で Import
#    Settings → Capabilities → Connectors → + Create → MCP server → Import
#    Config file path: .private/mcp-agentcore-quick.json
#    → Load file → Import 1 server → Add server

# 3. Chat で質問
#    「eda-regression/simulation/ のファイルを一覧表示して」
```

---

## 前提条件

| 項目 | 要件 |
|------|------|
| Amazon Quick | Enterprise サブスクリプション（Desktop MCP 機能を含む） |
| Quick Desktop | v0.1000.1495 以上（macOS / Windows） |
| Node.js | v22+（`npx` コマンドが使える状態） |
| AWS CLI | v2.35+ |
| FSx for ONTAP | S3 Access Point がアタッチ済みのボリューム |
| AgentCore | ap-northeast-1 に対応（2026-07 検証済み。us-east-1 も利用可能） |

---

## 詳細手順

### Step 1: インフラデプロイ

#### Option A: ワンクリックスクリプト（推奨）

```bash
./scripts/deploy-agentcore-mcp.sh \
  --s3ap-alias <your-s3ap-alias> \
  --s3ap-name <your-s3ap-name> \
  --stack-name agentcore-mcp-eda
```

スクリプトが以下を自動実行:
1. CloudFormation スタックデプロイ（Lambda + IAM Roles）
2. AgentCore Gateway 作成（NONE 認証、PoC 用）
3. Lambda ターゲット登録（tool schema 付き）
4. `tools/list` で 3 ツール検出を検証
5. Quick Desktop 用 MCP 設定 JSON を `.private/mcp-agentcore-quick.json` に生成

#### Option B: CloudFormation 手動デプロイ

```bash
aws cloudformation deploy \
  --template-file infrastructure/agentcore-mcp-gateway/template.yaml \
  --stack-name agentcore-mcp-eda \
  --parameter-overrides \
    S3AccessPointAlias=<your-alias> \
    S3AccessPointName=<your-name> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

デプロイ後、Gateway 作成はスクリプトの Step 3〜5 を手動実行。

### Step 2: Quick Desktop サインイン

**Email ベース**が最もシンプルです。

1. Quick Desktop 起動 → Region: Quick アカウントのリージョン
2. **「Continue with 📧」(Email)** を選択
3. QuickSight 登録メールアドレスを入力
4. メール認証リンクをクリック → ブラウザで「アクセスを許可」
5. Desktop に自動復帰

> **よくある混乱**: IAM ユーザー名 ≠ QuickSight ユーザー名。確認コマンド:
> ```bash
> aws quicksight list-users --aws-account-id $(aws sts get-caller-identity --query Account --output text) \
>   --namespace default --region ap-northeast-1 --query 'UserList[*].{User:UserName,Email:Email}'
> ```

### Step 3: MCP サーバー追加（Import 方式）

> **検証済み**: Import が唯一安定する方法です（2026-07 時点）。
> Local / Remote 直接追加はバグにより永続化されない場合があります。

1. Settings → Capabilities → **Connectors** タブ
2. **+ Create** → **MCP server** → **Import** タブ
3. Config file path に以下を入力:

```
<project-root>/.private/mcp-agentcore-quick.json
```

JSON の中身（デプロイスクリプトが自動生成）:

```json
{
  "mcpServers": {
    "EDA Log Analyzer": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "https://<gateway-id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"],
      "env": {},
      "disabled": false
    }
  }
}
```

4. **Load file** → 「Kiro / Claude Code — 1 server found」
5. **Import 1 server**
6. 確認ダイアログ → **Add server**
7. 「**EDA Log Analyzer — 3 tools · 3 write · Connected**」と表示されれば成功

### Step 4: 動作テスト

| クエリ | ツール | 期待結果 |
|--------|--------|---------|
| `eda-regression/simulation/ のファイルを一覧表示して` | list_files | 50 件のファイル一覧テーブル |
| `JOB_00005 のログを読んで結果を教えて` | read_file | FAIL + UVM_FATAL 原因分析 |
| `"JOB_0004" を含むログを検索してプレビュー付きで` | search_files | 10 件 (7 PASS / 3 FAIL) + 詳細 |

---

## 検証で得られた教訓

### 動作する構成

| コンポーネント | 構成 | 備考 |
|---|---|---|
| Gateway 認証 | **NONE** | PoC 用。本番は VPC + SG で保護 |
| MCP 追加方式 | **Import** (JSON file) | Local/Remote はバグあり（間欠的） |
| MCP トランスポート | **mcp-remote** (stdio proxy) | Remote 直接は不安定 |
| Lambda リージョン | **ap-northeast-1** (Gateway と同一) | クロスリージョンは不可 |
| Gateway リージョン | **ap-northeast-1** (2026-07 検証済み) | us-east-1 も利用可能 |

### 動作しない構成（2026-07 時点）

| 構成 | 原因 |
|---|---|
| Web コンソール MCP connector Step 2 | UI バグ "Fix highlighted fields" |
| Desktop → Remote/Local 直接追加 | 永続化されない |
| Gateway CUSTOM_JWT + Desktop | 403 (認可ポリシー不一致) |
| Gateway AWS_IAM + Desktop | SigV4 非対応 |

---

## 本番環境への移行

| # | 改善項目 | 方法 |
|---|---------|------|
| 1 | Gateway 認証 | NONE → CUSTOM_JWT + 認可ポリシー |
| 2 | ネットワーク | VPC 内配置 + Security Group |
| 3 | Lambda | インライン → ZIP パッケージ |
| 4 | 監視 | CloudWatch Metrics + X-Ray |
| 5 | データリージョン | Lambda を ap-northeast-1 に移行（AgentCore 対応待ち） |

> **Data residency note**: 現在の PoC 構成では Lambda（us-east-1）が S3 AP（ap-northeast-1）のファイル内容を取得するため、データがリージョン間を転送されます。コンプライアンス要件（FISC、個人情報保護法等）がある場合は、AgentCore Gateway の東京リージョン対応を待つか、同一リージョンに閉じた構成を検討してください。

---

## クリーンアップ

```bash
./scripts/deploy-agentcore-mcp.sh --cleanup --stack-name agentcore-mcp-eda
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [デモガイド](demo-agentcore-mcp-quick-desktop.md) | E2E デモ + スクリーンショット |
| [AgentCore MCP Tools 定義](agentcore-mcp-tools.md) | Lambda ツール仕様 |
| [CloudFormation テンプレート](../infrastructure/agentcore-mcp-gateway/template.yaml) | IaC |
| [デプロイスクリプト](../scripts/deploy-agentcore-mcp.sh) | ワンクリックデプロイ |
| [残課題トラッカー](agentcore-mcp-remaining-issues.md) | 既知の問題 |
| [Quick Desktop MCP 公式](https://docs.aws.amazon.com/quick/latest/userguide/connections-desktop.html) | AWS ドキュメント |
| [AgentCore Lambda ターゲット仕様](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html) | 入力フォーマット |
