# 既存環境影響評価ガイド

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## 概要

本ドキュメントでは、各 Phase の機能を有効化する際に既存環境へ与える影響を評価し、
安全な有効化手順とロールバック方法を提供する。

> **対象範囲**: Phase 1–5（今後のフェーズ追加時に本ドキュメントを更新）

設計原則:
- **Phase 1（UC1–UC5）**: 独立した CloudFormation スタックとして新規デプロイ。既存環境への影響は VPC/サブネットへの ENI 追加のみ
- **Phase 2（UC6–UC14）**: Phase 1 と同様の独立スタック。クロスリージョン API 呼び出しが追加
- **Phase 3（横断機能強化）**: 既存 UC への拡張。全機能は CloudFormation Conditions でオプトイン制御（デフォルト無効）
- **Phase 4（本番 SageMaker・マルチアカウント・イベント駆動）**: 既存 UC9 への拡張 + 新規テンプレート。全機能はオプトイン制御
- **Phase 5（Serverless Inference・コスト最適化・CI/CD・Multi-Region）**: 全機能はオプトイン設計（デフォルト無効）。有効化しない限り既存環境に影響なし

---

## Phase 1: 基盤 UC（UC1–UC5）

### 影響を与えるパラメーター一覧

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| VpcId / PrivateSubnetIds | — (必須) | 指定 VPC | Lambda ENI が作成される |
| EnableS3GatewayEndpoint | "true" | VPC ルートテーブル | ⚠️ 既存 S3 Gateway EP がある場合は競合する |
| EnableVpcEndpoints | "false" | VPC | Interface VPC Endpoints（Secrets Manager, FSx, CloudWatch, SNS）が作成される |
| PrivateRouteTableIds | — (必須) | ルートテーブル | S3 Gateway EP がルートテーブルに関連付けられる |
| ScheduleExpression | "rate(1 hour)" | EventBridge | 定期的に Step Functions を実行する |
| NotificationEmail | — (必須) | SNS | サブスクリプション確認メールが送信される |
| EnableCloudWatchAlarms | "false" | CloudWatch | 新規アラーム作成（既存に影響なし） |

### 考慮事項

#### ⚠️ 注意が必要なパラメーター

1. **EnableS3GatewayEndpoint**: 同一 VPC に既存の S3 Gateway Endpoint がある場合、`false` に設定すること。重複作成はエラーになる。
   - 確認方法: `aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.s3"`
   - 対処: 既存 EP がある場合は `EnableS3GatewayEndpoint=false` でデプロイ

2. **VpcId / PrivateSubnetIds**: Lambda ENI が指定サブネットに作成される。サブネットの IP アドレス枯渇に注意。
   - 確認方法: `aws ec2 describe-subnets --subnet-ids <subnet-id> --query 'Subnets[*].AvailableIpAddressCount'`
   - 目安: Lambda 関数あたり 1 ENI（同一セキュリティグループ・サブネットの Lambda は ENI を共有）

3. **ScheduleExpression**: デプロイ直後からスケジュール実行が開始される。テスト目的の場合はデプロイ後にスケジュールを無効化すること。

### 既存環境への影響なし（新規リソースのみ）

- S3 出力バケット（SSE-KMS 暗号化）
- Step Functions ステートマシン
- Lambda 関数群
- IAM ロール（スタック固有）
- Glue Data Catalog（UC1, UC3）
- Athena Workgroup（UC1, UC3）
- SNS Topic
- CloudWatch Log Groups

---

## Phase 2: 拡張 UC（UC6–UC14）

### 追加の影響パラメーター

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| CrossRegion | "us-east-1" | クロスリージョン API | Textract / Comprehend Medical API を指定リージョンに送信 |
| MapConcurrency | 10 | Step Functions Map | 並列 Lambda 実行数。Lambda 同時実行クォータに影響 |
| LambdaMemorySize | 256–1024 | Lambda | メモリ割り当て。コストに直結 |

### 考慮事項

