# コスト最適化ベストプラクティスガイド

🌐 **Language / 言語**: [日本語](cost-optimization-guide.md) | [English](cost-optimization-guide-en.md)

## 概要

本ドキュメントは、FSxN S3AP Serverless Patterns の全 Phase（1–5）を横断したコスト最適化のベストプラクティスを提供します。デプロイプロファイル別の月額見積もり、コスト削減チェックリスト、および CloudFormation パラメータ推奨を含みます。

---

## コンポーネント別コスト分析

### Phase 1–2: 基盤コンポーネント

| コンポーネント | 課金モデル | 月額概算（ap-northeast-1） | 最適化ポイント |
|--------------|-----------|--------------------------|--------------|
| Lambda（14 UC） | リクエスト + 実行時間 | $1–42 | メモリ最適化、実行時間短縮 |
| Step Functions | 状態遷移数 | $0.50–5 | Map State の並列度調整 |
| EventBridge Scheduler | スケジュール数 | $0（無料枠内） | 不要スケジュールの無効化 |
| S3 API（S3 AP 経由） | リクエスト数 + データ転送 | $0.50–10 | ListObjects のページサイズ最適化 |
| Secrets Manager | シークレット数 + API コール | $0.50–1 | キャッシュ活用 |
| Interface VPC Endpoints | 時間課金 + データ処理 | $0–36 | **オプショナル**（最大コスト要因） |
| S3 Gateway Endpoint | 無料 | $0 | 常に有効化推奨 |
| SNS | メッセージ数 | $0.01–0.50 | — |

### Phase 3: ストリーミング・ML・可観測性

| コンポーネント | 課金モデル | 月額概算 | 最適化ポイント |
|--------------|-----------|---------|--------------|
| Kinesis Data Streams | シャード時間 + PUT レコード | $15–30/シャード | オンデマンドモード検討 |
| SageMaker Batch Transform | ジョブ実行時間 | $0–50（ジョブ頻度依存） | 小バッチの統合 |
| X-Ray | トレース数 | $0–5 | サンプリングレート調整 |
| CloudWatch EMF | メトリクス数 | $0.30/メトリクス | 高カーディナリティ回避 |
| DynamoDB（状態テーブル） | RCU/WCU | $0–1 | TTL で自動クリーンアップ |

### Phase 4: 本番 SageMaker・マルチアカウント

| コンポーネント | 課金モデル | 月額概算 | 最適化ポイント |
|--------------|-----------|---------|--------------|
| SageMaker Real-time Endpoint | インスタンス時間 | $215/ml.m5.large | **Scheduled Scaling** |
| DynamoDB Task Token Store | PAY_PER_REQUEST | ~$0 | TTL 24h で自動削除 |
| Model Registry | メタデータのみ | $0 | — |
| Event-Driven Prototype | イベント数 | ~$0 | — |

### Phase 5: Serverless Inference・コスト管理

| コンポーネント | 課金モデル | 月額概算 | 最適化ポイント |
|--------------|-----------|---------|--------------|
| SageMaker Serverless Inference | リクエスト + 処理時間 | $1–300 | MemorySize 最適化 |
| Serverless PC | PC 数 × 時間 | $50–160/PC | 必要最小限の PC 数 |
| Scheduled Scaling | 無料（Auto Scaling 機能） | $0 | 営業時間外スケールダウン |
| Billing Alarms | アラーム数 | $0.10/アラーム | — |
| Auto-Stop Lambda | リクエスト + 実行時間 | ~$0 | — |
| DynamoDB Global Tables | リージョン × RCU/WCU | $0–2 | PAY_PER_REQUEST |

---

## デプロイプロファイル

### Minimal プロファイル（月額 ~$3–10）

**対象**: PoC、デモ、学習目的

```yaml
# CloudFormation パラメータ
EnableVpcEndpoints: "false"
EnableCloudWatchAlarms: "false"
EnableKinesisStreaming: "false"
EnableRealtimeEndpoint: "false"
EnableABTesting: "false"
EnableModelRegistry: "false"
InferenceType: "none"
EnableScheduledScaling: "false"
EnableBillingAlarms: "false"
EnableAutoStop: "false"
EnableMultiRegion: "false"
```

| コンポーネント | 月額 |
|--------------|------|
| Lambda（1–2 UC のみ） | $0.50–2 |
| Step Functions | $0.25–1 |
| S3 API | $0.50–2 |
| Secrets Manager | $0.50 |
| EventBridge | $0 |
| **合計** | **~$3–10** |

### Standard プロファイル（月額 ~$50–150）

**対象**: 開発環境、小規模本番

