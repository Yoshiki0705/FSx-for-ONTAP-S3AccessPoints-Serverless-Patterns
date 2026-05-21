# S3 Access Points for FSx for ONTAP — Performance Considerations

🌐 **Language / 言語**: [日本語](s3ap-performance-considerations.md) | [English](s3ap-performance-considerations.en.md)

## 概要

S3 Access Points for FSx for ONTAP 経由のデータアクセスは、FSx ファイルシステムのプロビジョンドスループットに依存します。本ドキュメントでは、パフォーマンス設計時に考慮すべき要素を整理します。

> **AWS ドキュメント引用**: "Amazon S3 access points for FSx for ONTAP file systems deliver latency in the tens of milliseconds range, consistent with S3 bucket access. The throughput and requests per second you can drive to an Amazon FSx file system via the S3 API depends on the file system's provisioned throughput."
> — [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

## スループットの依存関係

### FSx Provisioned Throughput → S3 AP Throughput

```
┌─────────────────────────────────────────────────────────────┐
│  S3 API Client (Lambda / Step Functions / EC2)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ S3 API (GetObject / PutObject / ListObjectsV2)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  S3 Access Point                                            │
│  • Latency: tens of milliseconds                           │
│  • Throughput: FSx provisioned throughput に依存             │
└─────────────────────────┬───────────────────────────────────┘
                          │ FSx Data Plane
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP File System                                  │
│  • SSD latency: sub-millisecond                            │
│  • Network I/O: throughput capacity で決定                   │
│  • Disk I/O: throughput capacity + SSD IOPS で決定          │
└─────────────────────────────────────────────────────────────┘
```

### FSx Throughput Capacity の上限（参考値）

| ファイルシステムタイプ | 最大読み取りスループット (per HA pair) | 最大書き込みスループット |
|---------------------|--------------------------------------|----------------------|
| 第1世代 Single-AZ (主要リージョン) | 4,096 MBps | 1,000 MBps |
| 第1世代 Multi-AZ (主要リージョン) | 4,096 MBps | 1,800 MBps |
| 第2世代 Single-AZ | 6,144 MBps (per HA pair, 最大12 pairs) | 1,024 MBps |
| 第2世代 Multi-AZ | 6,144 MBps | 2,048 MBps |

> **注意**: S3 AP 経由のスループットはこれらの上限を超えることはできません。S3 AP、NFS、SMB のすべてのアクセスが同じスループット容量を共有します。

## Object Size Profile

### S3 AP の制約

| 操作 | 最大サイズ | 備考 |
|------|-----------|------|
| PutObject (単一) | 5 GB | これを超えるファイルはアップロード不可 |
| GetObject | 制限なし | 5 GB 超のファイルもダウンロード可能 |
| Multipart Upload | 5 GB (完了後のオブジェクト) | パーツ単位でアップロード |
| Storage Class | FSX_ONTAP のみ | 他のストレージクラスは指定不可 |
| 暗号化 | SSE-FSX のみ | SSE-KMS / SSE-S3 は使用不可 |

### オブジェクトサイズ別の推奨戦略

| サイズ範囲 | 推奨アプローチ | Lambda メモリ目安 |
|-----------|--------------|-----------------|
| < 1 MB | 直接 GetObject、メモリ内処理 | 256-512 MB |
| 1-100 MB | GetObject + ストリーミング処理 | 512 MB - 1 GB |
| 100 MB - 1 GB | Range GET (部分読み取り) または /tmp 書き出し | 1-3 GB |
| 1-5 GB | /tmp (10 GB) + ストリーミング、または EFS マウント | 3-10 GB |
| > 5 GB | GetObject のみ（PutObject 不可）、分割処理を検討 | ECS/Batch 推奨 |

## ListObjectsV2 Pagination

### 動作仕様

- **MaxKeys**: デフォルト 1000、最大 1000
- **Pagination**: `IsTruncated=true` の場合、`NextContinuationToken` で次ページ取得
- **Prefix フィルタ**: サーバーサイドフィルタリング（効率的）
- **Delimiter**: ディレクトリ階層のシミュレーション（`CommonPrefixes` で返却）

### パフォーマンス考慮事項

```python
# 推奨: Prefix を活用して対象を絞り込む
response = s3.list_objects_v2(
    Bucket=s3ap_alias,
    Prefix="data/2026/05/",  # 日付ベースの絞り込み
    MaxKeys=1000
)

# 大量ファイル時: ページネーションのレイテンシを考慮
# 各ページ取得に tens of milliseconds かかる
# 10,000 ファイル = 10 ページ × ~50ms = ~500ms (最低)
```

### 大量ファイル環境での最適化

| ファイル数 | 推奨アプローチ | 想定所要時間 |
|-----------|--------------|------------|
| < 1,000 | 単一 ListObjectsV2 | < 100 ms |
| 1,000 - 10,000 | Prefix 分割 + 並列 List | 1-5 秒 |
| 10,000 - 100,000 | 日付/カテゴリ Prefix + DynamoDB キャッシュ | 5-30 秒 |
| > 100,000 | インクリメンタルスキャン（前回からの差分のみ） | ワークロード依存 |

## Large Object Read Strategy

### Range GET の活用

S3 AP for FSx for ONTAP は GetObject をサポートしており、HTTP Range ヘッダーによる部分読み取りが可能です:

```python
# Range GET で先頭 1MB のみ取得
response = s3.get_object(
    Bucket=s3ap_alias,
    Key="large-file.bin",
    Range="bytes=0-1048575"  # 先頭 1 MB
)
```

**活用シナリオ**:
- ファイルヘッダーのみ読み取り（DICOM, GDS, SEG-Y 等のバイナリフォーマット）
- 大きなログファイルの末尾読み取り
- 並列ダウンロード（複数 Range を並列取得）

### ストリーミング読み取り

```python
# メモリ効率の良いストリーミング処理
response = s3.get_object(Bucket=s3ap_alias, Key="large-file.csv")
for chunk in response["Body"].iter_chunks(chunk_size=8192):
    process_chunk(chunk)
response["Body"].close()
```

## Lambda Memory Size vs Throughput

### Lambda のネットワーク帯域幅

Lambda のネットワーク帯域幅はメモリサイズに比例して割り当てられます:

| Lambda メモリ | 概算ネットワーク帯域幅 | 10 MB ファイル取得時間 |
|-------------|---------------------|---------------------|
| 128 MB | ~50 Mbps | ~1.6 秒 |
| 512 MB | ~200 Mbps | ~0.4 秒 |
| 1,024 MB | ~400 Mbps | ~0.2 秒 |
| 1,769 MB (1 vCPU) | ~600 Mbps | ~0.13 秒 |
| 3,008 MB | ~1 Gbps | ~0.08 秒 |
| 10,240 MB (6 vCPU) | ~数 Gbps | < 0.05 秒 |

> **注意**: 上記は概算値。実際のスループットは S3 AP のレイテンシ（tens of ms）と FSx のプロビジョンドスループットにも制約されます。

### 推奨メモリサイズ（ユースケース別）

| ユースケース | 推奨メモリ | 理由 |
|------------|-----------|------|
| メタデータ抽出（小ファイル） | 512 MB | CPU/メモリ最小限で十分 |
| OCR / 画像処理 | 1-3 GB | 画像デコードにメモリが必要 |
| AI/ML 推論（Bedrock 呼び出し） | 512 MB - 1 GB | ネットワーク I/O 主体 |
| 大ファイル処理 | 3-10 GB | /tmp 書き出し + 処理 |
| バッチ集計 | 1-3 GB | 複数ファイルのメモリ内集計 |

## Step Functions Map Concurrency vs FSx Throughput

### 並列度の設計

Step Functions Map State で複数ファイルを並列処理する場合、FSx のスループット容量が上限となります:

```
Map State (MaxConcurrency=N)
  ├─→ Lambda 1: GetObject (file_1) → Process → PutObject
  ├─→ Lambda 2: GetObject (file_2) → Process → PutObject
  ├─→ Lambda 3: GetObject (file_3) → Process → PutObject
  └─→ ...
      ↓ (すべて同じ FSx ファイルシステムのスループットを共有)
```

### 並列度の計算

```
max_concurrency = fsxn_provisioned_throughput / per_lambda_throughput

例: FSx 512 MBps provisioned, 各 Lambda が 50 MBps 消費
  → max_concurrency ≈ 10 (S3 AP 経由のみの場合)

注意: NFS/SMB の既存ワークロードもスループットを消費するため、
      実際の利用可能帯域はさらに少ない
```

### 推奨 MaxConcurrency 設定

| FSx Throughput Capacity | 推奨 MaxConcurrency | 備考 |
|------------------------|--------------------|----|
| 128 MBps | 2-5 | 小規模 PoC |
| 256 MBps | 5-10 | 開発/テスト |
| 512 MBps | 10-20 | 小規模本番 |
| 1,024 MBps | 20-50 | 中規模本番 |
| 2,048+ MBps | 50-100 | 大規模本番 |

> **重要**: 上記は S3 AP 経由のアクセスのみを考慮した値。NFS/SMB の既存ワークロードがある場合は、その分を差し引いて設計してください。

## Retry / Backoff Policy

### S3 AP 固有のエラーと対処

| エラー | 原因 | 推奨対処 |
|--------|------|---------|
| `SlowDown` (503) | FSx スループット超過 | Exponential backoff (base: 1s, max: 30s) |
| `ServiceUnavailable` (503) | FSx データプレーン一時障害 | Retry with jitter (max 3 attempts) |
| `RequestTimeout` (408) | 大ファイル読み取りタイムアウト | Lambda timeout 延長 + retry |
| `AccessDenied` (403) | IAM or file system permission | Retry 不要（設定修正が必要） |

### 推奨 Retry 設定

```python
import botocore.config

s3_config = botocore.config.Config(
    retries={
        "max_attempts": 5,
        "mode": "adaptive"  # adaptive mode: 自動的に backoff を調整
    },
    connect_timeout=10,
    read_timeout=60,  # 大ファイル対応
)

s3 = boto3.client("s3", config=s3_config)
```

### Step Functions での Retry 設定

```json
{
  "Retry": [
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2.0,
      "JitterStrategy": "FULL"
    }
  ]
}
```

## パフォーマンスモニタリング

### 推奨 CloudWatch メトリクス

| メトリクス | 意味 | アラーム閾値（参考） |
|-----------|------|-------------------|
| FSx `DataReadBytes` | 読み取りスループット | > 80% of provisioned |
| FSx `DataWriteBytes` | 書き込みスループット | > 80% of provisioned |
| Lambda `Duration` | 処理時間 | > timeout × 0.8 |
| Step Functions `ExecutionTime` | ワークフロー全体時間 | SLO 依存 |
| SQS `ApproximateAgeOfOldestMessage` | バックログ蓄積 | > 300 秒 |

### ボトルネック特定フロー

```
Lambda Duration が長い
├── GetObject が遅い
│   ├── FSx DataReadBytes が上限に近い → Throughput Capacity 増加
│   ├── Lambda メモリが小さい → メモリ増加（帯域幅向上）
│   └── オブジェクトが大きい → Range GET / ストリーミング
├── Processing が遅い
│   ├── CPU bound → Lambda メモリ増加（vCPU 増加）
│   └── 外部 API 呼び出し → 並列化 / バッチ化
└── PutObject が遅い
    ├── FSx DataWriteBytes が上限に近い → Throughput Capacity 増加
    └── オブジェクトが大きい → Multipart Upload
```

## 参考リンク

- [Amazon FSx for NetApp ONTAP performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Access point compatibility (Supported S3 operations)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [S3AP 二段階認可モデル](s3ap-authorization-model.md)
- [Deployment Profiles](deployment-profiles.md)
