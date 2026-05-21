# S3AP Throughput Benchmark Results（実測値）

🌐 **Language / 言語**: [日本語](s3ap-benchmark-results.md) | [English](s3ap-benchmark-results.en.md)

## 概要

FSx for ONTAP S3 Access Points 経由の各 S3 API 操作のレイテンシとスループットを実測した結果です。

## 計測環境

| 項目 | 値 |
|------|-----|
| リージョン | ap-northeast-1 (東京) |
| FSx for ONTAP | Single-AZ (First-generation) |
| Throughput Capacity | 128 MBps |
| Storage Type | SSD |
| Tiering Policy | AUTO (cooling period 31 days) |
| S3 Access Point | NetworkOrigin=Internet |
| クライアント | macOS (boto3 1.34.x, Python 3.9) — インターネット経由 |
| Lambda Architecture | N/A（ローカル実行） |
| VPC Endpoint | N/A（Internet Origin AP のためインターネット経由） |
| 同時実行数 | 1（逐次実行） |
| 各操作 | 5-10 回の反復 |
| 統計値 | 平均、P50（中央値）、最小、最大を記載 |
| 計測日 | 2026-05-22 |

> **重要**: 本ベンチマーク結果はテスト環境での実測値であり、サービスレベル保証ではありません。スループットとレイテンシは FSx for ONTAP のサイジング、ワークロードプロファイル、ネットワーク経路、オブジェクトサイズ、同時実行数に依存します。本番環境での採用前に、お客様自身の AWS アカウント・リージョン・FSx 構成・ワークロードプロファイルで検証してください。

> **注意**: 本計測はインターネット経由（クライアント → S3AP）です。VPC 内 Lambda からのアクセスではネットワークレイテンシが大幅に低下し、スループットが向上します。

---

## PutObject

| ファイルサイズ | 平均レイテンシ | P50 | 最小 | 最大 |
|-------------|-------------|-----|------|------|
| 1 KB | 50.9 ms | 35.8 ms | 32.3 ms | 116.3 ms |
| 10 KB | 38.1 ms | 37.2 ms | 36.2 ms | 40.5 ms |
| 100 KB | 70.8 ms | 67.5 ms | 57.5 ms | 90.3 ms |
| 1 MB | 181.8 ms | 164.5 ms | 145.8 ms | 281.8 ms |
| 5 MB | 314.1 ms | 286.0 ms | 227.3 ms | 468.6 ms |

**観察**:
- 小ファイル (≤10KB): ~35-50ms（接続オーバーヘッドが支配的）
- 中ファイル (100KB-1MB): サイズに比例してレイテンシ増加
- 大ファイル (5MB): ~300ms（S3AP の最大アップロードサイズ上限）

---

## GetObject

| ファイルサイズ | 平均レイテンシ | P50 | 最小 | 最大 | 平均スループット |
|-------------|-------------|-----|------|------|--------------|
| 1 KB | 47.5 ms | 30.5 ms | 28.5 ms | 117.1 ms | 0.03 MB/s |
| 10 KB | 32.3 ms | 32.1 ms | 30.3 ms | 34.4 ms | 0.3 MB/s |
| 100 KB | 38.3 ms | 34.1 ms | 29.7 ms | 59.2 ms | 2.7 MB/s |
| 1 MB | 59.3 ms | 48.5 ms | 43.6 ms | 83.7 ms | 18.1 MB/s |
| 5 MB | 123.4 ms | 111.0 ms | 106.3 ms | 172.3 ms | 41.8 MB/s |

**観察**:
- AWS ドキュメントの「tens of milliseconds」と整合（P50: 30-111ms）
- 5MB ファイルで ~42 MB/s のスループット（インターネット経由）
- VPC 内 Lambda ではさらに高スループットが期待される

### GetObject パーセンタイル詳細（20 回反復、concurrency=1）

| ファイルサイズ | P50 | P90 | P95 | P99 | 最小 | 最大 |
|-------------|-----|-----|-----|-----|------|------|
| 1 KB | 35.5 ms | 39.0 ms | 40.2 ms | 40.2 ms | 32.0 ms | 40.2 ms |
| 100 KB | 37.6 ms | 50.1 ms | 100.2 ms | 100.2 ms | 30.1 ms | 100.2 ms |
| 1 MB | 47.8 ms | 63.3 ms | 92.3 ms | 92.3 ms | 38.1 ms | 92.3 ms |
| 5 MB | 108.0 ms | 115.8 ms | 134.8 ms | 134.8 ms | 100.1 ms | 134.8 ms |

