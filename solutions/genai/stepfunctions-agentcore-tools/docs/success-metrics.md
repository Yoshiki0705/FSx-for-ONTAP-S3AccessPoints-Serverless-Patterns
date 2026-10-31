# Success Metrics — Step Functions × AgentCore Gateway

Partner/SI の顧客会話で PoC の成否を判断するための指標。数値はデプロイ環境・
ファイル構成・モデルで変わるため、各環境で測り直す。

## Business Outcome

- 既存の Step Functions ワークフローを**作り直さずに**エージェントのツールにできる。
  業務ロジックの再実装コストを避けつつ、起動と結果確認を自然言語に寄せられる。
- 手順の順序と承認はワークフローが保証するため、エージェントが手順を飛ばして
  実行を確定させる経路が構造的に存在しない。

## Technical KPI

| 指標 | 測り方 | 目安 |
|---|---|---|
| ツール公開までの手順 | テンプレートデプロイ + deploy スクリプト 1 回 | 2 コマンド |
| ツール発見 | `tools/list` が 5 ツールを返す | 5 |
| 起動 → 結果確認の往復 | エージェントが `StartExecution` → `DescribeExecution` を自律実行 | 自動 |
| ワークフロー完了時間 | `GetExecutionHistory` の開始/終了イベント差分 | 環境依存（未測定） |

## Quality KPI

| 指標 | 測り方 | 目安 |
|---|---|---|
| 要約の確信度 | `human_review.confidence_score` の分布 | 環境・モデル依存 |
| Human Review 率 | `HumanReviewRequired` / `FilesProcessed`（EMF メトリクス） | 業務の許容値で設定 |
| 処理成功率 | report の `success_rate_pct` | 100% を目標、逸脱は調査 |

## Cost KPI

- Step Functions（Standard、状態遷移課金）+ AgentCore Gateway の通常料金 +
  Lambda（arm64）+ Bedrock（モデル・トークン依存）。金額は時点情報のため、
  提示前に Pricing API で確認する。
- Gateway 経由かどうかで Step Functions / Lambda の課金は変わらない。追加されるのは
  Gateway の料金だけ。

## Go / No-Go

- **Go**: DemoMode でワークフローが成功し、`tools/list` が期待ツールを返し、
  エージェントが起動 → 状況確認 → 結果報告を自律的に行えること。
- **No-Go の典型要因**: Gateway とステートマシンのリージョン不一致、Gateway サービス
  ロールの権限不足（`DescribeExecution` の実行 ARN スコープ漏れ）、`input` JSON の
  日本語化け対策が未適用で業務データが壊れる、同期即応答が必須なのに Standard を選んでいる。

## 測定条件の明示

数値を外部に出すときは、リージョン・モデル ID（推論プロファイル接頭辞）・ファイル数と
サイズ・測定日を併記する。併記できない数値は「未測定」と書く。
