# Phase 11 AWS コンソール確認ガイド

## 概要

Phase 11 でデプロイされたリソースを AWS マネジメントコンソールで確認するためのガイド。
初見ユーザーがソリューションの全体像を把握するために有用な画面を記載。

## 確認すべきコンソール画面

### 1. CloudWatch Dashboard — Cross-Account Overview

**URL**: `https://ap-northeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-northeast-1#dashboards/dashboard/fsxn-s3ap-cross-account-overview`

**確認ポイント**:
- Lambda Invocations & Errors (全アカウント集約)
- Step Functions Executions (Started/Failed/Succeeded)
- Lambda Duration P90 & Average
- FSxN S3AP Processing Latency (カスタムメトリクス)

### 2. EventBridge — カスタムバス (fsxn-fpolicy-events)

**URL**: `https://ap-northeast-1.console.aws.amazon.com/events/home?region=ap-northeast-1#/eventbuses/fsxn-fpolicy-events`

**確認ポイント**:
- バスに関連付けられたルール一覧
- 各ルールのイベントパターン（prefix/suffix フィルタ）
- ターゲット（Step Functions / Lambda）

### 3. CloudWatch OAM — Observability Sink

**URL**: `https://ap-northeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-northeast-1#settings/observability-access-manager`

**確認ポイント**:
- Sink: `fsxn-s3ap-observability-sink`
- リンクされたアカウント（マルチアカウント環境の場合）
- 共有リソースタイプ（Metrics, Logs, X-Ray Traces）

### 4. CloudFormation — デプロイ済みスタック

**URL**: `https://ap-northeast-1.console.aws.amazon.com/cloudformation/home?region=ap-northeast-1#/stacks`

**確認すべきスタック**:
| スタック名 | 説明 |
|-----------|------|
| `fsxn-shared-observability` | Cross-Account Observability (Sink + Dashboard + SNS + IAM) |
| `fsxn-idempotency-store` | HYBRID モード重複排除用 DynamoDB |
| `fsxn-fpolicy-*` | FPolicy パイプライン (ECS + SQS + EventBridge) |

### 5. DynamoDB — Idempotency Store

**URL**: `https://ap-northeast-1.console.aws.amazon.com/dynamodbv2/home?region=ap-northeast-1#table?name=fsxn-s3ap-idempotency-store`

**確認ポイント**:
- テーブル設定: PAY_PER_REQUEST, TTL 有効
- キースキーマ: pk (UC#file_path), sk (operation#timestamp_bucket)
- Point-in-Time Recovery: 有効

### 6. ECS — FPolicy Server (Fargate)

**URL**: `https://ap-northeast-1.console.aws.amazon.com/ecs/v2/clusters/fsxn-fpolicy-fsxn-fp-srv/services?region=ap-northeast-1`

**確認ポイント**:
- サービス: fpolicy-service (desired=1, running=1)
- タスク定義: FPolicy Server コンテナ
- ネットワーク: Private Subnet, Security Group

### 7. SQS — Ingestion Queue

**URL**: `https://ap-northeast-1.console.aws.amazon.com/sqs/v3/home?region=ap-northeast-1#/queues/https%3A%2F%2Fsqs.ap-northeast-1.amazonaws.com%2F178625946981%2Ffsxn-fpolicy-ingestion-fsxn-fpolicy-ingestion`

**確認ポイント**:
- メッセージ数 (Available / In-Flight / Delayed)
- DLQ 設定
- 暗号化設定

### 8. SNS — Aggregated Alerts

**URL**: `https://ap-northeast-1.console.aws.amazon.com/sns/v3/home?region=ap-northeast-1#/topic/arn:aws:sns:ap-northeast-1:178625946981:fsxn-s3ap-aggregated-alerts`

**確認ポイント**:
- サブスクリプション（Email）
- KMS 暗号化
- アクセスポリシー（CloudWatch Alarms + Workload Accounts）

## TriggerMode 切り替え手順

### POLLING → EVENT_DRIVEN に変更する場合

```bash
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=EVENT_DRIVEN \
  --capabilities CAPABILITY_NAMED_IAM
```

**結果**:
- EventBridge Scheduler: 削除される (Condition: IsPollingOrHybrid = false)
- FPolicy EventBridge Rule: 作成される (Condition: IsEventDrivenOrHybrid = true)

### EVENT_DRIVEN → HYBRID に変更する場合

```bash
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=HYBRID \
  --capabilities CAPABILITY_NAMED_IAM
```

**結果**:
- EventBridge Scheduler: 作成される
- FPolicy EventBridge Rule: 維持される
- Idempotency Store で重複排除

## Persistent Store 確認

### ONTAP REST API 経由

```bash
# Lambda 経由で確認
aws lambda invoke \
  --function-name fsxn-fpolicy-ip-updater \
  --payload '{"action": "ontap_api", "method": "GET", "path": "/api/protocols/fpolicy/9ae87e42-068a-11f1-b1ff-ada95e61ee66/persistent-stores?fields=*"}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  /tmp/ps-status.json && cat /tmp/ps-status.json
```

**期待される出力**:
```json
{
  "statusCode": 200,
  "body": {
    "records": [{
      "name": "fpolicy_aws_store",
      "volume": "fpolicy_persistent_store",
      "size": 1073741824
    }]
  }
}
```
