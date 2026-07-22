# デモガイド: Amazon Quick Desktop × AgentCore MCP Gateway × FSx for ONTAP

> ⚠️ **本デモは PoC 構成（認証なし Gateway）を使用します。** 機密データを含むボリュームには接続しないでください。本番では CUSTOM_JWT 認証 + VPC 保護が必要です。
>
> **Data residency note**: Lambda（us-east-1）→ S3 AP（ap-northeast-1）間でファイル内容がリージョン間転送されます。

> **検証日**: 2026-07-19/20
> **検証環境**: ap-northeast-1 (Quick) + us-east-1 (AgentCore Gateway)
> **ステータス**: ✅ E2E 動作確認完了

## 概要

Amazon Quick Desktop から自然言語で質問すると、AgentCore MCP Gateway 経由で FSx for ONTAP 上の EDA シミュレーションログをリアルタイムにブラウズ・読み取り・検索できることを確認しました。

### アーキテクチャ

```
Amazon Quick Desktop (MCP Client)
    ↓ stdio (mcp-remote → HTTP Streamable)
AgentCore MCP Gateway (ap-northeast-1, NONE auth, PoC)
    ↓ Lambda Invoke (同一リージョン)
MCP Tools Lambda (list_files / read_file / search_files)
    ↓ S3 API (ListObjectsV2 / GetObject)
FSx for ONTAP S3 Access Point (ap-northeast-1)
    ↓
FSx for ONTAP Volume (/eda_demo — 50 simulation logs)
```

> **リージョン**: 全コンポーネントが ap-northeast-1 に配置。クロスリージョンレイテンシーなし。
> 初期検証時は us-east-1 に配置していましたが、AWS サポートの確認により ap-northeast-1 で利用可能と判明（2026-07-21）。

---

## セットアップ手順

### 前提条件

- Amazon Quick Desktop v0.1000.1495+
- Node.js 22+（`npx` が使える状態）
- AgentCore MCP Gateway がデプロイ済み（後述）
- FSx for ONTAP S3 AP にデータがアップロード済み

### Step 1: Quick Desktop にサインイン

1. Quick Desktop 起動 → Region: **Asia Pacific (Tokyo)**
2. **「Continue with 📧」(Email)** を選択
3. QuickSight 登録メールアドレスを入力
4. メール認証リンクをクリック → ブラウザで「アクセスを許可」
5. Desktop に自動復帰

> **ポイント**: 「Continue with SSO」→ IAM ユーザーサインインではなく、Email ベースが最もシンプル

<!-- Screenshot: quick-desktop-signin-email.png -->

### Step 2: MCP 設定ファイルを作成

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

ファイルを保存（例: `~/.config/mcp-agentcore.json`）

### Step 3: Import で MCP サーバーを追加

1. Settings → Capabilities → Connectors タブ
2. **+ Create** → MCP server
3. **Import** タブを選択
4. Config file path に JSON ファイルのパスを入力
5. **Load file** → 「Kiro / Claude Code — 1 server found」と表示される
6. **Import 1 server**
7. 確認ダイアログ「Allow MCP server?」→ **Add server**

<!-- Screenshot: quick-desktop-import-config.png -->
<!-- Screenshot: quick-desktop-import-detected.png -->
<!-- Screenshot: quick-desktop-allow-server.png -->

### Step 4: 接続確認

Settings → Capabilities → Connectors → MCP SERVERS に以下が表示される:

> **EDA Log Analyzer** — 3 tools · 3 write · **Connected**

<!-- Screenshot: quick-desktop-mcp-connected.png -->

---

## デモクエリ

### クエリ 1: ファイル一覧表示

```
eda-regression/simulation/ にあるファイルを一覧表示して
```

Quick の応答:
- 「EDA Log Analyzer のMCPツールを使ってFSx上のファイルを確認する方が適切でしょうか？」と確認
- 承認後、MCP ツール `list_files` が呼び出される
- **50 件のシミュレーションログ** (JOB_00001_sim.log 〜 JOB_00050_sim.log) がテーブル形式で表示
- Quick が自動分析:「大きめのファイル (400〜475B) はエラーや追加情報を含んでいる可能性」

<!-- Screenshot: quick-desktop-tool-approval.png -->
<!-- Screenshot: quick-desktop-list-files-result.png -->

### クエリ 2: 失敗ジョブの調査（推奨デモ）

```
JOB_00005のシミュレーションログの中身を読んで、結果がPASSかFAILか教えて
```

