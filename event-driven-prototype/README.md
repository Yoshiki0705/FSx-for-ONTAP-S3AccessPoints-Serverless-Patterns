# Event-Driven Prototype（イベント駆動プロトタイプ）

## 概要

本プロトタイプは、FSx for NetApp ONTAP S3 Access Points（FSx ONTAP S3 AP）の
将来のネイティブ通知機能を見据えた、イベント駆動ファイル処理パイプラインの
リファレンス実装である。

通常の S3 バケットの Event Notifications を使用して、
将来の FSx ONTAP S3 AP ネイティブ通知動作をシミュレートする。

## アーキテクチャ

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge 有効)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (画像タグ付け + メタデータ生成)
          → Latency Reporter Lambda (EMF メトリクス出力)
```

## FSx ONTAP S3 AP 将来対応へのマッピング

| 現在のプロトタイプ | 将来の FSx ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx ONTAP S3 AP + Native Notifications |
| `aws.s3` イベントソース | `aws.fsx` イベントソース（予定） |
| S3 バケット名でフィルタ | S3 AP エイリアスでフィルタ |
| S3 GetObject で読み取り | S3 AP 経由で読み取り |

## 必要な変更点（ネイティブ通知対応時）

FSx ONTAP S3 AP がネイティブ通知をサポートした際に必要な変更:

### 1. テンプレート変更

```yaml
# 変更前（プロトタイプ）
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# 変更後（FSx ONTAP S3 AP）
# S3 Bucket リソースを削除し、既存の FSx ONTAP S3 AP を参照
# EventBridge Rule のソースフィルタを更新
```

### 2. EventBridge ルール変更

```json
// 変更前
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// 変更後（予定）
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Lambda 環境変数変更

```yaml
# 変更前
SOURCE_BUCKET: !Ref SourceBucket

# 変更後
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Lambda コード変更

```python
# 変更前（プロトタイプ）
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# 変更後（FSx ONTAP S3 AP）
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## デプロイ手順

### 前提条件

- AWS CLI 設定済み
- Python 3.12
- Lambda デプロイパッケージ用 S3 バケット

### デプロイ

```bash
# 1. Lambda パッケージのビルド・アップロード
# (省略: CI/CD パイプラインで自動化)

# 2. CloudFormation スタックのデプロイ
aws cloudformation deploy \
  --template-file event-driven-prototype/template-deploy.yaml \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM

# 3. テストファイルのアップロード
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### テスト実行

```bash
# ユニットテスト
pytest event-driven-prototype/tests/ -v

# レイテンシ比較テスト（デプロイ後）
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## ディレクトリ構成

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation テンプレート
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # イベント処理 Lambda（UC11 互換）
│   └── latency_reporter/
│       └── handler.py            # レイテンシ計測 Lambda
├── tests/
│   ├── test_event_processor.py   # イベント処理ユニットテスト
│   ├── test_latency_reporter.py  # レイテンシ計測ユニットテスト
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # 本ドキュメント
```

## メトリクス

CloudWatch EMF 形式で以下のメトリクスを出力:

| メトリクス名 | 単位 | 説明 |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | イベント発生→処理開始 |
| `EndToEndDuration` | Milliseconds | イベント発生→処理完了 |
| `ProcessingDuration` | Milliseconds | 処理実行時間 |
| `EventVolumePerMinute` | Count | 1分あたりイベント処理数 |

## 関連ドキュメント

- [イベント駆動アーキテクチャ設計](../docs/event-driven/architecture-design.md)
- [移行ガイド](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