```yaml
# CloudFormation パラメータ
EnableVpcEndpoints: "true"
EnableCloudWatchAlarms: "true"
EnableKinesisStreaming: "false"
EnableRealtimeEndpoint: "false"
InferenceType: "serverless"
ServerlessMemorySizeInMB: 4096
ServerlessMaxConcurrency: 5
ServerlessProvisionedConcurrency: 0
EnableScheduledScaling: "false"
EnableBillingAlarms: "true"
BillingWarningThreshold: 100
BillingCriticalThreshold: 200
BillingEmergencyThreshold: 500
EnableAutoStop: "true"
EnableMultiRegion: "false"
```

| コンポーネント | 月額 |
|--------------|------|
| Lambda（全 14 UC） | $5–42 |
| Step Functions | $2–5 |
| Interface VPC Endpoints | $36 |
| Serverless Inference | $1–30 |
| CloudWatch Alarms | $1 |
| Billing Alarms | $0.30 |
| その他 | $5–10 |
| **合計** | **~$50–150** |

### Full プロファイル（月額 ~$300–700）

**対象**: 本番環境、高可用性要件

```yaml
# CloudFormation パラメータ
EnableVpcEndpoints: "true"
EnableCloudWatchAlarms: "true"
EnableKinesisStreaming: "true"
EnableRealtimeEndpoint: "true"
EnableABTesting: "true"
EnableAutoScaling: "true"
MinCapacity: 1
MaxCapacity: 4
InferenceType: "provisioned"
EnableScheduledScaling: "true"
BusinessHoursStart: 9
BusinessHoursEnd: 18
EnableBillingAlarms: "true"
BillingWarningThreshold: 500
BillingCriticalThreshold: 1000
BillingEmergencyThreshold: 2000
EnableAutoStop: "true"
EnableMultiRegion: "true"
PrimaryRegion: "ap-northeast-1"
SecondaryRegion: "us-east-1"
```

| コンポーネント | 月額 |
|--------------|------|
| Lambda（全 14 UC） | $10–42 |
| Step Functions | $3–5 |
| Interface VPC Endpoints | $36 |
| SageMaker Real-time Endpoint | $215–430 |
| Kinesis Data Streams | $15–30 |
| DynamoDB Global Tables | $1–5 |
| CloudWatch（Alarms + Metrics） | $5–10 |
| X-Ray | $2–5 |
| その他 | $10–20 |
| **合計** | **~$300–700** |

---

## コスト削減チェックリスト

### 1. CloudFormation Conditions による無効化

最も効果的なコスト削減は、不要な機能を Conditions で無効化することです:

| 機能 | パラメータ | 削減額/月 |
|------|-----------|----------|
| Interface VPC Endpoints | `EnableVpcEndpoints=false` | ~$36 |
| SageMaker Real-time Endpoint | `EnableRealtimeEndpoint=false` | ~$215+ |
| Kinesis Data Streams | `EnableKinesisStreaming=false` | ~$15–30 |
| A/B Testing（追加バリアント） | `EnableABTesting=false` | ~$215/バリアント |
| Multi-Region レプリケーション | `EnableMultiRegion=false` | ~$5–20 |

### 2. Scheduled Scaling（営業時間スケーリング）

SageMaker Endpoint を営業時間のみ稼働させることで、最大 60% のコスト削減:

```yaml
# shared/cfn/scheduled-scaling.yaml
BusinessHoursStart: 9    # 09:00 JST スケールアップ
BusinessHoursEnd: 18     # 18:00 JST スケールダウン
EnableWeekendShutdown: "true"  # 週末シャットダウン
```

| 構成 | 月額 | 削減率 |
|------|------|-------|
| 24/7 稼働 | $215 | — |
| 平日 9–18 時のみ | $90 | 58% |
| 平日 9–18 時 + 週末停止 | $65 | 70% |

### 3. DynamoDB TTL による自動クリーンアップ

Task Token Store のレコードを 24 時間 TTL で自動削除:

```python
# TTL 設定（shared/task_token_store.py）
'ttl': int(time.time()) + 86400  # 24 時間後に自動削除
```

- ストレージコスト削減
- 不要データの蓄積防止
- Global Tables レプリケーションコスト削減

### 4. Lambda メモリ最適化

Lambda のメモリ設定を最適化することで、実行時間とコストのバランスを改善:

| Lambda 種別 | 推奨メモリ | 理由 |
|------------|-----------|------|
| Discovery Lambda | 256 MB | S3 ListObjects のみ、CPU 負荷低 |
| Processing Lambda（テキスト） | 512 MB | テキスト処理、中程度の CPU |
| Processing Lambda（画像） | 1024 MB | 画像処理、高 CPU |
| Report Lambda | 256 MB | レポート生成、低 CPU |
| Auto-Stop Lambda | 256 MB | API コールのみ |
| Realtime Invoke Lambda | 512 MB | SageMaker API コール + リトライ |

