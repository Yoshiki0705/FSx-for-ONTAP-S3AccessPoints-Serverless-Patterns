# Step Functions × AgentCore Gateway — ワークフローを AI エージェントのツールに

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

FSx for ONTAP の S3 Access Points 上のファイルを処理する Standard な Step Functions
ワークフロー（発見 → 処理 → レポート）を、Amazon Bedrock AgentCore Gateway の
組み込み Step Functions コネクタ経由で AI エージェントのツールとして公開するサンプルです。

エージェントは「いつ動かすか」「何を入力するか」を判断し、手順の順序はワークフローが
保証します。決まった手順はワークフロー、起動判断はエージェント、という棲み分けです。

## ユースケース

- 既存の Step Functions ワークフローを、ステートマシンに手を入れずエージェントから起動する
- 手順と承認はワークフローに固めておき、実行判断だけをエージェントに任せる
- エージェントに「どの処理がどこまで進んだか」を実行履歴から調べさせる

## アーキテクチャ

```
AI エージェント ──MCP──▶ AgentCore Gateway (Step Functions コネクタ)
                              │ GatewayServiceRole で states:StartExecution 等
                              ▼
                     Standard StateMachine (Discover→Choice→Map→Report)
                              │
                 Discovery / Processing / Report Lambda
                              │
                        S3 Access Point (FSx for ONTAP / DemoMode は通常 S3)
```

詳細は [docs/architecture.md](docs/architecture.md) を参照してください。

## 公開されるツール

| ツール | 入力 | 用途 |
|---|---|---|
| `workflow___StartExecution` | `input`（JSON 文字列） | ワークフロー起動 |
| `workflow___ListExecutions` | `statusFilter`（任意） | 実行一覧（Standard のみ） |
| `workflow___DescribeStateMachine` | `includedData`（任意） | ステートマシンのメタ/定義 |
| `workflow___DescribeExecution` | `executionArn`、`includedData` | 状況・結果の確認 |
| `workflow___GetExecutionHistory` | `executionArn` | ステップ履歴 |

固定したステートマシン ARN はツールに出ず、エージェントは変更できません。

## パラメータ

| パラメータ | 説明 | デフォルト |
|---|---|---|
| `S3AccessPointAlias` | FSx for ONTAP ボリュームの S3 AP Alias（DemoMode では通常バケット名） | (必須) |
| `DemoMode` | `true` で FSx for ONTAP 不要（通常 S3 バケットで動作） | `false` |
| `FilePrefix` | 走査するプレフィックス | `input/` |
| `BedrockModelId` | 要約モデル / 推論プロファイル ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 1 実行あたりの最大ファイル数 | `100` |
| `NotificationEmail` | SNS 通知先（空でスキップ） | `""` |
| `GatewayName` | Gateway 名（deploy スクリプトが使用） | `sfn-agentcore-tools-gateway` |

## デプロイ

Gateway もコネクタターゲットも CloudFormation の第一級リソース
（`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`）なので、1 つのテンプレートで
宣言的に完結します。deploy スクリプトは `sam build` + `sam deploy` のラッパーで、
デプロイ後に `tools/list` を検証します。

```bash
# DemoMode（FSx for ONTAP 不要）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# 本番（S3 AP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# 後片付け
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

会話例と検証手順は [docs/demo-guide.md](docs/demo-guide.md) にあります。

## Human Review 閾値

Processing Lambda は要約の確信度を `shared/human_review.py` で評価します。

| 確信度 | 判定 |
|---|---|
| `>= 0.85`（既定 `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`） | AUTO_APPROVE |
| `>= 0.30`（既定 `HUMAN_REVIEW_REJECT_THRESHOLD`）かつ `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

閾値は環境変数で上書きできます。判定は結果に含めるだけで、このパターンは最終判断を
自動では行いません。

## データ分類

Report Lambda は出力に `shared/data_classification.py` 由来の `data_classification`
ラベルを付けます。既定は `INTERNAL`。環境変数 `DATA_CLASSIFICATION` で変更できます。

## Governance Note

- エージェントが担うのは**起動判断と状況確認だけ**です。処理の順序・分岐・承認は
  ステートマシンが保証し、エージェントがスキップや並べ替えをすることはできません。
- 固定したステートマシン ARN はツールに露出せず、別のステートマシンを起動できません。
- AI による要約・分類は**補助信号**であり、最終判断ではありません。確信度が閾値を
  下回る場合は Human Review に回す設計です。
- `SendTaskSuccess` 等のタスクトークン操作はこのパターンでは公開していません
  （IAM でリソース制限できないため）。
- これはガバナンスの指針であり、法務・コンプライアンス上の判断を代替しません。

## テスト

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## 既知の注意点

同一リージョン制約、1 操作 1 pin、日本語入力の `?` 化けと `\uXXXX` 回避、Cedar での
`input` 条件の制約などは [docs/demo-guide.md](docs/demo-guide.md) にまとめています。

## 参考

- [AWS Step Functions as Connector Target（公式）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools（What's New）](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)

---

<!-- playbook-reading:start -->
## 本番に出す前に読むもの

デプロイしたあとに当たる制約を、どう設計判断に翻訳するかは [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) 側にあります。同じ内容を 2 か所に置くと、更新が止まった側が更新された側より長く残るためです。

- [データ活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/data-utilization) — S3 Access Point 経由の制約（全パターン共通）
- [セキュリティ・ガバナンス](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/domains/security-governance) — このパターンで判断が集中するところ
- [構築](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/ja/playbooks/04-build) — 本番前に通す（全パターン共通）
<!-- playbook-reading:end -->