1. **MapConcurrency**: Lambda 同時実行クォータ（デフォルト 1000）を超えないよう注意。複数 UC を同時実行する場合は合計値を確認。
2. **CrossRegion**: UC7, UC10, UC12, UC13, UC14 で使用。レイテンシ増加（50–200ms）とデータ転送コストが発生。
3. **VPC Endpoints の共有**: 最初の UC デプロイ時に作成した VPC Endpoints は同一 VPC 内の後続 UC で共有可能。2 番目以降は `EnableVpcEndpoints=false` を推奨。

---

## Phase 3: 横断機能強化

### 影響を与えるパラメーター一覧

#### Theme A: Kinesis ストリーミング（UC11 のみ）

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableStreamingMode | "false" | UC11 | 新規リソース作成（Kinesis, DynamoDB, Lambda）。既存ポーリングパスに影響なし |
| KinesisShardCount | 1 | Kinesis | シャード数。コストに直結（$0.015/シャード/時間） |
| KinesisRetentionHours | 24 | Kinesis | データ保持期間 |

#### Theme B: SageMaker Batch Transform（UC9 のみ）

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableSageMakerTransform | "false" | UC9 Step Functions | ⚠️ 有効化すると Step Functions ワークフローに SageMaker パスが追加される |
| MockMode | "true" | SageMaker Invoke Lambda | モックモードでは実際の SageMaker ジョブを作成しない |
| SageMakerInstanceType | "ml.m5.xlarge" | SageMaker | インスタンスタイプ。コストに直結 |

#### Theme C: 可観測性（全 14 UC）

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableXRayTracing | "true" | 全 Lambda + Step Functions | ⚠️ X-Ray トレース送信が開始される（追加コスト: $5/100万トレース） |

### 既存コードへの非破壊保証

- shared/streaming/ と shared/observability.py はオプショナルインポート。未使用時に既存 Lambda に影響なし
- EnableStreamingMode=false（デフォルト）で Phase 2 と同一動作
- EnableSageMakerTransform=false（デフォルト）で Phase 2 と同一動作
- EnableXRayTracing=false で X-Ray SDK 依存なしの動作

---

## Phase 4: 本番 SageMaker・マルチアカウント・イベント駆動

### 影響を与えるパラメーター一覧

#### Theme A: DynamoDB Task Token Store（UC9）

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableDynamoDBTokenStore | "false" | UC9 Lambda | 新規 DynamoDB テーブル作成。Lambda の Token 管理方式が変更される |
| TOKEN_STORAGE_MODE | "direct" | SageMaker Invoke/Callback Lambda | "dynamodb" に変更すると DynamoDB 経由の Token 管理に切り替わる |
| TOKEN_TTL_SECONDS | 86400 | DynamoDB | Token の有効期限（デフォルト 24 時間） |

#### Theme B: Real-time Inference + A/B Testing（UC9）

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableRealtimeEndpoint | "false" | UC9 | ⚠️ 有効化すると SageMaker Real-time Endpoint が作成される（常時稼働コスト発生） |
| EnableABTesting | "false" | UC9 | Multi-Variant Endpoint 構成に変更される |
| EnableModelRegistry | "false" | UC9 | SageMaker Model Package Group が作成される |

#### Theme C/D: Multi-Account / Event-Driven

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| N/A | — | テンプレート提供 / 独立スタック | デプロイしない限り影響なし |

### 考慮事項

1. **EnableRealtimeEndpoint**: **常時稼働コスト**が発生（ml.m5.xlarge: ~$0.23/時間 ≈ $166/月）。検証後は削除を推奨。
2. **EnableDynamoDBTokenStore**: 切り替え時に実行中の SageMaker ジョブがある場合、Callback が失敗する可能性がある。
3. **Multi-Account テンプレート**: クロスアカウント IAM ロールが作成される。External ID と Permission Boundary を必ず設定。

---

## Phase 5: Serverless Inference・コスト最適化・CI/CD・Multi-Region

