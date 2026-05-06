# SageMaker 推論パターン コスト比較ガイド

🌐 **Language / 言語**: 日本語（本ドキュメント）

## 概要

本ドキュメントでは、FSxN S3AP Serverless Patterns Phase 4 で提供する 3 つの SageMaker 推論パターンのコスト比較と選択指針を提供します。

対象リージョン: **ap-northeast-1（東京）**

## 推論パターン比較

### 3 パターンの特徴

| 項目 | Batch Transform | Real-time Endpoint (Provisioned) | Serverless Inference |
|------|----------------|----------------------------------|---------------------|
| 課金モデル | ジョブ実行時間のみ | インスタンス常時稼働 | リクエスト処理時間のみ |
| レイテンシ | 分〜時間（ジョブ起動含む） | ミリ秒〜秒 | 秒〜十秒（コールドスタート含む） |
| スケーリング | ジョブ単位で自動 | Auto Scaling（分単位） | 自動（0 → N） |
| 最小コスト | $0（未使用時） | インスタンス 1 台分/時 | $0（未使用時） |
| コールドスタート | なし（ジョブ起動が遅い） | なし | あり（数秒〜数十秒） |
| 最大ペイロード | 100 MB（S3 経由） | 6 MB | 4 MB |
| 適用シナリオ | 大量バッチ処理 | 低レイテンシ常時稼働 | スポラディックな推論 |

### アーキテクチャ上の位置づけ

```
Step Functions Workflow
  │
  ├─ file_count >= threshold (default: 10)
  │   └─→ Batch Transform Path（大量バッチ、コスト効率重視）
  │
  └─ file_count < threshold
      └─→ Real-time / Serverless Path（低レイテンシ重視）
           ├─ InferenceType: "provisioned" → Real-time Endpoint
           └─ InferenceType: "serverless" → Serverless Inference
```

## 定量コスト見積もり（ap-northeast-1）

### 前提条件

- モデル: 点群セグメンテーション（推論時間: 約 2 秒/リクエスト）
- インスタンスタイプ: ml.m5.xlarge（Compute-optimized 基準）
- 料金: ml.m5.xlarge = $0.298/時間（ap-northeast-1）
- Serverless: メモリ 4096 MB、推論時間 2 秒/リクエスト

### 低ボリューム: 100 リクエスト/日

| パターン | 月額コスト概算 | 内訳 |
|---------|--------------|------|
| **Batch Transform** | **~$5** | 100 req × 2 sec × 30 日 ÷ 3600 × $0.298 = ~$5 |
| **Real-time Endpoint** | **~$215** | $0.298 × 24h × 30 日 = ~$215（常時稼働） |
| **Serverless Inference** | **~$4** | 100 req × 2 sec × 30 日 × $0.00002/sec (4096MB) = ~$4 |

**推奨**: ✅ **Serverless Inference**（最低コスト、コールドスタート許容可能）

### 中ボリューム: 1,000 リクエスト/日

| パターン | 月額コスト概算 | 内訳 |
|---------|--------------|------|
| **Batch Transform** | **~$50** | 1000 req × 2 sec × 30 日 ÷ 3600 × $0.298 = ~$50 |
| **Real-time Endpoint** | **~$215** | $0.298 × 24h × 30 日 = ~$215（1 インスタンス） |
| **Serverless Inference** | **~$36** | 1000 req × 2 sec × 30 日 × $0.00002/sec = ~$36 |

**推奨**: ✅ **Serverless Inference**（コスト効率良好）または **Batch Transform**（レイテンシ不要時）

### 高ボリューム: 10,000 リクエスト/日

| パターン | 月額コスト概算 | 内訳 |
|---------|--------------|------|
| **Batch Transform** | **~$500** | 10000 req × 2 sec × 30 日 ÷ 3600 × $0.298 = ~$500 |
| **Real-time Endpoint** | **~$215** | $0.298 × 24h × 30 日 = ~$215（1 インスタンス、Auto Scaling で 2-3 台想定: ~$430-$645） |
| **Serverless Inference** | **~$360** | 10000 req × 2 sec × 30 日 × $0.00002/sec = ~$360 |

**推奨**: ✅ **Real-time Endpoint**（高スループット、安定レイテンシ）

## 決定マトリクス

### 選択基準

| 基準 | Batch Transform | Real-time Endpoint | Serverless Inference |
|------|:-:|:-:|:-:|
| レイテンシ要件 < 1 秒 | ❌ | ✅ | ⚠️（ウォーム時のみ） |
| レイテンシ要件 < 10 秒 | ❌ | ✅ | ✅ |
| レイテンシ要件 > 1 分許容 | ✅ | ✅ | ✅ |
| リクエスト量 < 100/日 | ✅ | ❌（過剰コスト） | ✅ |
| リクエスト量 100–1000/日 | ✅ | ⚠️ | ✅ |
| リクエスト量 > 5000/日 | ⚠️ | ✅ | ⚠️（スロットリング） |
| コールドスタート許容 | — | — | 必須 |
| コスト感度: 高 | ✅ | ❌ | ✅ |
| コスト感度: 低 | ✅ | ✅ | ✅ |
| 大ペイロード (> 6 MB) | ✅ | ❌ | ❌ |
| A/B テスト対応 | ❌ | ✅（Multi-Variant） | ❌ |
| GPU 必須 | ✅ | ✅ | ❌ |

