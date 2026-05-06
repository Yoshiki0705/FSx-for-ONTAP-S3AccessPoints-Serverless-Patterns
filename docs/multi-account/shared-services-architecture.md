# 共有サービスアカウント アーキテクチャ

> 集中可観測性・アラート統合による Single Pane of Glass 運用

## 概要

本ドキュメントでは、共有サービスアカウントの責務と構成を定義する。運用チームが全ワークロードアカウントを単一のダッシュボードから監視・トラブルシューティングできる集中可観測性プラットフォームを構築する。

### 共有サービスアカウントの責務

| 責務 | 実装 |
|---|---|
| 集中 CloudWatch ダッシュボード | Cross-Account Dashboard |
| X-Ray トレース集約 | Cross-Account Tracing |
| SNS アラートルーティング | Aggregated Alert Topic |
| セキュリティ監査ログ | CloudTrail + CloudWatch Logs |
| コスト可視化 | Cost Explorer + タグベース配分 |

---

## アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Shared Services Account                               │
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ CloudWatch       │  │ X-Ray            │  │ SNS Aggregated       │  │
│  │ Observability    │  │ Cross-Account    │  │ Alerts               │  │
│  │ Sink             │  │ Group            │  │                      │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│           │                     │                        │              │
│           ▼                     ▼                        ▼              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              Cross-Account Dashboard                              │  │
│  │  • Lambda Invocations/Errors (All Accounts)                      │  │
│  │  • Step Functions Executions (All Accounts)                      │  │
│  │  • Processing Latency (Custom Metrics)                           │  │
│  │  • X-Ray Service Map                                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────────────────────────────┐   │
│  │ Troubleshooting  │  │ Metric Delivery Role                     │   │
│  │ Role (Read-Only) │  │ (Workload → Shared Services)             │   │
│  └──────────────────┘  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
          ▲                       ▲                        ▲
          │ Sharing Link          │ X-Ray Traces           │ SNS Publish
          │                       │                        │
┌─────────┴───────────────────────┴────────────────────────┴──────────────┐
│                    Workload Account A                                     │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ Lambda       │  │ Step         │  │ CloudWatch   │                  │
│  │ Functions    │  │ Functions    │  │ Alarms       │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    Workload Account B                                     │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ Lambda       │  │ Step         │  │ CloudWatch   │                  │
│  │ Functions    │  │ Functions    │  │ Alarms       │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## CloudWatch Cross-Account Observability

### 仕組み

CloudWatch Cross-Account Observability は **Sink**（受信側）と **Sharing Link**（送信側）で構成される:

1. **Sink**: 共有サービスアカウントに作成。メトリクス/ログ/トレースの受信先
2. **Sharing Link**: 各ワークロードアカウントに作成。Sink にデータを送信

### Sink の設定（共有サービスアカウント）

テンプレート [`shared/cfn/shared-services-observability.yaml`](../../shared/cfn/shared-services-observability.yaml) で自動作成される。

```yaml
# Sink Policy: Organization 内のアカウントからのリンクを許可
Policy:
  Version: "2012-10-17"
  Statement:
    - Effect: Allow
      Principal: "*"
      Action: ["oam:CreateLink", "oam:UpdateLink"]
      Condition:
        ForAnyValue:StringEquals:
          aws:PrincipalOrgID: "o-example123"
        ForAllValues:StringEquals:
          oam:ResourceTypes:
            - "AWS::CloudWatch::Metric"
            - "AWS::Logs::LogGroup"
            - "AWS::XRay::Trace"
```

### Sharing Link の設定（ワークロードアカウント）

各ワークロードアカウントで以下のコマンドを実行:

```bash
aws oam create-link \
  --label-template "workload-$AccountName" \
  --resource-types \
    AWS::CloudWatch::Metric \
    AWS::Logs::LogGroup \
    AWS::XRay::Trace \
  --sink-identifier arn:aws:oam:ap-northeast-1:SHARED_ACCOUNT_ID:sink/SINK_ID
```

### 共有されるデータ

| データタイプ | 内容 | 遅延 |
|---|---|---|
| Metrics | Lambda, Step Functions, カスタムメトリクス | ~1 分 |
| Logs | CloudWatch Logs グループ | ~数秒 |
| Traces | X-Ray トレースデータ | ~数秒 |

---

## X-Ray Cross-Account Tracing

### 設定手順

1. **共有サービスアカウント**: X-Ray Group を作成（テンプレートで自動）
2. **ワークロードアカウント**: Lambda に X-Ray トレーシングを有効化
3. **Sharing Link**: X-Ray Trace を含めてリンク作成

### トレース可視化

共有サービスアカウントの X-Ray コンソールで全アカウントのサービスマップを表示:

```
Workload A Lambda → S3 AP → FSx ONTAP
                  → DynamoDB
                  → SageMaker

Workload B Lambda → S3 AP → FSx ONTAP
                  → Step Functions → Processing Lambda
```

### フィルタ式

```
# 特定アカウントのトレースをフィルタ
service(id(account.id: "111111111111"))

# エラーのあるトレースのみ
service(id(type: "AWS::Lambda::Function")) { fault = true }

# レイテンシが高いトレース
responsetime > 5
```

---

## SNS Aggregated Alerts