### 影響を与えるパラメーター一覧

#### Theme A: SageMaker Serverless Inference

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| InferenceType | "none" | UC9 Step Functions | "serverless" に変更すると Choice State のルーティングが変更される |
| ServerlessMemorySizeInMB | 4096 | SageMaker | 新規リソース作成（既存エンドポイントに影響なし） |
| ServerlessMaxConcurrency | 5 | SageMaker | 新規リソース作成 |

#### Theme B: コスト最適化

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableScheduledScaling | "false" | 既存 SageMaker Endpoint | ⚠️ 有効化すると既存エンドポイントのスケーリングが変更される |
| EnableBillingAlarms | "false" | CloudWatch | 新規アラーム作成（既存に影響なし） |
| EnableAutoStop | "false" | 既存 SageMaker Endpoint | ⚠️ 有効化するとアイドルエンドポイントが自動停止される |

#### Theme C: CI/CD

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| N/A | — | GitHub Actions | ワークフローファイル追加のみ。既存デプロイに影響なし |

#### Theme D: Multi-Region

| パラメーター | デフォルト値 | 影響範囲 | 有効化時の影響 |
|------------|------------|---------|-------------|
| EnableMultiRegion | "false" | DynamoDB, Route 53 | ⚠️ 有効化すると DynamoDB テーブルが Global Table に変換される |

### 考慮事項

1. **EnableScheduledScaling**: 既存の SageMaker Endpoint に Scheduled Scaling を適用する。営業時間外にインスタンス数が最小値まで削減される。
   - 注意: `DesiredInstanceCount=0` は Inference Components を使用するエンドポイントでのみ有効。標準エンドポイントの最小値は 1。
   - ロールバック: Scheduled Action を削除

2. **EnableAutoStop**: アイドル状態の SageMaker Endpoint を自動的にスケールダウンする。
   - 保護方法: 重要なエンドポイントに `DoNotAutoStop=true` タグを付与

3. **EnableMultiRegion**: DynamoDB テーブルを Global Table に変換する。**この操作は不可逆**（Global Table から通常テーブルに戻せない）。
   - 前提条件: DynamoDB Streams が有効であること

---

## 影響確認方法

### デプロイ前チェックリスト（全 Phase 共通）

1. [ ] VPC の IP アドレス空き状況を確認
2. [ ] 既存 S3 Gateway Endpoint の有無を確認
3. [ ] Lambda 同時実行クォータの余裕を確認
4. [ ] 対象リージョンでの AI/ML サービス可用性を確認
5. [ ] CloudFormation スタック数の上限を確認（デフォルト 2000）
6. [ ] 全既存テストが PASS することを確認: `pytest shared/tests/ use-cases/*/tests/ -v`
7. [ ] cfn-lint でテンプレートエラーなし: `cfn-lint use-cases/*/template-deploy.yaml`
8. [ ] オプトインパラメーターがデフォルト値（無効）であることを確認
9. [ ] 既存 Step Functions ワークフローが変更なく動作することを確認
10. [ ] 既存 Lambda 関数が新規 Phase モジュールをインポートしていないことを確認

### デプロイ後確認

1. [ ] 既存 Step Functions ワークフローを手動実行して正常完了を確認
2. [ ] CloudWatch メトリクスに異常がないことを確認
3. [ ] Lambda エラー率が増加していないことを確認
4. [ ] VPC Endpoint の状態が "available" であることを確認
5. [ ] 既存 DynamoDB テーブルのスループットに変化がないことを確認

---

## ロールバック手順

### Phase 1/2: スタック削除

```bash
# スタック削除前に S3 バケットを空にする
aws s3 rm s3://<output-bucket> --recursive

# バージョニング有効バケットの場合
aws s3api list-object-versions --bucket <bucket> --query 'Versions[*].{Key:Key,VersionId:VersionId}' | \
  jq -c '.[]' | while read obj; do
    aws s3api delete-object --bucket <bucket> \
      --key $(echo $obj | jq -r '.Key') \
      --version-id $(echo $obj | jq -r '.VersionId')
  done

# CloudFormation スタック削除
aws cloudformation delete-stack --stack-name <stack-name>
aws cloudformation wait stack-delete-complete --stack-name <stack-name>
```

