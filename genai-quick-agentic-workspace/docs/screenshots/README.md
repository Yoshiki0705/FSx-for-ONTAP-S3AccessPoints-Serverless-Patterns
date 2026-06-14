# UC30 スクリーンショット

- `originals/` … 元画像（環境固有情報を含む、gitignore 対象）
- `masked/` … マスク済み画像（公開安全、tracked）

マスクは Playwright で DOM に黒塗りを注入してから撮影する方式で実施。手順は steering「スクリーンショットマスキング」準拠。

## マスク済み画像

| ファイル | 内容 |
|---------|------|
| `masked/cloudformation-stacks.png` | UC29/UC30 の CloudFormation スタック（CREATE/UPDATE_COMPLETE） |
| `masked/athena-recent-queries.png` | Athena 実行履歴（quick-workspace-wg）: sales_pipeline_total / it_incident_summary（SELECT 集計）と CREATE EXTERNAL TABLE が Completed |
| `masked/quick-home.png` | Amazon Quick ホーム（エージェント型ワークスペース: Chat/Spaces/Flows/Research/Knowledge/Quick Sight） |
| `masked/quick-knowledge-integrations.png` | Quick Knowledge データソース。**Amazon S3 コネクタ**（S3 Access Point データを Quick Index に接続する入口）ほか |
| `masked/quick-flows.png` | Quick Flows 画面（アクション自動化、UC30 Action API 連携の入口） |
| `masked/quick-s3-kb-connect.png` | Quick の S3 ナレッジベース接続ダイアログ。**FSxN S3 AP エイリアスを有効なバケット URL として受理**するが、権限不足メッセージ（接続にはデータアクセスロールの S3 AP 権限が必要＝統合境界の証跡） |

> アカウント ID・S3 結果バケット名・リソース ID・ユーザー名（Quick アカウント名）はマスク済み。