### 5. EventBridge Scheduler の最適化

不要なスケジュール実行を削減:

```yaml
# 本番: 1 時間ごと
ScheduleExpression: "rate(1 hour)"

# 開発: 手動実行のみ（スケジュール無効化）
ScheduleState: "DISABLED"

# 低頻度: 1 日 1 回
ScheduleExpression: "rate(1 day)"
```

### 6. Auto-Stop Lambda による未使用リソース検出

```yaml
# shared/cfn/auto-stop-resources.yaml
IdleThresholdMinutes: 60  # 60 分間ゼロリクエストで停止
DryRun: "false"           # 本番: 実際に停止
```

- 未使用 SageMaker Endpoint の自動スケールダウン
- 推定削減額の EMF メトリクス出力
- `DoNotAutoStop=true` タグで保護可能

### 7. X-Ray サンプリングレート調整

```yaml
# 開発: 全トレース
TracingConfig:
  Mode: Active

# 本番: サンプリング（コスト削減）
# X-Ray サンプリングルールで 5% に設定
```

---

## CloudFormation パラメータマトリクス

### コストプロファイル別推奨パラメータ

| パラメータ | Minimal | Standard | Full |
|-----------|---------|----------|------|
| `EnableVpcEndpoints` | false | true | true |
| `EnableCloudWatchAlarms` | false | true | true |
| `EnableKinesisStreaming` | false | false | true |
| `EnableRealtimeEndpoint` | false | false | true |
| `EnableABTesting` | false | false | true |
| `InferenceType` | none | serverless | provisioned |
| `ServerlessMemorySizeInMB` | — | 4096 | — |
| `ServerlessMaxConcurrency` | — | 5 | — |
| `ServerlessProvisionedConcurrency` | — | 0 | — |
| `EnableScheduledScaling` | false | false | true |
| `BusinessHoursStart` | — | — | 9 |
| `BusinessHoursEnd` | — | — | 18 |
| `EnableWeekendShutdown` | — | — | true |
| `EnableBillingAlarms` | false | true | true |
| `BillingWarningThreshold` | — | 100 | 500 |
| `BillingCriticalThreshold` | — | 200 | 1000 |
| `BillingEmergencyThreshold` | — | 500 | 2000 |
| `EnableAutoStop` | false | true | true |
| `IdleThresholdMinutes` | — | 60 | 60 |
| `EnableMultiRegion` | false | false | true |
| **月額概算** | **$3–10** | **$50–150** | **$300–700** |

---

## コスト監視とアラート

### Billing Alarm 3 段階設定

```yaml
# shared/cfn/billing-alarm.yaml
WarningThreshold: 100    # 月額 $100 超過で通知
CriticalThreshold: 200   # 月額 $200 超過で通知
EmergencyThreshold: 500  # 月額 $500 超過で緊急通知
```

### 推奨アラート設定

| レベル | 閾値 | アクション |
|-------|------|----------|
| Warning | 予算の 70% | メール通知、コスト確認 |
| Critical | 予算の 90% | メール + Slack 通知、不要リソース停止検討 |
| Emergency | 予算の 120% | 即座に Auto-Stop 実行、エスカレーション |

### Auto-Stop Lambda メトリクス

| メトリクス | 説明 |
|-----------|------|
| `EndpointsChecked` | チェックしたエンドポイント数 |
| `EndpointsStoppedCount` | 停止したエンドポイント数 |
| `EstimatedSavingsPerHour` | 推定時間あたり削減額（USD） |

---

## コスト最適化の段階的アプローチ

### Step 1: 可視化（Week 1）

1. Billing Alarm を有効化
2. CloudWatch ダッシュボードでコスト推移を確認
3. Cost Explorer でサービス別コストを分析

### Step 2: 即効性のある削減（Week 2）

1. 不要な VPC Endpoints を無効化
2. 未使用 SageMaker Endpoint を停止
3. Lambda メモリを最適化

### Step 3: 自動化（Week 3–4）

1. Scheduled Scaling を設定
2. Auto-Stop Lambda を有効化
3. DynamoDB TTL を確認

### Step 4: 継続的最適化（Monthly）

1. コストレポートのレビュー
2. 使用パターンに基づくプロファイル調整
3. 新機能のコスト影響評価

---

## 関連ドキュメント

- [コスト構造分析](cost-analysis.md)
- [推論コスト比較ガイド](inference-cost-comparison.md)
- [Serverless Inference コールドスタート特性](serverless-inference-cold-start.md)
- [CI/CD ガイド](ci-cd-guide.md)

---

*本ドキュメントは FSxN S3AP Serverless Patterns Phase 5 の一部です。*
