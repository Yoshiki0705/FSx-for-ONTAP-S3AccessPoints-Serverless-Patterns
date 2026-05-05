# スクリーンショット

本ディレクトリには、AWS マネジメントコンソールの UI スクリーンショットを保存します。

## 撮影対象

AWS 環境での検証後、以下のスクリーンショットを撮影してこのディレクトリに保存してください。

### Phase 1 スクリーンショット

| # | ファイル名 | 内容 | 撮影タイミング |
|---|-----------|------|--------------|
| 1 | `step-functions-workflow.png` | Step Functions ワークフロー実行画面 | ワークフロー実行完了後 |
| 2 | `cloudformation-stack.png` | CloudFormation スタック作成画面 | スタックデプロイ完了後 |
| 3 | `s3-output-bucket.png` | S3 出力バケット内容 | ワークフロー実行完了後 |
| 4 | `cloudwatch-logs.png` | CloudWatch ログ | Lambda 関数実行後 |
| 5 | `eventbridge-scheduler.png` | EventBridge Scheduler 設定 | スタックデプロイ完了後 |

### Phase 2 スクリーンショット

| # | ファイル名 | 内容 | 撮影タイミング |
|---|-----------|------|--------------|
| 6 | `phase2-step-functions-all.png` | Phase 2 全 UC の Step Functions 実行一覧 | 全 UC デプロイ・実行完了後 |
| 7 | `phase2-cloudformation-stacks.png` | Phase 2 CloudFormation スタック一覧 | 全 UC デプロイ完了後 |
| 8 | `phase2-s3-output-structure.png` | Phase 2 S3 出力バケットの日付パーティション構造 | ワークフロー実行完了後 |
| 9 | `phase2-cross-region-logs.png` | クロスリージョン API 呼び出しの CloudWatch ログ | UC7/UC10/UC12/UC13/UC14 実行後 |
| 10 | `phase2-textract-cross-region.png` | Textract (us-east-1) の API 呼び出し確認 | Cross-Region UC 実行後 |
| 11 | `phase2-comprehend-medical.png` | Comprehend Medical (us-east-1) の実行結果 | UC7 実行後 |
| 12 | `phase2-distributed-map.png` | Distributed Map の実行画面（10K+ オブジェクト） | 大規模データテスト後 |

## 撮影時の注意事項

- **AWS アカウント ID を黒塗りまたは除外すること**（環境情報保護ルール準拠）
- IP アドレス、VPC ID、サブネット ID 等の環境固有情報もマスクすること
- ブラウザのブックマークバーや個人情報が映り込まないよう注意すること
- 画像形式は PNG を推奨（JPEG でも可）
- 解像度は 1280x720 以上を推奨

## Phase 2 撮影手順

### Step Functions ワークフロー実行画面

1. AWS コンソール → Step Functions → ステートマシン一覧
2. Phase 2 UC のステートマシンを選択（例: `fsxn-semiconductor-eda-workflow`）
3. 「実行」タブで最新の実行を選択
4. グラフビューで全ステートが緑（成功）であることを確認
5. スクリーンショットを撮影

### CloudFormation スタック一覧

1. AWS コンソール → CloudFormation → スタック
2. フィルタで `fsxn-` プレフィックスのスタックを表示
3. Phase 2 の 9 スタックが `CREATE_COMPLETE` であることを確認
4. スクリーンショットを撮影

### S3 出力バケット構造

1. AWS コンソール → S3 → 出力バケット
2. 日付パーティション構造（`year=YYYY/month=MM/day=DD/`）を展開
3. 生成されたレポートファイル（JSON / テキスト）を確認
4. スクリーンショットを撮影

### クロスリージョン API ログ

1. AWS コンソール → CloudWatch → ログ → ロググループ
2. Cross-Region UC の Lambda ログを選択（例: `/aws/lambda/fsxn-logistics-ocr-OcrFunction`）
3. ログストリームで `Cross-region call to us-east-1` のログエントリを確認
4. スクリーンショットを撮影

## 現在のステータス

> **注意**: Phase 2 スクリーンショットは AWS 環境での検証完了後に追加してください。