### Phase 3: 機能無効化

```bash
# Kinesis ストリーミング無効化（UC11）
aws cloudformation update-stack \
  --stack-name <uc11-stack> \
  --use-previous-template \
  --parameters ParameterKey=EnableStreamingMode,ParameterValue=false

# SageMaker Transform 無効化（UC9）
aws cloudformation update-stack \
  --stack-name <uc9-stack> \
  --use-previous-template \
  --parameters ParameterKey=EnableSageMakerTransform,ParameterValue=false

# X-Ray 無効化（全 UC）
aws cloudformation update-stack \
  --stack-name <stack> \
  --use-previous-template \
  --parameters ParameterKey=EnableXRayTracing,ParameterValue=false
```

### Phase 4: 機能無効化

```bash
# Real-time Endpoint 削除（UC9）— 常時稼働コスト停止
aws sagemaker delete-endpoint --endpoint-name <endpoint-name>
aws sagemaker delete-endpoint-config --endpoint-config-name <config-name>

# DynamoDB Token Store 無効化（UC9）
aws cloudformation update-stack \
  --stack-name <uc9-stack> \
  --use-previous-template \
  --parameters ParameterKey=EnableDynamoDBTokenStore,ParameterValue=false

# Event-Driven Prototype 削除
aws cloudformation delete-stack --stack-name <event-driven-stack>
```

### Phase 5: 機能無効化

```bash
# Scheduled Scaling 無効化
aws application-autoscaling delete-scheduled-action \
  --service-namespace sagemaker \
  --scheduled-action-name ScaleUpBusinessHours \
  --resource-id endpoint/<endpoint-name>/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount

# Auto-Stop Lambda 無効化
aws events disable-rule --name <auto-stop-rule-name>

# Billing Alarm 削除
aws cloudformation delete-stack --stack-name <billing-alarm-stack>

# Serverless Endpoint 削除
aws sagemaker delete-endpoint --endpoint-name <serverless-endpoint>
```

### 完全ロールバック（コード削除）

**Phase 3 削除対象:**
- `shared/streaming/`, `shared/observability.py`
- `shared/cfn/observability-dashboard.yaml`, `shared/cfn/alert-automation.yaml`
- `retail-catalog/functions/stream_producer/`, `retail-catalog/functions/stream_consumer/`
- `autonomous-driving/functions/sagemaker_invoke/`, `autonomous-driving/functions/sagemaker_callback/`

**Phase 4 削除対象:**
- `shared/task_token_store.py`
- `shared/cfn/cross-account-*.yaml`, `shared/cfn/ram-resource-share.yaml`, `shared/cfn/stacksets-admin.yaml`
- `use-cases/uc09-autonomous-driving/lambdas/realtime_invoke/`, `use-cases/uc09-autonomous-driving/lambdas/inference_comparison/`
- `event-driven-prototype/`, `scripts/register_model.py`, `scripts/compare_polling_vs_event.py`
- `docs/multi-account/`, `docs/event-driven/`

