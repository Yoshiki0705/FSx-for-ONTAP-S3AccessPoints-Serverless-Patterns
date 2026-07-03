🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

# Event-Driven Prototype（事件驱动原型）

## 概述

本原型是一个面向 FSx for ONTAP S3 Access Points（FSx for ONTAP S3 AP）
未来原生通知功能的事件驱动文件处理管道的
参考实现。

它使用普通 S3 存储桶的 Event Notifications，
模拟未来 FSx for ONTAP S3 AP 原生通知的行为。

## 架构

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge 已启用)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (图像标记 + 元数据生成)
          → Latency Reporter Lambda (EMF 指标输出)
```

## 与 FSx for ONTAP S3 AP 未来支持的映射

| 当前原型 | 未来的 FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| `aws.s3` 事件源 | `aws.fsx` 事件源（计划中） |
| 按 S3 存储桶名称过滤 | 按 S3 AP 别名过滤 |
| 通过 S3 GetObject 读取 | 通过 S3 AP 读取 |

## 所需变更（支持原生通知时）

当 FSx for ONTAP S3 AP 支持原生通知时所需的变更:

### 1. 模板变更

```yaml
# 变更前（原型）
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# 变更后（FSx for ONTAP S3 AP）
# 删除 S3 Bucket 资源，引用现有的 FSx for ONTAP S3 AP
# 更新 EventBridge Rule 的源过滤器
```

### 2. EventBridge 规则变更

```json
// 变更前
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// 变更后（计划中）
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Lambda 环境变量变更

```yaml
# 变更前
SOURCE_BUCKET: !Ref SourceBucket

# 变更后
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Lambda 代码变更

```python
# 变更前（原型）
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# 变更后（FSx for ONTAP S3 AP）
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## 部署步骤

### 前提条件

- 已配置 AWS CLI
- Python 3.12
- 用于 Lambda 部署包的 S3 存储桶

### 部署

```bash
# 1. 构建并上传 Lambda 包
# （省略: 由 CI/CD 管道自动完成）

# 2. 部署 SAM 堆栈
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. 上传测试文件
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### 运行测试

```bash
# 单元测试
pytest event-driven-prototype/tests/ -v

# 延迟比较测试（部署后）
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## 目录结构

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation 模板
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # 事件处理 Lambda（UC11 兼容）
│   └── latency_reporter/
│       └── handler.py            # 延迟测量 Lambda
├── tests/
│   ├── test_event_processor.py   # 事件处理单元测试
│   ├── test_latency_reporter.py  # 延迟测量单元测试
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # 本文档
```

## 指标

以 CloudWatch EMF 格式输出以下指标:

| 指标名称 | 单位 | 说明 |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | 事件发生 → 处理开始 |
| `EndToEndDuration` | Milliseconds | 事件发生 → 处理完成 |
| `ProcessingDuration` | Milliseconds | 处理执行时间 |
| `EventVolumePerMinute` | Count | 每分钟事件处理数 |

## 相关文档

- [事件驱动架构设计](../docs/event-driven/architecture-design.md)
- [迁移指南](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
