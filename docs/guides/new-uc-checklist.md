# New UC Template Checklist (Phase 9 Baseline)

After Phase 9, new UCs should start from the unified baseline. Use this
checklist when adding a new UC to the pattern library.

---

## Template Parameters (required)

- [ ] `OutputDestination` (STANDARD_S3 / FSXN_S3AP, default: STANDARD_S3)
- [ ] `OutputS3APAlias` (empty default, fallback to S3AccessPointAlias)
- [ ] `OutputS3APPrefix` (default: "ai-outputs/")
- [ ] `EnableCloudWatchAlarms` (default: "false")
- [ ] `EnableVpcEndpoints` (default: "false")
- [ ] `EnableS3GatewayEndpoint` (default: "true")
- [ ] `LambdaMemorySize` (default: 512)
- [ ] `LambdaTimeout` (default: 900)
- [ ] `NotificationEmail`
- [ ] `TriggerMode` (POLLING / EVENT_DRIVEN / HYBRID, default: POLLING) — Phase 10
- [ ] `AlarmProfile` (BATCH / REALTIME / HIGH_VOLUME / CUSTOM, default: UC 別) — Phase 10
- [ ] `CustomFailureThreshold` (default: 10) — Phase 10
- [ ] `CustomErrorThreshold` (default: 3) — Phase 10
- [ ] `MaxConcurrencyUpperBound` (default: 40) — Phase 10
- [ ] `OntapApiRateLimit` (default: 100) — Phase 10
- [ ] `EnableCostScheduling` (default: "false") — Phase 10
- [ ] `BusinessHoursStart` (default: 9) — Phase 10
- [ ] `BusinessHoursEnd` (default: 18) — Phase 10

## Conditions (required)

- [ ] `UseStandardS3` / `UseFsxnS3AP` / `HasOutputS3APAlias`
- [ ] `CreateCloudWatchAlarms`
- [ ] `HasS3AccessPointName`
- [ ] `EnablePolling` / `EnableEventDriven` / `EnableIdempotency` — Phase 10
- [ ] `UseCustomProfile` — Phase 10
- [ ] `EnableCostSchedulingCondition` — Phase 10

## Lambda Functions

- [ ] Discovery Lambda: 512MB / 900s, VPC-attached
- [ ] AI/ML output Lambdas: use `OutputWriter.from_env()` (not direct s3_client)
- [ ] All Lambdas: `OUTPUT_DESTINATION`, `OUTPUT_S3AP_ALIAS`, `OUTPUT_S3AP_PREFIX` env vars

## S3 Access Point（全 UC 共通 — 必読）

⚠️ **FSx ONTAP S3 AP の制約** — 詳細: `docs/guides/s3ap-fsxn-specification.md`

