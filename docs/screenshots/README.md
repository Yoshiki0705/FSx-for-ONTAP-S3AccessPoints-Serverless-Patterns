# スクリーンショット

本ディレクトリには、AWS マネジメントコンソールの UI スクリーンショットを保存します。

## 撮影対象

AWS 環境での検証後、以下のスクリーンショットを撮影してこのディレクトリに保存してください。

| # | ファイル名 | 内容 | 撮影タイミング |
|---|-----------|------|--------------|
| 1 | `step-functions-workflow.png` | Step Functions ワークフロー実行画面 | ワークフロー実行完了後 |
| 2 | `cloudformation-stack.png` | CloudFormation スタック作成画面 | スタックデプロイ完了後 |
| 3 | `s3-output-bucket.png` | S3 出力バケット内容 | ワークフロー実行完了後 |
| 4 | `cloudwatch-logs.png` | CloudWatch ログ | Lambda 関数実行後 |
| 5 | `eventbridge-scheduler.png` | EventBridge Scheduler 設定 | スタックデプロイ完了後 |

## 撮影時の注意事項

- **AWS アカウント ID を黒塗りまたは除外すること**（環境情報保護ルール準拠）
- IP アドレス、VPC ID、サブネット ID 等の環境固有情報もマスクすること
- ブラウザのブックマークバーや個人情報が映り込まないよう注意すること
- 画像形式は PNG を推奨（JPEG でも可）
- 解像度は 1280x720 以上を推奨

## 現在のステータス

> **注意**: 現在はプレースホルダーのみです。AWS 環境での検証完了後にスクリーンショットを追加してください。

### 期待されるスクリーンショット一覧

1. **step-functions-workflow.png** — Step Functions ワークフロー実行画面
   - ステートマシンのグラフビュー
   - 各ステートの実行結果（成功/失敗）
   - 実行時間の表示

2. **cloudformation-stack.png** — CloudFormation スタック作成画面
   - スタックのリソース一覧
   - パラメータ設定値
   - 出力（Outputs）セクション

3. **s3-output-bucket.png** — S3 出力バケット内容
   - 日付パーティション構造
   - 生成されたレポートファイル
   - Manifest JSON ファイル

4. **cloudwatch-logs.png** — CloudWatch ログ
   - Lambda 関数のログストリーム
   - 正常実行時のログ出力例
   - エラー発生時のスタックトレース例

5. **eventbridge-scheduler.png** — EventBridge Scheduler 設定
   - スケジュール式（rate/cron）の設定
   - ターゲット（Step Functions）の設定
   - 有効/無効の状態
