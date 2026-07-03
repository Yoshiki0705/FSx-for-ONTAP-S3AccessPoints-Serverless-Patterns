🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

# Event-Driven Prototype

## Overview

This prototype is a reference implementation of an event-driven file processing
pipeline that anticipates the future native notification capability of
FSx for ONTAP S3 Access Points (FSx for ONTAP S3 AP).

It uses the Event Notifications of a regular S3 bucket to simulate the
future native notification behavior of FSx for ONTAP S3 AP.

## Architecture

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge enabled)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (image tagging + metadata generation)
          → Latency Reporter Lambda (EMF metrics output)
```

## Mapping to Future FSx for ONTAP S3 AP Support

| Current prototype | Future FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| `aws.s3` event source | `aws.fsx` event source (planned) |
| Filter by S3 bucket name | Filter by S3 AP alias |
| Read via S3 GetObject | Read via S3 AP |

## Required Changes (When Native Notifications Are Supported)

Changes required once FSx for ONTAP S3 AP supports native notifications:

### 1. Template Changes

```yaml
# Before (prototype)
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# After (FSx for ONTAP S3 AP)
# Remove the S3 Bucket resource and reference the existing FSx for ONTAP S3 AP
# Update the source filter of the EventBridge Rule
```

### 2. EventBridge Rule Changes

```json
// Before
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// After (planned)
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Lambda Environment Variable Changes

```yaml
# Before
SOURCE_BUCKET: !Ref SourceBucket

# After
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Lambda Code Changes

```python
# Before (prototype)
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# After (FSx for ONTAP S3 AP)
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## Deployment Steps

### Prerequisites

- AWS CLI configured
- Python 3.12
- S3 bucket for the Lambda deployment package

### Deploy

```bash
# 1. Build and upload the Lambda package
# (omitted: automated by the CI/CD pipeline)

# 2. Deploy the SAM stack
# Prerequisite: AWS SAM CLI is required. sam build automatically packages the code and shared layers.
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. Upload a test file
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### Running Tests

```bash
# Unit tests
pytest event-driven-prototype/tests/ -v

# Latency comparison test (after deployment)
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## Directory Structure

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation template
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # Event processing Lambda (UC11 compatible)
│   └── latency_reporter/
│       └── handler.py            # Latency measurement Lambda
├── tests/
│   ├── test_event_processor.py   # Event processing unit tests
│   ├── test_latency_reporter.py  # Latency measurement unit tests
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # This document
```

## Metrics

The following metrics are emitted in CloudWatch EMF format:

| Metric name | Unit | Description |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | Event occurrence → processing start |
| `EndToEndDuration` | Milliseconds | Event occurrence → processing complete |
| `ProcessingDuration` | Milliseconds | Processing execution time |
| `EventVolumePerMinute` | Count | Events processed per minute |

## Related Documents

- [Event-Driven Architecture Design](../docs/event-driven/architecture-design.md)
- [Migration Guide](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
