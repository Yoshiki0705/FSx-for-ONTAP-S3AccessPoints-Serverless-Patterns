# UC29 スクリーンショット

- `originals/` … 元画像（環境固有情報を含む、gitignore 対象）
- `masked/` … マスク済み画像（公開安全、tracked）

マスクは Playwright で DOM に黒塗りを注入してから撮影する方式で実施（アカウント ID・S3 AP エイリアス・
KB/DS ID・リソース ID・ユーザー名を黒塗り）。手順は steering「スクリーンショットマスキング」準拠。

## マスク済み画像

| ファイル | 内容 |
|---------|------|
| `masked/step-functions-execution-succeeded.png` | シナリオB の Step Functions 実行（全経路 Succeeded: DetectAndStartIngestion → Wait → CheckIngestionStatus → IsIngestionComplete → NotifySuccess、Events 23 件） |
| `masked/bedrock-kb-detail.png` | Amazon Bedrock Knowledge Base 詳細（マネージド RAG、S3 AP データソース） |

> アカウント ID・ARN・S3 AP エイリアスはマスク済み。
