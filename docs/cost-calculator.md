# コスト試算ツール — FSx for ONTAP S3AP Serverless Patterns

## 入力パラメータ

顧客のワークロード特性を入力し、月額コストを概算します。

| パラメータ | 記号 | 単位 | 例 |
|-----------|------|------|-----|
| 1 日あたりの処理ファイル数 | F | files/day | 100 |
| 平均ファイルサイズ | S | MB | 1 |
| 実行頻度 | R | times/day | 24 (hourly) |
| Lambda 関数数（パターンによる） | N | functions | 4 |
| Bedrock 入力トークン数/ファイル | T_in | tokens | 2,000 |
| Bedrock 出力トークン数/ファイル | T_out | tokens | 500 |
| Athena スキャン量/クエリ | A | MB | 10 |

## 計算式

### Lambda コスト

```
Lambda 月額 = F × R × 30 × N × (メモリ GB × 実行秒数 × $0.0000166667 + $0.0000002)
```

例: 100 files × 24 × 30 × 4 functions × (0.256 GB × 2 sec × $0.0000166667 + $0.0000002)
= 288,000 invocations × ($0.0000085 + $0.0000002) = **$2.51/月**

### S3 API コスト

```
S3 API 月額 = (ListObjectsV2 回数 × $0.0047/10K) + (GetObject 回数 × $0.0004/1K)
```

例: (720 list + 72,000 get) × 30 = 21,600 list + 2,160,000 get
= $0.01 + $0.86 = **$0.87/月**

### Bedrock コスト (Nova Lite)

```
Bedrock 月額 = F × 30 × ((T_in / 1000 × $0.00006) + (T_out / 1000 × $0.00024))
```

例: 100 × 30 × ((2000/1000 × $0.00006) + (500/1000 × $0.00024))
= 3,000 × ($0.00012 + $0.00012) = **$0.72/月**

### Step Functions コスト

```
Step Functions 月額 = F × R × 30 × (N + 2) × $0.000025
```

例: 100 × 24 × 30 × 6 transitions = 432,000 transitions × $0.000025 = **$10.80/月**

### Athena コスト

```
Athena 月額 = R × 30 × A / 1024 / 1024 × $5
```

例: 24 × 30 × 10 MB / 1,048,576 TB × $5 = **$0.003/月** (最小課金 10 MB/クエリ)

### SNS コスト

```
SNS 月額 = R × 30 × $0.50 / 100,000
```

例: 24 × 30 = 720 notifications × $0.50/100K = **$0.004/月**

## 合計概算テーブル

| ワークロード規模 | ファイル数/日 | 頻度 | Lambda | S3 API | Bedrock | Step Functions | 合計 |
|----------------|-------------|------|--------|--------|---------|---------------|------|
| 小規模 PoC | 10 | 1x/day | $0.01 | $0.01 | $0.02 | $0.005 | **~$0.05/月** |
| 標準 | 100 | hourly | $2.51 | $0.87 | $0.72 | $10.80 | **~$15/月** |
| 大規模 | 1,000 | hourly | $25.10 | $8.70 | $7.20 | $108.00 | **~$150/月** |
| エンタープライズ | 10,000 | 15min | $100+ | $35+ | $72+ | $430+ | **~$640/月** |

## 固定コスト（既存 FSx for ONTAP 環境前提）

| コンポーネント | 月額概算 | 備考 |
|--------------|---------|------|
| FSx for ONTAP (128 MBps, 1 TB SSD) | ~$230 | 既存環境を共有する前提 |
| S3 Access Point | $0 | 追加料金なし |
| CloudWatch Logs (1 GB/月) | $0.76 | |
| Secrets Manager (1 シークレット) | $0.40 | |

## オプショナルコスト

| コンポーネント | 月額概算 | 有効化条件 |
|--------------|---------|-----------|
| Interface VPC Endpoints (4 個) | $28.80 | EnableVpcEndpoints=true |
| CloudWatch Alarms (3 個) | $0.30 | EnableCloudWatchAlarms=true |
| Kinesis Data Stream (1 shard) | $10.80 | TriggerMode=STREAMING |
| OpenSearch Serverless (2 OCU) | $345.60 | UC16 OpenSearch モード |
| SageMaker Endpoint (ml.m5.large) | $33.12 | UC9 リアルタイム推論 |

## AWS Pricing Calculator リンク

詳細な見積もりは [AWS Pricing Calculator](https://calculator.aws/) で作成してください。

## 注意事項

> **Governance Caveat**: 本コスト試算は概算であり、保証値ではありません。実際の請求額は使用パターン、データ量、リージョン、AWS 料金改定により異なります。最新の料金は AWS 公式ドキュメントを参照してください。

> 上記計算は ap-northeast-1 (東京) リージョンの 2026 年 5 月時点の料金に基づいています。料金は変更される可能性があります。