**Phase 5 削除対象:**
- `shared/routing.py`, `shared/cost_validation.py`, `shared/lambdas/auto_stop/`
- `shared/cfn/scheduled-scaling.yaml`, `shared/cfn/billing-alarm.yaml`, `shared/cfn/auto-stop-resources.yaml`
- `shared/cfn/global-task-token-store.yaml`, `shared/cfn/multi-region-base.yaml`
- `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
- `security/cfn-guard-rules/`

---

## 安全な有効化手順

### 推奨順序（全 Phase 統合）

| 順序 | 機能 | Phase | リスク | 備考 |
|------|------|-------|--------|------|
| 1 | UC1 デプロイ（最小構成） | 1 | 低 | 独立スタック。Athena + Bedrock のみ |
| 2 | 可観測性（X-Ray + EMF） | 3 | 低 | graceful degradation で既存に影響なし |
| 3 | CI/CD パイプライン | 5 | なし | ワークフローファイル追加のみ |
| 4 | Kinesis ストリーミング（UC11） | 3 | 低 | 既存ポーリングパスに影響なし |
| 5 | SageMaker Batch Transform（UC9） | 3 | 低 | MockMode=true で安全に検証 |
| 6 | DynamoDB Task Token Store | 4 | 低 | 新規テーブル作成のみ |
| 7 | Serverless Inference | 5 | 低 | 新規リソース作成のみ |
| 8 | Event-Driven Prototype | 4 | 低 | 独立スタック |
| 9 | Billing Alarms | 5 | 低 | 新規アラーム作成のみ |
| 10 | Real-time Endpoint | 4 | 中 | ⚠️ 常時稼働コスト発生 |
| 11 | Scheduled Scaling | 5 | 中 | ⚠️ 既存 Endpoint のスケーリング変更 |
| 12 | Auto-Stop | 5 | 中 | ⚠️ アイドル Endpoint 自動停止 |
| 13 | Multi-Account | 4 | 中 | ⚠️ クロスアカウント IAM ロール作成 |
| 14 | Multi-Region | 5 | 高 | ⚠️ **不可逆** — DynamoDB Global Table 変換 |

---

## コスト影響サマリー

| Phase | 機能 | デフォルト状態 | 有効化時の追加コスト |
|-------|------|-------------|-----------------|
| 1/2 | VPC Endpoints | 無効 | ~$29/月（VPC 単位で共有可） |
| 1/2 | CloudWatch Alarms | 無効 | ~$0.10/アラーム/月 |
| 1/2 | Lambda 実行 | 有効 | 従量課金（~$0.20/100万リクエスト） |
| 3 | Kinesis Data Stream | 無効 | ~$11/シャード/月 + データ転送 |
| 3 | X-Ray | 有効 | ~$5/100万トレース |
| 3 | CloudWatch EMF | 有効 | ログストレージ（~$0.50/GB） |
| 4 | DynamoDB Token Store | 無効 | PAY_PER_REQUEST（~$0.25/100万書込） |
| 4 | Real-time Endpoint | 無効 | ⚠️ ~$166/月（ml.m5.xlarge 常時稼働） |
| 4 | Event-Driven Prototype | 別スタック | 従量課金のみ |
| 5 | Serverless Inference | 無効 | 従量課金（コールドスタートあり） |
| 5 | Scheduled Scaling | 無効 | なし（既存 Endpoint のスケジュール変更） |
| 5 | Billing Alarms | 無効 | ~$0.30/月（3 アラーム） |
| 5 | Auto-Stop | 無効 | Lambda 実行コストのみ |
| 5 | Multi-Region | 無効 | DynamoDB Global Table 追加コスト |

---

## 関連ドキュメント

- [コスト構造分析](cost-analysis.md)
- [ストリーミング vs ポーリング選択ガイド](streaming-vs-polling-guide.md)
- [推論コスト比較ガイド](inference-cost-comparison.md)
- [コスト最適化ベストプラクティスガイド](cost-optimization-guide.md)
- [Model Registry ガイド](model-registry-guide.md)
- [Multi-Account PoC 結果](multi-account/poc-results.md)
- [Event-Driven アーキテクチャ設計](event-driven/architecture-design.md)
- [Serverless Inference コールドスタート特性](serverless-inference-cold-start.md)
- [CI/CD ガイド](ci-cd-guide.md)
- [Multi-Region Disaster Recovery](multi-region/disaster-recovery.md)
- [デプロイ手順書](guides/deployment-guide.md)
- [トラブルシューティング](guides/troubleshooting-guide.md)

---

*本ドキュメントは FSxN S3AP Serverless Patterns の既存環境影響評価ガイドです。*