**観察**:
- P90 は P50 の 1.1-1.3 倍程度（tail latency は比較的安定）
- P95/P99 で occasional spike（100ms 超）が発生 — 接続再利用やネットワーク揺らぎが原因
- 本番設計では P90 を基準にタイムアウトを設定し、P99 に対して retry を設計するのが推奨

---

## 並列アクセス性能（Concurrent GetObject）

1 MB ファイルに対する並列アクセス:

| 同時実行数 | 総リクエスト | 平均 | P50 | P90 | P99 | 最大 | 合計スループット |
|-----------|------------|------|-----|-----|-----|------|--------------|
| 1 | 5 | 63.8 ms | 41.4 ms | 140.4 ms | — | 140.4 ms | 35.6 MB/s |
| 5 | 25 | 112.9 ms | 97.5 ms | 187.1 ms | 198.9 ms | 229.5 ms | 108.9 MB/s |
| 10 | 50 | 151.7 ms | 137.4 ms | 232.7 ms | 287.3 ms | 363.3 ms | 137.6 MB/s |

**観察**:
- 並列度を上げると個々のレイテンシは増加するが、合計スループットは向上
- concurrency=5 で ~109 MB/s、concurrency=10 で ~138 MB/s（FSx 128 MBps の上限に近づく）
- **FSx Throughput Capacity が並列性能のボトルネック** — 128 MBps 構成では concurrency=10 で飽和
- 高並列処理が必要な場合は FSx Throughput Capacity の増加が必要

> **表記注**: 本ドキュメントでは MB/s（メガバイト毎秒）を使用しています。AWS コンソールの FSx Throughput Capacity 表記 (MBps) と同義です。測定値 138 MB/s が 128 MBps 構成を若干超えて見えるのは、FSx の短時間バースト機能、測定の丸め誤差、および throughput 計算方法（elapsed time ベース）の差異によるものです。持続的なスループットは provisioned capacity を超えません。

---

## Range GET（部分読み取り）

5 MB ファイルからの部分読み取り:

| Range | 読み取りサイズ | 平均レイテンシ | P50 | 最小 | 最大 |
|-------|-------------|-------------|-----|------|------|
| bytes=0-1023 | 1 KB | 52.0 ms | 34.5 ms | 31.7 ms | 125.4 ms |
| bytes=0-102399 | 100 KB | 39.1 ms | 37.2 ms | 31.7 ms | 52.0 ms |
| bytes=0-1048575 | 1 MB | 54.5 ms | 55.5 ms | 45.3 ms | 64.2 ms |

**観察**:
- ✅ **Range GET はサポートされている**（FSxN S3AP で動作確認済み）
- 部分読み取りのレイテンシは全体読み取りと同等（接続オーバーヘッドが支配的）
- 大ファイルのヘッダーのみ読み取り（DICOM, GDS, SEG-Y 等）に有効

### Range GET の活用ユースケース

| ユースケース | 対象 UC | Range 指定例 | 効果 |
|------------|---------|------------|------|
| DICOM ヘッダー読み取り | UC5 | `bytes=0-4095` (4KB) | 画像本体を読まずにメタデータ取得 |
| GDS/OASIS ファイルヘッダー | UC6 | `bytes=0-1023` (1KB) | 設計ファイルのバージョン・レイヤー情報取得 |
| SEG-Y トレースヘッダー | UC8 | `bytes=0-3599` (3.6KB) | 地震探査データのサーベイ情報取得 |
| ログファイル末尾確認 | UC3 | `bytes=-10240` (末尾10KB) | 最新ログエントリの確認 |
| PDF 先頭ページ抽出 | UC16 | `bytes=0-102399` (100KB) | 文書の先頭部分のみ OCR |
| 大容量メディアのプレビュー | UC4 | `bytes=0-1048575` (1MB) | VFX アセットのサムネイル生成用 |

---

## HeadObject

| 平均レイテンシ | P50 | 最小 | 最大 |
|-------------|-----|------|------|
| 18.9 ms | 18.0 ms | 17.8 ms | 20.8 ms |

**観察**:
- 最も軽量な操作（~19ms）
- ファイル存在確認やメタデータ取得に最適

---

## ListObjectsV2