### 推奨フローチャート

```
[開始] リクエストパターンは？
  │
  ├─ バッチ処理（定期的に大量データ）
  │   └─→ レイテンシ要件は？
  │         ├─ 分〜時間許容 → ✅ Batch Transform
  │         └─ 秒単位必要 → Real-time Endpoint
  │
  ├─ リアルタイム（常時リクエスト）
  │   └─→ リクエスト量は？
  │         ├─ > 5000/日 → ✅ Real-time Endpoint (Auto Scaling)
  │         ├─ 100–5000/日 → コスト感度は？
  │         │     ├─ 高 → ✅ Serverless Inference
  │         │     └─ 低 → ✅ Real-time Endpoint
  │         └─ < 100/日 → ✅ Serverless Inference
  │
  └─ スポラディック（不定期、予測不能）
      └─→ コールドスタート許容？
            ├─ はい → ✅ Serverless Inference
            └─ いいえ → ✅ Real-time Endpoint (min instances: 1)
```

## インスタンスタイプ推奨

### Compute-Optimized（CPU ベース）

| インスタンスタイプ | vCPU | メモリ | 料金/時間 (ap-northeast-1) | 推奨ワークロード |
|------------------|------|--------|--------------------------|----------------|
| ml.m5.large | 2 | 8 GB | $0.149 | 軽量モデル、テスト用 |
| ml.m5.xlarge | 4 | 16 GB | $0.298 | 標準的な推論ワークロード |
| ml.m5.2xlarge | 8 | 32 GB | $0.596 | 中規模モデル |
| ml.c5.xlarge | 4 | 8 GB | $0.238 | CPU 集約型推論 |
| ml.c5.2xlarge | 8 | 16 GB | $0.476 | 高スループット CPU 推論 |

### GPU（ディープラーニングモデル）

| インスタンスタイプ | GPU | GPU メモリ | 料金/時間 (ap-northeast-1) | 推奨ワークロード |
|------------------|-----|-----------|--------------------------|----------------|
| ml.g4dn.xlarge | 1× T4 | 16 GB | $0.894 | 推論最適化、コスト効率 |
| ml.g4dn.2xlarge | 1× T4 | 32 GB | $1.267 | 中規模 DL モデル |
| ml.g5.xlarge | 1× A10G | 24 GB | $1.578 | 高性能推論 |
| ml.p3.2xlarge | 1× V100 | 16 GB | $4.838 | 大規模モデル、学習兼用 |

### 選択指針

| ワークロード特性 | 推奨カテゴリ | 推奨インスタンス |
|----------------|------------|----------------|
| 点群セグメンテーション（本 UC9） | Compute-Optimized | ml.m5.xlarge |
| 画像分類・物体検出 | GPU | ml.g4dn.xlarge |
| 自然言語処理（BERT 等） | GPU | ml.g4dn.xlarge |
| 大規模言語モデル | GPU | ml.g5.xlarge 以上 |
| 表形式データ推論 | Compute-Optimized | ml.c5.xlarge |
| リアルタイム + コスト重視 | Compute-Optimized | ml.m5.large |

## Phase 4 での実装

### CloudFormation パラメータ

```yaml
Parameters:
  EnableRealtimeEndpoint:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: "Real-time Endpoint を有効化"

  InferenceType:
    Type: String
    Default: "provisioned"
    AllowedValues: ["provisioned", "serverless"]
    Description: "推論タイプ（provisioned / serverless）"

  RealtimeInstanceType:
    Type: String
    Default: "ml.m5.xlarge"
    Description: "Real-time Endpoint のインスタンスタイプ"

  FileCountThreshold:
    Type: Number
    Default: 10
    Description: "Real-time / Batch Transform ルーティング閾値"
```

### コスト最適化のベストプラクティス

1. **デフォルト無効**: `EnableRealtimeEndpoint=false` でデプロイし、必要時のみ有効化
2. **Auto Scaling 設定**: `MinInstanceCount=1`, `MaxInstanceCount` をピーク時に合わせて設定
3. **Serverless 検討**: 低〜中ボリュームでは Serverless Inference が最もコスト効率が高い
4. **Batch Transform 活用**: レイテンシ不要な大量処理は Batch Transform で実行
5. **閾値チューニング**: `FileCountThreshold` をワークロードに合わせて調整

## 関連ドキュメント

- [Phase 4 設計書](.kiro/specs/fsxn-s3ap-serverless-patterns-phase4/design.md)
- [ストリーミング vs ポーリング選択ガイド](streaming-vs-polling-guide.md)
- [コスト構造分析](cost-analysis.md)
- [AWS SageMaker 料金](https://aws.amazon.com/sagemaker/pricing/)