### アラートフロー

```
Workload Account CloudWatch Alarm
  → SNS Publish (Cross-Account)
    → Shared Services Aggregated Alert Topic
      → Email Subscription
      → (Optional) Slack Webhook
      → (Optional) PagerDuty
```

### ワークロードアカウントでの設定

ワークロードアカウントの CloudWatch Alarm に共有サービスアカウントの SNS トピック ARN を指定:

```yaml
# ワークロードアカウントの CloudWatch Alarm
AlarmActions:
  - !Sub "arn:aws:sns:${AWS::Region}:SHARED_ACCOUNT_ID:fsxn-s3ap-aggregated-alerts"
```

### アラート分類

| 重要度 | 条件 | アクション |
|---|---|---|
| Critical | Lambda エラー率 > 10% AND Step Functions 失敗 | PagerDuty + Email |
| Warning | Lambda エラー率 > 5% | Email |
| Info | 新規アカウント追加、設定変更 | Email |

---

## IAM ロール定義

### 1. メトリクス/ログ配信ロール

**用途**: ワークロードアカウント → 共有サービスアカウントへのメトリクス/ログ配信

```json
{
  "RoleName": "fsxn-s3ap-shared-metric-delivery-role",
  "Trust": "Workload Account IDs (Organization 条件付き)",
  "Permissions": [
    "cloudwatch:PutMetricData (namespace: FSxN-S3AP)",
    "logs:CreateLogStream",
    "logs:PutLogEvents"
  ]
}
```

### 2. トラブルシューティングロール（Read-Only）

**用途**: 共有サービスアカウント → ワークロードアカウントへの読み取り専用アクセス

```json
{
  "RoleName": "fsxn-s3ap-shared-troubleshooting-role",
  "Trust": "Shared Services Account Root",
  "Permissions": [
    "cloudwatch:Get*/List*/Describe*",
    "logs:Get*/Filter*/Describe*/StartQuery/StopQuery",
    "xray:Get*/BatchGet*",
    "states:Describe*/Get*/List*"
  ]
}
```

---

## Cross-Account Dashboard

### ダッシュボード構成

テンプレートで作成されるダッシュボードには以下のウィジェットが含まれる:

| ウィジェット | メトリクス | 目的 |
|---|---|---|
| Lambda Overview | Invocations, Errors | 全アカウントの Lambda 実行状況 |
| Step Functions | Started, Failed, Succeeded | ワークフロー実行状況 |
| Duration | P90, Average | パフォーマンス監視 |
| S3 Objects | NumberOfObjects | ストレージ使用量 |
| Custom Metrics | ProcessingLatencyMs | FSxN S3AP 固有メトリクス |

### カスタムダッシュボードの追加

```bash
# ダッシュボードの更新
aws cloudwatch put-dashboard \
  --dashboard-name fsxn-s3ap-cross-account-overview \
  --dashboard-body file://custom-dashboard.json
```

---

## デプロイ手順

### 1. 共有サービスアカウントでテンプレートをデプロイ

```bash
aws cloudformation deploy \
  --template-file shared/cfn/shared-services-observability.yaml \
  --stack-name fsxn-shared-observability \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    OrganizationId=o-example123 \
    WorkloadAccountIds=111111111111,222222222222 \
    AlertEmail=ops@example.com \
    EnableXRayTracing=true \
    EnableLogAggregation=true
```

### 2. 各ワークロードアカウントで Sharing Link を作成

```bash
# Sink ARN は Step 1 の出力から取得
SINK_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-shared-observability \
  --query "Stacks[0].Outputs[?OutputKey=='ObservabilitySinkArn'].OutputValue" \
  --output text)

aws oam create-link \
  --label-template "workload-$(aws sts get-caller-identity --query Account --output text)" \
  --resource-types AWS::CloudWatch::Metric AWS::Logs::LogGroup AWS::XRay::Trace \
  --sink-identifier $SINK_ARN
```

### 3. 動作確認

```bash
# Sink に接続されたリンクを確認
aws oam list-links

# ダッシュボードでメトリクスが表示されることを確認
aws cloudwatch get-dashboard \
  --dashboard-name fsxn-s3ap-cross-account-overview
```

---

## 運用ガイダンス

### 新規ワークロードアカウントの追加

1. テンプレートの `WorkloadAccountIds` パラメータに新アカウント ID を追加
2. スタックを更新
3. 新アカウントで Sharing Link を作成
4. ダッシュボードでメトリクスが表示されることを確認

### トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| メトリクスが表示されない | Sharing Link 未作成 | ワークロードアカウントでリンク作成 |
| X-Ray トレースが見えない | Lambda トレーシング無効 | Lambda 設定で TracingConfig を Active に |
| アラートが届かない | SNS サブスクリプション未確認 | メール確認リンクをクリック |
| ダッシュボードが空 | Organization ID 不一致 | Sink Policy の OrgID を確認 |

---

## 関連ドキュメント

- [Cross-Account S3 AP アクセスパターン](./cross-account-s3ap.md)
- [AWS RAM リソース共有](./ram-sharing.md)
- [Cross-Account IAM ロール設計](./cross-account-iam.md)
- [StackSets デプロイガイド](./stacksets-deployment.md)
