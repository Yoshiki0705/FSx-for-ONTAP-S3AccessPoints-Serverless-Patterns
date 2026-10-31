# Demo Guide — Step Functions × AgentCore Gateway

## 前提

- デプロイ済みの S3 Access Point（または DemoMode 用の通常 S3 バケット）
- AWS CLI v2（SSO ログイン済み）、`python3`、`jq`
- Bedrock Nova（または指定モデル）へのアクセス

## デプロイ

```bash
# 本番（S3 AP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias \
  --stack-name sfn-agentcore-tools

# DemoMode（通常 S3 バケット、FSx for ONTAP 不要）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode \
  --stack-name sfn-agentcore-tools-demo
```

デプロイ後、Gateway URL と公開ツールが表示される。

## ツールの確認

```bash
curl -s -X POST "$GATEWAY_URL" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}' | jq '.result.tools[].name'
```

期待される出力（ターゲット名が `workflow` の場合）:

```
workflow___StartExecution
workflow___ListExecutions
workflow___DescribeStateMachine
workflow___DescribeExecution
workflow___GetExecutionHistory
```

## エージェントとの会話例

ツールの説明は操作の汎用的な説明なので、`input` に渡す JSON の形はツールからは
分からない。エージェントのシステムプロンプトで次のように伝える。

```
あなたはファイル処理のオペレーターです。
- 処理を開始するには workflow___StartExecution に
  {"file_prefix": "input/", "max_files": 50} の形の input を渡します
- 開始したら workflow___DescribeExecution に executionArn と
  includedData: "ALL_DATA" を渡して結果を確認します
- 途中経過や停止箇所は workflow___GetExecutionHistory で調べます
```

会話の流れ:

1. 「input/ のファイルを処理して」
   → エージェントが `StartExecution` を呼び、`executionArn` を受け取る
2. エージェントが `DescribeExecution`（`ALL_DATA`）で状況と結果を確認
3. 「さっきの処理どうなった？」
   → `ListExecutions` で実行中/完了を探し、`DescribeExecution` で結果を報告
4. 「どのステップまで進んだ？」
   → `GetExecutionHistory` でステップ遷移を読み取る

## 1 ツールだけ直接呼ぶ（デバッグ）

```bash
curl -s -X POST "$GATEWAY_URL" -H "Content-Type: application/json" -d '{
  "jsonrpc":"2.0","id":1,"method":"tools/call",
  "params":{"name":"workflow___StartExecution",
    "arguments":{"input":"{\"file_prefix\":\"input/\",\"max_files\":10}"}}}' | jq
```

## 後片付け

```bash
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

## 既知の注意点

公式ドキュメントと検証から確認した、設計・運用で踏みやすい点。

- **Gateway とステートマシンは同一リージョン。** Gateway は同じリージョンの Step
  Functions エンドポイントを呼ぶ。別リージョンのステートマシンはつなげない。
- **1 操作に pin できるステートマシンは 1 つ。** 複数のワークフローを同じ操作で
  公開するなら、ワークフローごとにターゲットを分ける。
- **ツールの説明は汎用的。** `input` に渡す JSON の形はツールスキーマから分からないので、
  システムプロンプトやスキルでエージェントに伝える。
- **Standard と Express で使える操作が違う。** 本パターンは Standard。`ListExecutions` /
  `DescribeExecution` / `GetExecutionHistory` は Standard でのみ使える。同期即応答が
  必要なら Express + `StartSyncExecution` を別途検討する（本パターンの範囲外）。
- **タスクトークンは秘密として扱う。** `SendTaskSuccess` / `SendTaskFailure` /
  `SendTaskHeartbeat` は IAM でリソース制限できず、有効なタスクトークンを持つ
  エージェントなら誰でもタスクを完了できる。本パターンはこれらを公開しない。
- **日本語入力が `?` に化けることがある**（2026-10-30 時点の観測）。ワークフローに渡す
  JSON の日本語を `\uXXXX` にエスケープしてから送ると回避できる。エージェント側の
  ツール呼び出し直前フックで `json.dumps(obj)`（`ensure_ascii=True`）に通すのが簡単。
- **Cedar Policy Engine で `input` の中身を条件にした認可は現状エラーになる**
  （`context.input` の型評価エラー）。金額や理由など入力の中身による判断は
  ワークフロー側に持たせる。ツール単位の許可/拒否は Cedar で書ける。
- **成功レスポンスは成功の証拠ではない。** `StartExecution` は実行 ARN を返す非同期
  処理で、ワークフロー自体の成否は `DescribeExecution` で確認する。
