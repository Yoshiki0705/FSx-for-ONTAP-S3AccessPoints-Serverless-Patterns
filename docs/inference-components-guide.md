# SageMaker Inference Components ガイド

## 概要

SageMaker Inference Components は、単一の SageMaker Endpoint 上に複数のモデルをホストし、各モデルに対して独立したスケーリングポリシーを適用できる機能です。`MinInstanceCount=0` を設定することで、真の scale-to-zero を実現し、アイドル時のコストをゼロにできます。

### Inference Components の特徴

- **マルチモデルホスティング**: 1 つの Endpoint に複数モデルを配置
- **独立スケーリング**: 各 Component に個別の Auto Scaling ポリシー
- **真の scale-to-zero**: `MinInstanceCount=0` でインスタンスを完全に解放
- **コスト最適化**: 使用時のみインスタンスが起動（アイドル時コスト = $0）
- **scale-from-zero**: リクエスト到着時に自動でインスタンスを起動（数分のレイテンシ）

## 4 パターン比較表

| 項目 | Batch Transform | Serverless Inference | Provisioned Endpoint | Inference Components |
|------|----------------|---------------------|---------------------|---------------------|
| **レイテンシ** | 分〜時間 | ミリ秒〜秒 | ミリ秒 | ミリ秒（起動後） |
| **コールドスタート** | N/A（ジョブ起動） | 〜180 秒 | なし | 数分（scale-from-zero） |
| **アイドルコスト** | $0 | $0（ただし制限あり） | 常時課金 | $0（MinCount=0 時） |
| **最大ペイロード** | 100 MB | 6 MB | 6 MB | 6 MB |
| **同時実行** | 並列ジョブ | 最大 200 | インスタンス数依存 | CopyCount 依存 |
| **scale-to-zero** | ✅（ジョブ完了後） | ✅（自動） | ❌ | ✅（MinCount=0） |
| **マルチモデル** | ❌ | ❌ | ❌（Multi-Variant のみ） | ✅ |
| **ユースケース** | 大量バッチ処理 | 低頻度・軽量推論 | 低レイテンシ必須 | コスト最適化 + 柔軟性 |

### 選択ガイドライン

```
推論頻度が低い（1日数回以下）
  └── レイテンシ要件が緩い → Batch Transform
  └── レイテンシ要件あり → Inference Components (scale-to-zero)

推論頻度が中程度（1時間に数回）
  └── コスト重視 → Inference Components
  └── レイテンシ重視 → Serverless Inference

推論頻度が高い（常時リクエスト）
  └── Provisioned Endpoint
```

## scale-to-zero の仕組み

### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│ SageMaker Endpoint (常時存在)                                │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Inference Component (MinInstanceCount=0)             │    │
│  │                                                      │    │
│  │  [アイドル時] インスタンス数 = 0 (コスト $0)         │    │
│  │  [リクエスト到着] → Auto Scaling → インスタンス起動  │    │
│  │  [一定時間アイドル] → Scale-in → インスタンス数 = 0  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 設定要素

1. **ScalableTarget**: `MinCapacity: 0` で scale-to-zero を有効化
2. **Step Scaling Policy**: `NoCapacityInvocationFailures` メトリクスでトリガー
3. **CloudWatch Alarm**: インスタンス不足時のアラーム → スケーリングアクション

### CloudFormation 設定例

```yaml
# ScalableTarget — MinCapacity: 0 で scale-to-zero
ComponentsScalableTarget:
  Type: AWS::ApplicationAutoScaling::ScalableTarget
  Properties:
    MaxCapacity: 4
    MinCapacity: 0  # ← 真の scale-to-zero
    ResourceId: !Sub "inference-component/${ComponentName}"
    ScalableDimension: "sagemaker:inference-component:DesiredCopyCount"
    ServiceNamespace: sagemaker

# Step Scaling Policy — scale-from-zero トリガー
ComponentsStepScalingPolicy:
  Type: AWS::ApplicationAutoScaling::ScalingPolicy
  Properties:
    PolicyType: StepScaling
    StepScalingPolicyConfiguration:
      AdjustmentType: ChangeInCapacity
      Cooldown: 120
      StepAdjustments:
        - MetricIntervalLowerBound: 0
          ScalingAdjustment: 1
```

## scale-from-zero のレイテンシと対策

### レイテンシの内訳

scale-from-zero 時のレイテンシは以下の要素で構成される:

| フェーズ | 所要時間 | 説明 |
|---------|---------|------|
| Auto Scaling 検出 | 〜60 秒 | CloudWatch Alarm → Scaling Action |
| インスタンス起動 | 1〜3 分 | EC2 インスタンスのプロビジョニング |
| コンテナ起動 | 30 秒〜2 分 | Docker イメージのプル + モデルロード |
| **合計** | **2〜5 分** | 初回リクエストの応答時間 |

### 対策

1. **リトライロジック**: `ModelNotReadyException` に対する exponential backoff
2. **Step Functions タイムアウト**: 十分な `TimeoutSeconds`（300 秒推奨）
3. **フォールバック**: タイムアウト時は Batch Transform にフォールバック
4. **ウォームアップ**: 予測可能なワークロードでは事前にリクエストを送信

### リトライロジック（Lambda 実装）

```python
# scale-from-zero リトライ設定
MODEL_NOT_READY_RETRY_DELAY = 5      # 初期待機秒
MODEL_NOT_READY_MAX_RETRIES = 10     # 最大リトライ回数
MODEL_NOT_READY_MAX_DELAY = 30       # 最大待機秒
STEP_FUNCTIONS_TASK_TIMEOUT = 300    # 合計タイムアウト秒

# Exponential backoff: 5s, 10s, 20s, 30s, 30s, ...
delay = min(
    initial_delay * (2 ** (attempt - 1)),
    max_delay,
)
```

## コスト比較

### 月間コスト試算（ml.m5.large、東京リージョン）

| パターン | 月間コスト | 前提条件 |
|---------|-----------|---------|
| Provisioned (24/7) | 〜$140 | 常時 1 インスタンス |
| Serverless (低頻度) | 〜$5-20 | 1日 100 リクエスト |
| Inference Components (scale-to-zero) | 〜$2-15 | 1日 100 リクエスト、平均起動 2 時間 |
| Batch Transform | 〜$1-5 | 1日 1 ジョブ、10 分実行 |

### コスト最適化のポイント

- **Inference Components**: アイドル時間が長いほどコスト削減効果大
- **Serverless**: 6 MB ペイロード制限内で軽量推論に最適
- **Provisioned**: 常時リクエストがある場合は最もコスト効率が良い
- **Batch Transform**: 大量データの一括処理に最適

## 有効化手順

### Step 1: パラメータ設定

```bash
# samconfig.toml または deploy コマンドで設定
EnableInferenceComponents = "true"
InferenceType = "components"
EnableRealtimeEndpoint = "true"  # Endpoint が必要
InferenceComponentName = "ad-segmentation-component"
ComponentsMinInstanceCount = 0   # scale-to-zero
ComponentsMaxInstanceCount = 4
ComponentsScaleFromZeroTimeout = 300
```

### Step 2: デプロイ

```bash
# Phase 4 のデプロイスクリプトを使用
./scripts/deploy_phase4.sh

# または直接 SAM/CloudFormation デプロイ
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name uc9-autonomous-driving \
  --parameter-overrides \
    EnableInferenceComponents=true \
    InferenceType=components \
    EnableRealtimeEndpoint=true \
    ComponentsMinInstanceCount=0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 3: 動作確認

```bash
# Inference Component の状態確認
aws sagemaker describe-inference-component \
  --inference-component-name ad-segmentation-component \
  --query "InferenceComponentStatus"

# scale-to-zero 確認（DesiredCopyCount=0）
aws application-autoscaling describe-scalable-targets \
  --service-namespace sagemaker \
  --resource-ids "inference-component/ad-segmentation-component"

# テスト呼び出し（scale-from-zero トリガー）
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name uc9-autonomous-driving-realtime-endpoint \
  --inference-component-name ad-segmentation-component \
  --body '{"data": "test"}' \
  --content-type application/json \
  output.json
```

## トラブルシューティング

| 問題 | 原因 | 解決策 |
|------|------|--------|
| ModelNotReadyException が続く | scale-from-zero に時間がかかっている | タイムアウトを延長（300→600 秒） |
| ValidationError | Component が存在しない or Endpoint が InService でない | Endpoint の状態を確認 |
| Scale-in が遅い | Cooldown 期間中 | Cooldown を短縮（120→60 秒） |
| コストが下がらない | MinInstanceCount > 0 | MinInstanceCount=0 を確認 |

## 関連ドキュメント

- [AWS SageMaker Inference Components ドキュメント](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-components.html)
- [scale-to-zero ドキュメント](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-zero-instances.html)
- [Serverless Inference コールドスタートガイド](./serverless-inference-cold-start.md)
- [推論コスト比較](./inference-cost-comparison.md)
