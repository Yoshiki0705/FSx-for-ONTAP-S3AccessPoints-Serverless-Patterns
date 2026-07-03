🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

# Event-Driven Prototype（事件驅動原型）

## 概述

本原型是一個著眼於 FSx for ONTAP S3 Access Points（FSx for ONTAP S3 AP）
未來原生通知功能的事件驅動檔案處理管線的
參考實作。

它使用一般 S3 儲存貯體的 Event Notifications，
模擬未來 FSx for ONTAP S3 AP 原生通知的行為。

## 架構

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge 已啟用)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (影像標記 + 中繼資料產生)
          → Latency Reporter Lambda (EMF 指標輸出)
```

## 與 FSx for ONTAP S3 AP 未來支援的對應

| 目前的原型 | 未來的 FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| `aws.s3` 事件來源 | `aws.fsx` 事件來源（預定） |
| 依 S3 儲存貯體名稱篩選 | 依 S3 AP 別名篩選 |
| 透過 S3 GetObject 讀取 | 透過 S3 AP 讀取 |

## 所需變更（支援原生通知時）

當 FSx for ONTAP S3 AP 支援原生通知時所需的變更:

### 1. 範本變更

```yaml
# 變更前（原型）
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# 變更後（FSx for ONTAP S3 AP）
# 刪除 S3 Bucket 資源，並參照現有的 FSx for ONTAP S3 AP
# 更新 EventBridge Rule 的來源篩選器
```

### 2. EventBridge 規則變更

```json
// 變更前
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// 變更後（預定）
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Lambda 環境變數變更

```yaml
# 變更前
SOURCE_BUCKET: !Ref SourceBucket

# 變更後
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Lambda 程式碼變更

```python
# 變更前（原型）
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# 變更後（FSx for ONTAP S3 AP）
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## 部署步驟

### 前提條件

- 已設定 AWS CLI
- Python 3.12
- 用於 Lambda 部署套件的 S3 儲存貯體

### 部署

```bash
# 1. 建置並上傳 Lambda 套件
# （省略: 由 CI/CD 管線自動化）

# 2. 部署 SAM 堆疊
# 前提: 需要 AWS SAM CLI。sam build 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. 上傳測試檔案
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### 執行測試

```bash
# 單元測試
pytest event-driven-prototype/tests/ -v

# 延遲比較測試（部署後）
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## 目錄結構

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation 範本
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # 事件處理 Lambda（UC11 相容）
│   └── latency_reporter/
│       └── handler.py            # 延遲測量 Lambda
├── tests/
│   ├── test_event_processor.py   # 事件處理單元測試
│   ├── test_latency_reporter.py  # 延遲測量單元測試
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # 本文件
```

## 指標

以 CloudWatch EMF 格式輸出下列指標:

| 指標名稱 | 單位 | 說明 |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | 事件發生 → 處理開始 |
| `EndToEndDuration` | Milliseconds | 事件發生 → 處理完成 |
| `ProcessingDuration` | Milliseconds | 處理執行時間 |
| `EventVolumePerMinute` | Count | 每分鐘事件處理數 |

## 相關文件

- [事件驅動架構設計](../docs/event-driven/architecture-design.md)
- [移轉指南](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