- [ ] S3 AP は**読み取り専用**。PutObject は使用不可（書き込みは NFS/SMB のみ）
- [ ] IAM ポリシーの Resource ARN: `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用（エイリアスではない）
- [ ] GetObject の Resource: `arn:aws:s3:{region}:{account}:accesspoint/{name}/object/*`
- [ ] `s3:GetBucketLocation` は S3 AP では無効（使用しないこと）
- [ ] VPC 内 Lambda から S3 AP にアクセスする場合: **タイムアウトする**（S3 Gateway EP 経由不可）
- [ ] S3 AP アクセスが必要な Lambda は VPC 外実行 or NAT Gateway 経由にする
- [ ] S3 AP リソースポリシーが未設定の場合、IAM ポリシーだけでは AccessDenied になる場合がある

## Observability (gated by CreateCloudWatchAlarms)

- [ ] `StepFunctionsFailureAlarm` (AWS::CloudWatch::Alarm)
- [ ] `DiscoveryErrorAlarm` (AWS::CloudWatch::Alarm)
- [ ] `StepFunctionsFailureEventRule` (AWS::Events::Rule)
- [ ] `EventBridgeToSnsPolicy` (AWS::SNS::TopicPolicy)

## IAM

- [ ] S3AP write policies use dual-format (alias + full ARN via `!If HasS3AccessPointName`)
- [ ] No `s3:*` or `Resource: "*"` in Lambda execution roles
- [ ] Secrets Manager access scoped to specific secret ARN

## Deployment

- [ ] No assumption that shared VPC Endpoints already exist
- [ ] `deploy_generic_ucs.sh` auto-detection handles endpoint creation
- [ ] Template passes `cfn-lint` with 0 real errors
- [ ] Template passes `check_s3ap_iam_patterns.py`
- [ ] Template passes `check_conditional_refs.py`

## Testing

- [ ] Unit tests for all handler functions
- [ ] Tests do NOT patch `handler.boto3` if handler doesn't import boto3
- [ ] `check_handler_names.py` reports 0 undefined names

## Documentation

- [ ] `<uc>/docs/demo-guide.md` (Japanese) + 7 language variants
- [ ] Screenshot section with recommended capture list
- [ ] Processing time estimates (if applicable)

## Phase 11 追加項目

### TriggerMode 統合

- [ ] `TriggerMode` パラメータ (POLLING / EVENT_DRIVEN / HYBRID, default: POLLING)
- [ ] `FPolicyEventBusName` パラメータ (default: "fsxn-fpolicy-events")
- [ ] Conditions: `IsPolling`, `IsEventDriven`, `IsHybrid`, `IsPollingOrHybrid`, `IsEventDrivenOrHybrid`
- [ ] EventBridge Scheduler に `Condition: IsPollingOrHybrid`
- [ ] SchedulerRole に `Condition: IsPollingOrHybrid`
- [ ] FPolicy EventBridge Rule (`Condition: IsEventDrivenOrHybrid`)
- [ ] FPolicyEventRuleRole (`Condition: IsEventDrivenOrHybrid`)

### EventBridge ディスパッチルール

- [ ] EventPattern: `source: ["fsxn.fpolicy"]`, `detail-type: ["FPolicy File Operation"]`
- [ ] `detail.file_path`: UC 固有の prefix フィルタ（主フィルタ）
- [ ] `detail.file_path`: UC 固有の suffix フィルタ（補助フィルタ）
- [ ] `detail.operation_type`: UC が関心のある操作のみ
- [ ] ターゲット: UC の Step Functions StateMachine ARN
- [ ] `docs/guides/fpolicy-uc-routing.md` にルーティング情報を追記

### File Readiness（大容量ファイル UC 向け）

大容量ファイル（.parquet, .tiff, .las, .bam, .gds 等）を処理する UC では、
FPolicy イベント到着時にファイル書き込みが完了していない可能性がある。
以下のいずれかの readiness strategy を実装すること:

- [ ] **Rename-based commit**: 一時パスに書き込み → 完了後に最終パスへ rename。`rename` イベントのみ処理。
- [ ] **Marker file**: `.done` / `_SUCCESS` マーカーファイルを検知して処理開始。
- [ ] **Size-stability check**: N 秒間隔でファイルサイズを確認、連続 2 回同一なら処理開始。
- [ ] **WRITE_COMPLETE_DELAY_SEC**: FPolicy Server の遅延設定（小ファイル向け、デフォルト 5 秒）。

### Idempotency（HYBRID モード UC 向け）

- [ ] Step Functions の最初のステップに Idempotency Check を追加
- [ ] `IDEMPOTENCY_TABLE` 環境変数を設定
- [ ] `USE_CASE` 環境変数を設定（パーティションキーのプレフィックス）
- [ ] `DEDUP_WINDOW_MINUTES` を UC 要件に合わせて調整（デフォルト: 5 分）


### File Readiness 推奨パターン（UC 別）

| ワークロード種別 | 代表 UC | 推奨 Readiness パターン |
|----------------|---------|----------------------|
| 小容量 JSON/CSV センサーデータ | manufacturing-analytics | fixed delay or size-stability |
| 大容量地理空間ファイル | smart-city-geospatial, energy-seismic | marker file or size-stability |
| メディア/VFX 大容量ファイル | media-vfx | marker file |
| ゲノミクス BAM/FASTQ | genomics-pipeline | rename-based commit |
| EDA アーティファクト | semiconductor-eda | marker file + manifest |
| 医療画像 DICOM | healthcare-dicom | size-stability |
| PDF/ドキュメント | legal-compliance, financial-idp | fixed delay (5s) |
| 自動運転 LiDAR/カメラ | autonomous-driving | rename-based commit |

### Step Functions WaitForFileReady 共通パターン

大容量ファイル UC では、Step Functions の最初のステップに以下のような
ファイル準備確認ロジックを追加することを推奨:

```json
{
  "WaitForFileReady": {
    "Type": "Task",
    "Resource": "${FileReadinessCheckerFunction.Arn}",
    "Parameters": {
      "file_path.$": "$.file_path",
      "strategy": "size-stability",
      "check_interval_sec": 10,
      "stable_count": 2
    },
    "Retry": [{"ErrorEquals": ["FileNotReady"], "IntervalSeconds": 10, "MaxAttempts": 6}],
    "Next": "ProcessFile"
  }
}
```
