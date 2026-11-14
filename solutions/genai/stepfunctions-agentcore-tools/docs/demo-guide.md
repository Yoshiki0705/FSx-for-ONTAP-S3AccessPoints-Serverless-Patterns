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

## 業種を指定した要約
`input` に任意の `industry` を足すと、要約の注目点を業種に合わせて切り替えられる。

```json
{"file_prefix": "contracts/", "max_files": 50, "industry": "legal"}
```

`industry` は固定の表（`shared/industry_focus.py`）にある ID だけが使われる。表にない値は無視され、
入力の文字列がプロンプトに入ることはない。指定しなければ従来どおりの要約になる。
注目点は要約の観点を足すだけで、専門家の判断の代わりにはならない。人に回すかどうかは、
従来どおり Human Review の閾値で決まる。エージェントのシステムプロンプトには、
上の `input` の形に `industry` を足した例を書いておく。

| `industry` | 要約で注目する点 |
|---|---|
| `government` | 条例・規則・通達の名称と条番号、公開前に確認が要る個人情報や非開示情報の可能性 |
| `healthcare` | 手順書やガイドラインの名称、数値と単位（原文のまま）、患者を特定できる記述の有無。診断や治療方針は述べない |
| `legal` | 契約当事者、期間、解除・損害賠償・秘密保持などの条項と条番号。法的助言は述べない |
| `insurance` | 事案の種類、必要書類と不足、適用される約款や査定基準。支払可否は述べない |
| `manufacturing` | 品質基準、仕様の値と許容差（原文のまま）、不具合の原因と是正処置 |
| `construction` | 安全基準、工程、設計変更の内容と影響を受ける図面や協力会社 |
| `education` | 科目や制度の名称、成績や評価の方針、研究計画や助成の要件。個人の成績は述べない |
| `financial` | 金額、通貨、期日、当事者。予算・実績・見込みの区別。数値は丸めない |
| `media` | 素材やプロジェクトの名称、利用許諾の範囲・期間・地域、審査の指摘 |
| `semiconductor` | 設計仕様と設計ルールの該当箇所、検証結果の重大度、リビジョン間の変更点 |
| `lifesciences` | 実験や手順の名称、取扱い・保管・緊急時対応の要点、数値（原文のまま）、手順の逸脱 |
| `energy` | 設備名、点検日と指摘事項、調査の目的・方法・結果、保安規程の該当箇所 |
| `automotive` | 試験や走行の条件と日付、不具合と対策、仕様変更の影響を受ける仕様書や試験 |
| `retail` | 商品名と仕様、取引条件、返品規程。資料にない効能や性能は述べない |
| `logistics` | 伝票番号、日付、車両や設備の点検・整備記録、運送契約の条項 |
| `telecom` | 障害の症状と発生日時、対応手順、変更の影響を受けるサービスと手順書 |
| `agrifood` | ロット番号、原料から出荷までの記録、衛生・品質検査で基準を外れた点 |
| `realestate` | 物件名、賃貸借の期間・賃料・更新・解約の条件、修繕と点検の履歴 |
| `hr` | 制度や手続の名称、対象者、期限。個人の人事記録は述べない |
| `esg` | 指標名、実績値、年度と単位、開示基準との対応と不足している情報 |
| `travel` | 予約や手配の番号、日付、取消規定と料金 |

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
