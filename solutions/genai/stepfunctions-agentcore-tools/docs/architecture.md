# Architecture — Step Functions × AgentCore Gateway

## 全体像

```
                         ┌─────────────────────────────┐
   AI エージェント ──MCP──▶│  AgentCore Gateway          │
   (起動判断・結果確認)     │  Step Functions コネクタ     │
                         │  (connectorId: "states")     │
                         └──────────────┬──────────────┘
                                        │ GatewayServiceRole を assume
                                        │ states:StartExecution 等
                                        ▼
                         ┌─────────────────────────────┐
                         │  Standard StateMachine       │
                         │  Discover→Choice→Map→Report  │
                         └──────┬──────┬──────┬─────────┘
                                ▼      ▼      ▼
                       Discovery   Processing   Report
                       (S3 AP 走査) (Bedrock +   (集計 + SNS +
                                    human_review) data_classification)
                                │      │      │
                                └──────┴──────┘
                                  S3 Access Point
                            (FSx for ONTAP / DemoMode は通常 S3)
```

エージェントは「いつワークフローを動かすか」「何を入力するか」を判断する。
処理の順序（発見 → 処理 → レポート）はステートマシンが保証し、エージェントは
スキップも並べ替えもできない。確実に守らせたい手順はワークフロー側に置き、
判断はエージェントに任せる、という棲み分けになる。

## エージェントから見えるツール

ターゲット名を `workflow` とした場合、Gateway は次のツールを公開する。

| ツール | 入力 | 用途 |
|---|---|---|
| `workflow___StartExecution` | `input`（JSON 文字列） | ワークフロー起動。`executionArn` を返す |
| `workflow___ListExecutions` | `statusFilter`（任意） | 実行一覧（Standard のみ） |
| `workflow___DescribeStateMachine` | `includedData`（任意） | ステートマシンのメタ/定義 |
| `workflow___DescribeExecution` | `executionArn`、`includedData` | 状況確認（`ALL_DATA` で入出力込み） |
| `workflow___GetExecutionHistory` | `executionArn` | どのステップで止まっているか |

固定したステートマシン ARN はツールスキーマに出ず、エージェントは変更できない。
別の ARN を渡すと Gateway が `Invalid request parameters` で拒否する。

## 既存の AgentCore パターンとの違い

このリポジトリには Lambda ターゲット方式の AgentCore 連携
（`infrastructure/agentcore-mcp-gateway`）が既にある。本パターンはコネクタ方式で、
ターゲットの実体が異なる。

| 観点 | Lambda ターゲット（既存） | 本パターン（コネクタ） |
|---|---|---|
| ターゲット種別 | `mcp.lambda` | `mcp.connector`（`connectorId: "states"`） |
| ツールの実体 | Lambda が直接ツールになる | ステートマシンの操作がツールになる |
| handler の露出 | Gateway が Lambda を直接呼ぶ | Lambda は Task としてのみ呼ばれ Gateway に露出しない |
| ツール定義 | 自分で inlinePayload を書く | Gateway が操作からスキーマを生成する |

## コンポーネント

- **Discovery Lambda**: `S3ApHelper` で S3 AP を走査し、処理対象の manifest を返す
- **Processing Lambda**: `S3ApHelper` でファイルを読み、Bedrock Nova で要約・分類。
  確信度を `evaluate_confidence` で評価して human_review 判定を結果に含める
- **Report Lambda**: Map の結果を集計し、`data_classification` ラベルを付けて SNS 通知
- **Standard StateMachine**: Discover → Choice（件数判定）→ Map（並列処理）→ Report。
  全 Task に Retry / Catch。Standard のため実行履歴が残り `GetExecutionHistory` で追える
- **GatewayServiceRole**: Gateway がステートマシンを呼ぶためのロール。pin 操作は
  ステートマシン ARN、非 pin 操作は実行 ARN にスコープした最小権限

## IaC は宣言的に完結する

Gateway とコネクタターゲットは CloudFormation の第一級リソース
（`AWS::BedrockAgentCore::Gateway` / `AWS::BedrockAgentCore::GatewayTarget`）です。
したがってパターン全体を 1 つのテンプレートで宣言でき、スタックをデプロイすれば
Gateway の `tools/list` までそろいます。別途の作成手順は要りません。

`scripts/deploy-stepfunctions-agentcore.sh` は `sam build` + `sam deploy` の薄い
ラッパーで、デプロイ後に `tools/list` を検証します。コネクタターゲットは pin 可能な
4 操作にステートマシン ARN を固定します（`Mcp.Connector.Source.ConnectorId: states`、
`Configurations[].ParameterValues.stateMachineArn`）。`ParameterValues` のキーは
Step Functions API のパラメータ名なので `stateMachineArn` は camelCase のままです。