Quick の応答:
- `read_file` ツールで JOB_00005_sim.log を読み取り
- **結果: FAIL** と即座に判定
- ログ全文を整形表示（Cadence Xcelium シミュレーター出力）
- AI 分析ポイント:
  - 「UVM_FATAL が 1 件発生、`serdes_tx_scoreboard` の `COMPARE_FAIL` が原因」
  - 「Expected と Actual が同じ値 (0x000020ba) に見える — スコアボードのタイミングやサンプリングに問題がある可能性」
  - 「UVM_ERROR も 9 件あり、他にも問題が発生」

<!-- Screenshot: quick-desktop-read-file-approval.png -->
<!-- Screenshot: quick-desktop-read-file-result.png -->

### クエリ 3: パターン検索 + 分析

```
ファイル名に "JOB_0004" を含むシミュレーションログを検索して、内容のプレビューも表示して
```

Quick の応答:
- `search_files` ツールでパターン `JOB_0004` を検索
- **10 件ヒット** (JOB_00040 〜 JOB_00049)
- 各ファイルのプレビューを読み取り、結果をテーブルで自動整理:

| ジョブ | モジュール | シミュレーション時間 | 結果 | 詳細 |
|--------|-----------|------------------|------|------|
| JOB_00040 | watchdog_top | 16232 ns | ❌ FAIL | タイミング違反 (usb_clk, Slack: -2.92 ns) |
| JOB_00041 | clock_gen_top | 14357 ns | ✅ PASS | — |
| JOB_00042 | memory_ctrl_top | 8847 ns | ✅ PASS | — |
| JOB_00046 | clock_gen_top | 20485 ns | ❌ FAIL | ASSERTION_FAIL (UVM_ERROR: 1) |
| JOB_00048 | audio_codec_top | 29030 ns | ❌ FAIL | タイミング違反 (ddr_clk, Slack: -2.22 ns) |

- **失敗ジョブの詳細分析**:
  - JOB_00040: パス `watchdog/reg_q -> watchdog/mux_out`、Required: 1.50 ns / Actual: 3.29 ns / Slack: **-2.92 ns**
  - JOB_00046: `clock_gen_top` で `ASSERTION_FAIL` 検出
  - JOB_00048: パス `audio_codec/reg_q -> audio_codec/mux_out`、Required: 1.50 ns / Actual: 1.43 ns / Slack: **-2.22 ns**
- サマリー: **10 件中 7 件 PASS / 3 件 FAIL**

<!-- Screenshot: quick-desktop-search-files-approval.png -->
<!-- Screenshot: quick-desktop-search-files-result-table.png -->
<!-- Screenshot: quick-desktop-search-files-result-detail.png -->

---

## 重要な注意点

### Quick Desktop の MCP 追加方式

| 方式 | 動作状況 | 備考 |
|------|---------|------|
| **Import (推奨)** | ✅ 動作確認済み | JSON ファイルから読み込み |
| Local (手動入力) | ⚠️ 保存されない場合あり | v0.1000.1495 のバグ |
| Remote (直接 HTTP) | ⚠️ 保存されない場合あり | 同上 |

### 認証方式の選択

| Gateway 認証 | Quick Desktop 互換 | 備考 |
|---|:---:|---|
| **NONE** | ✅ | PoC 向け。mcp-remote で直接接続 |
| CUSTOM_JWT (Cognito) | ❌ | 403 Forbidden（認可ポリシー要調査） |
| AWS_IAM | ❌ | Quick Desktop は SigV4 非対応 |

> **本番環境**: 認証なし Gateway は PoC 専用です。本番では VPC 内配置 + Security Group、または CUSTOM_JWT の認可ポリシーを正しく設定してください。

---

## クリーンアップ

```bash
# AgentCore Gateway 削除
aws bedrock-agentcore-control delete-gateway \
  --gateway-identifier <your-gateway-id> \
  --region us-east-1

# Lambda 削除
aws lambda delete-function \
  --function-name <your-stack-name>-tools \
  --region us-east-1

# S3 AP 削除（FSx for ONTAP ボリュームは残す場合）
aws fsx detach-and-delete-s3-access-point \
  --name <your-ap-name> \
  --region ap-northeast-1

# Cognito User Pool 削除
aws cognito-idp delete-user-pool \
  --user-pool-id <your-user-pool-id> \
  --region us-east-1
```

> **Tip**: デプロイスクリプトを使った場合は `./scripts/deploy-agentcore-mcp.sh --cleanup --stack-name <your-stack-name>` で一括削除できます。

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [Quick Desktop MCP セットアップ](quick-desktop-mcp-setup.md) | 詳細な設定手順 + IaC |
| [AgentCore MCP Tools 定義](agentcore-mcp-tools.md) | Lambda ツール仕様 |
| [Workshop EDA 統合ガイド](workshop-eda-integration.md) | Workshop 全モジュール対応 |
| [AWS Workshop (Module 09)](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore) | AgentCore Gateway ハンズオン |