| MaxKeys | オブジェクト数 | 平均レイテンシ | P50 | 最小 | 最大 |
|---------|-------------|-------------|-----|------|------|
| 1000 | 6 | 26.0 ms | 25.8 ms | 22.1 ms | 30.1 ms |

**観察**:
- 少数オブジェクトでは ~26ms
- ページネーション（1000 オブジェクト/ページ）では各ページに ~26ms
- 10,000 ファイル = 10 ページ × ~26ms = ~260ms（最低）

---

## DeleteObject

| 操作 | 結果 |
|------|------|
| DeleteObject (各サイズ) | ✅ 成功（レイテンシ未計測） |

---

## サーバーレスパイプラインへの設計指針

### Lambda メモリ別の推奨

| ファイルサイズ | 推奨 Lambda メモリ | 理由 |
|-------------|-----------------|------|
| < 100 KB | 256-512 MB | 接続オーバーヘッドが支配的、メモリ増加の効果小 |
| 100 KB - 1 MB | 512 MB - 1 GB | スループット向上の恩恵あり |
| 1 MB - 5 MB | 1-3 GB | ネットワーク帯域幅がボトルネック |
| > 5 MB (GetObject only) | 3-10 GB or ECS | /tmp 書き出し + ストリーミング |

### Step Functions Map 並列度の推奨

| FSx Throughput | 推奨 MaxConcurrency | 根拠 |
|---------------|--------------------|----|
| 128 MBps | 3-5 | 128 ÷ 42 ≈ 3 (5MB ファイル基準) |
| 256 MBps | 6-10 | |
| 512 MBps | 12-20 | |
| 1,024 MBps | 24-40 | |
| 2,048+ MBps | 40+ | upper_bound で制限推奨 |

> 上記は S3AP 経由のアクセスのみ。NFS/SMB の既存ワークロードがある場合は差し引いて設計。

### コスト比較（1,000 ファイル/日、平均 1MB）

| 方式 | 月額概算 | 備考 |
|------|---------|------|
| FSxN S3AP (POLLING, rate(1h)) | ~$8-15 | Lambda 実行 + Scheduler |
| S3 コピー方式 (DataSync + S3) | ~$20-40 | DataSync + S3 ストレージ + Lambda |
| NFS マウント Lambda (VPC 内) | ~$15-25 | VPC Endpoint コスト含む |

---

## 制約と注意事項

1. **インターネット経由の計測**: VPC 内 Lambda からはレイテンシが 30-50% 低下する可能性
2. **FSx Throughput 依存**: 本計測の FSx は低スループット構成。高スループット構成ではさらに高速
3. **同時アクセス**: 単一クライアントからの逐次アクセス。並列アクセスでは FSx スループット上限に注意
4. **初回アクセス**: 最初のリクエストは接続確立のため若干遅い（cold start 的な挙動）
5. **S3AP 固有**: 通常の S3 バケットとは異なるレイテンシ特性（FSx データプレーン経由）

> **免責事項**: 本ドキュメントに記載されたベンチマーク結果およびコスト数値はテスト環境での実測値であり、サービスレベル保証ではありません。本番環境での採用前に、お客様自身の AWS アカウント・リージョン・FSx for ONTAP 構成・ワークロードプロファイルで検証してください。

---

## 次回ベンチマーク計画

### 測定目的別の整理

| 測定目的 | 変動パラメータ | 固定パラメータ | 期待される知見 |
|---------|-------------|-------------|-------------|
| Latency characterization | Object size (1KB-5MB) | concurrency=1, FSx=128MBps | サイズ別レイテンシ特性 |
| Throughput saturation | Concurrency (1-50) | Object size=1MB, FSx=128MBps | 飽和点の特定 |
| FSx capacity comparison | FSx throughput (128/256/512 MBps) | Object size=1MB, concurrency=10 | capacity 別スケール特性 |
| Object size impact | Object size (1KB-50MB) | concurrency=5, FSx=256MBps | サイズ別スループット |
| Range GET behavior | Range size (1KB-5MB from 50MB file) | concurrency=1, FSx=128MBps | 部分読み取りの効果 |

### 固定条件（次回計測時）

```
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU)
Lambda architecture: arm64
VPC path: VPC 内 Lambda (NAT Gateway or VPC Origin AP)
Iterations: 50 per data point
Statistics: p50, p90, p95, p99, min, max
FSx CloudWatch metrics: DataReadBytes, NetworkThroughput (同時取得)
```

---

## 参考リンク

- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [AWS: Accessing your data via S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [FSx for ONTAP Performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
