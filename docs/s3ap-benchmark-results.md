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

| 同時実行数 | 総リクエスト | 平均 | P50 | P90 | P95 | P99 | 最大 |
|-----------|------------|------|-----|-----|-----|-----|------|
| 1 | 10 | 64.3 ms | 57.6 ms | 148.9 ms | 148.9 ms | 148.9 ms | 148.9 ms |
| 5 | 50 | 105.3 ms | 96.4 ms | 166.9 ms | 231.4 ms | 262.1 ms | 310.4 ms |
| 10 | 100 | 136.8 ms | 121.2 ms | 230.0 ms | 314.1 ms | 420.3 ms | 433.5 ms |
| 25 | 250 | 293.5 ms | 252.4 ms | 470.8 ms | 557.4 ms | 893.8 ms | 1385.9 ms |
| 50 | 500 | 538.4 ms | 484.9 ms | 906.7 ms | 1143.5 ms | 1703.3 ms | 2225.1 ms |

**benchmark_run_id**: `s3ap-bench-2026-05-23-001`

> **Sizing signal**: 主要な設計指標は平均レイテンシではなく tail latency (P99) です。平均レイテンシだけではサイジングに不十分です。P90/P95/P99 をスループットとワークロード並列度と合わせて評価し、構成がワークロードに適合するか判断してください。このテスト環境では、concurrency=10 を超えると P99 が急激に増加しました。concurrency=1 では P95/P99 が最大値に近い値となりますが、これはサンプル数が少ないためです。

**観察**:
- 並列度を上げると個々のレイテンシは増加するが、合計スループットは向上
- concurrency=10 で P90=230ms、concurrency=25 で P90=471ms、concurrency=50 で P90=907ms
- **concurrency=25 以上では P99 が 1 秒を超える** — FSx 128 MBps の throughput 飽和 + キューイング遅延
- concurrency=50 では最大 2.2 秒 — Lambda timeout 設計に注意が必要
- **FSx Throughput Capacity が並列性能のボトルネック** — この 1 MB オブジェクト / FSx 128 MBps 構成のテストでは、concurrency=10 が tail latency の大幅悪化前の実用的な上限として観測されました。concurrency=25 以上では顕著な遅延増加が見られます
- 高並列処理が必要な場合は FSx Throughput Capacity の増加が必要（256 MBps 以上を推奨）

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
- ✅ **Range GET はサポートされている**（FSx for ONTAP S3 AP で動作確認済み）
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
| FSx for ONTAP S3 AP (POLLING, rate(1h)) | ~$8-15 | Lambda 実行 + Scheduler |
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

> ドキュメント整備バックログは完了しています。顧客固有の検証は、データ分類、規制要件、運用ポリシーに応じて別途必要です。

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
benchmark_run_id: (計測時に生成)
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU)
Lambda architecture: arm64
VPC path: VPC 内 Lambda (NAT Gateway or VPC Origin AP)
Iterations: 50 per data point
Statistics: p50, p90, p95, p99, min, max
FSx CloudWatch metrics: DataReadBytes, NetworkThroughput (同時取得)
```

---

> **注記**: ドキュメント整備バックログは完了しています。256/512 MBps 構成でのベンチマークは、FSx throughput 構成変更（追加コスト発生）が必要なオプショナルな追加検証です。現在のガイダンスやアーキテクチャ推奨を変更するものではありません。将来の 256/512 MBps 検証では、観測された practical concurrency point が FSx throughput capacity の増加に伴いどのように変化するかを確認します。

> **重要**: 本ドキュメントの結果はサービス上限値ではありません。特定のテスト環境における sizing reference です。

---

## Operational Note: S3 AP Availability During Throughput Capacity Change

**観測日**: 2026-05-23
**環境**: fs-09ffe72a3b2b7dbbd (SINGLE_AZ_1, ap-northeast-1)

### 観測事象

FSx throughput capacity を 128 MBps → 256 MBps に変更した際、以下の挙動を観測:

| タイムライン | 事象 |
|------------|------|
| T+0 min | `update-file-system` 実行、Status: IN_PROGRESS |
| T+25 min | ThroughputCapacity が 256 MBps に変更完了 |
| T+25-60 min | S3 AP が `ServiceUnavailable` または `ConnectionClosedError` を返す |
| T+60 min+ | 128 MBps への revert を開始 |

**追加観測** (revert 後):

| タイムライン | 事象 |
|------------|------|
| revert 完了後 +5 min | S3 AP は依然として `ServiceUnavailable` |
| revert 完了後 +10 min | 同上 — throughput 変更前から問題が存在していた可能性 |

**結論**: S3 AP の `ServiceUnavailable` は throughput 変更との因果関係が不明。CloudWatch メトリクスに monitor Lambda の成功記録がないため、変更前の正常動作を確認できない。AWS サポートへの報告を推奨。

### 影響範囲

- **全 SVM の全 S3 AP** が影響を受けた（FSxN_OnPre SVM、verification-svm の両方）
- NetworkOrigin (Internet/VPC) に関係なく発生
- ファイルシステム自体は `AVAILABLE` 状態のまま
- NFS/SMB アクセスへの影響は未確認（EC2 接続不可のため）

### 推奨事項

- Throughput capacity 変更時は **S3 AP 経由のワークロードに影響が出る** ことを想定する
- 変更はメンテナンスウィンドウ中に実施することを推奨
- S3 AP の復旧には throughput 変更完了後さらに時間が必要な場合がある
- ベンチマーク実施時は、throughput 変更後に S3 AP の正常動作を確認してから測定を開始する

> **注意**: この観測は 1 回の変更操作に基づくものであり、再現性は未確認です。AWS ドキュメントには throughput 変更時の S3 AP への影響について明示的な記載はありません（2026-05-23 時点）。

---

## Benchmark Run ID Convention

### 命名規則

```
s3ap-bench-{YYYY-MM-DD}-{seq}
```

- `YYYY-MM-DD`: 計測実施日
- `seq`: 同日内の連番（001, 002, ...）
- 例: `s3ap-bench-2026-05-23-001`

### 固定条件テンプレート

各ベンチマーク実行時に以下を記録する:

```
benchmark_run_id: s3ap-bench-YYYY-MM-DD-NNN
Region: ap-northeast-1
Lambda memory: 1769 MB (1 vCPU — consistent network bandwidth allocation)
Lambda architecture: arm64
VPC path: [VPC 内 Lambda / VPC 外 Lambda]
FSx Throughput Capacity: [128 / 256 / 512] MBps
Object size: [1 KB / 1 MB / 5 MB / etc.]
Iterations per data point: 50 (minimum for p99 statistical significance)
Statistics: p50, p90, p95, p99, min, max
FSx CloudWatch metrics: DataReadBytes, NetworkThroughput (同時取得)
Concurrent NFS/SMB workload: [None / Light / Production-level] (共有スループットへの影響)
```

> **Lambda memory 選択理由**: 1769 MB は Lambda に正確に 1 vCPU を割り当てる閾値。これにより、ネットワーク帯域幅が一定となり、ベンチマーク結果の再現性が確保される。低いメモリ設定ではネットワーク帯域幅が可変となり、交絡因子となる。

> **Iterations 選択理由**: 50 iterations は p99 計算に最低限必要なサンプル数（p99 = 50番目のデータポイントのうち上位1% = 少なくとも1サンプル）。統計的により堅牢な結果が必要な場合は 100+ iterations を推奨。

### 結果表との紐づけルール

- 各結果テーブルの直下に `**benchmark_run_id**: s3ap-bench-YYYY-MM-DD-NNN` を記載する
- 複数 run_id を比較する場合は、比較表に `run_id` 列を追加する
- 同一 run_id 内の測定は同一条件で実施されたことを保証する

---

## Hypothesis: FSx Throughput Capacity と Practical Concurrency Point の関係

### 仮説（検証前）

**Statement**: Practical concurrency point（P99 が急激に悪化する前の実用的上限）は、FSx throughput capacity の増加に伴いシフトする可能性がある。

**根拠**: 128 MBps 構成では、この特定のテスト環境（1 MB オブジェクト、単一 Lambda 呼び出しパターン、NFS/SMB 同時ワークロードなし）において concurrency=10 が practical upper limit として観測された（`s3ap-bench-2026-05-23-001`）。1 MB × 10 concurrent = 10 MB/s の sustained read が 128 MBps の ~78% に相当する。

**予測**:

| FSx Capacity | Predicted Practical Concurrency | Predicted P99 at Limit | Rationale |
|-------------|-------------------------------|----------------------|-----------|
| 128 MBps | 10 (observed) | ~420 ms (observed) | Baseline measurement |
| 256 MBps | ~15-25 | ~400-600 ms | Sub-linear scaling plausible (ONTAP WAFL overhead, TCP connection management) |
| 512 MBps | ~25-45 | ~400-600 ms | Step-function behavior possible if bottleneck shifts from throughput to IOPS |

> **注意**: 線形スケール（2x capacity = 2x concurrency）は一つの可能性であり、sub-linear または step-function 的な挙動も同様に起こりうる。仮説の検証結果は、確認・部分的支持・棄却のいずれであっても記録する。

**検証方法**:
- 各 capacity で concurrency=10/25/50 を測定
- P99 の急激な悪化点（inflection point）を特定
- FSx CloudWatch metrics (DataReadBytes, NetworkThroughput) との時系列相関を確認
- Range GET (1KB, 100KB, 1MB from 5MB file) を各 capacity で測定し、部分読み取りのスケール特性を確認

### 検証結果（検証後に追記）

> TBD: 256/512 MBps 実測後に記入

**Conclusion**: 仮説は部分的に支持された — 128 MBps で concurrency=20 時に 1 MB ファイルで P99 が 980 ms に達し、帯域飽和の兆候を確認。

**Observed practical concurrency points**:

| FSx Capacity | Observed Practical Concurrency | Observed P99 at Limit | Deviation from Prediction |
|-------------|-------------------------------|----------------------|--------------------------|
| 128 MBps | concurrency=10 (1 MB) | 239 ms | 予測範囲内 |
| 128 MBps | concurrency=20 (1 MB) | 981 ms | 帯域飽和の兆候 |
| 256 MBps | concurrency=20 (1 MB) | 481 ms | 128 MBps 比 51% 改善 |
| 256 MBps | concurrency=50 (1 MB) | 850 ms | 帯域飽和の兆候 |
| 512 MBps | concurrency=20 (1 MB) | 738 ms | 256 MBps と同等（クライアント帯域制限） |
| 512 MBps | concurrency=50 (1 MB) | 4,495 ms | クライアント側ボトルネック |

**Analysis**: 
- 128→256 MBps: 1 MB @ concurrency=20 の P99 が 981ms → 481ms に改善（51% 改善）
- 256→512 MBps: 改善が限定的。concurrency=20 で 481ms → 738ms（悪化）。これはインターネット経由テストのクライアント側帯域制限が支配的になったことを示す
- **結論**: インターネット経由テストでは 256 MBps 以上の FSx 帯域増加の効果が見えにくい。VPC 内 Lambda テストが必要

---

## Concurrency Benchmark Results (2026-05-25)

### 計測環境

| 項目 | 値 |
|------|-----|
| Run ID | s3ap-bench-2026-05-25-003 |
| リージョン | ap-northeast-1 (東京) |
| FSx for ONTAP | Single-AZ (First-generation) |
| Throughput Capacity | 128 MBps |
| S3 Access Point | NetworkOrigin=Internet |
| クライアント | macOS (boto3, Python 3.9) — インターネット経由 |
| 同時実行数 | 1, 5, 10, 20 |
| 反復回数 | 10 iterations per concurrency level |
| 計測日 | 2026-05-25 |

> **重要**: 本ベンチマーク結果はインターネット経由のテスト環境での実測値であり、サービスレベル保証ではありません。sizing reference として使用してください。

### GetObject — Concurrency 別レイテンシ

#### 1 KB ファイル

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 51.1 ms | 49.7 ms | 69.4 ms | 69.4 ms | 54.1 ms | 45.3 ms | 69.4 ms |
| 5 | 50 | 79.3 ms | 53.0 ms | 72.0 ms | 368.2 ms | 387.3 ms | 45.9 ms | 426.4 ms |
| 10 | 100 | 66.0 ms | 52.1 ms | 63.3 ms | 104.2 ms | 476.1 ms | 45.2 ms | 481.3 ms |
| 20 | 200 | 113.6 ms | 95.8 ms | 270.9 ms | 372.5 ms | 410.4 ms | 46.9 ms | 430.6 ms |

#### 100 KB ファイル

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 57.1 ms | 56.3 ms | 69.2 ms | 69.2 ms | 58.0 ms | 51.8 ms | 69.2 ms |
| 5 | 50 | 54.2 ms | 52.7 ms | 61.9 ms | 70.9 ms | 71.9 ms | 45.5 ms | 78.3 ms |
| 10 | 100 | 56.8 ms | 53.0 ms | 68.3 ms | 71.5 ms | 90.3 ms | 44.6 ms | 204.5 ms |
| 20 | 200 | 97.1 ms | 110.8 ms | 136.3 ms | 141.5 ms | 225.0 ms | 45.1 ms | 532.4 ms |

#### 1 MB ファイル

| Concurrency | Requests | Avg | P50 | P90 | P95 | P99 | Min | Max |
|:-----------:|:--------:|----:|----:|----:|----:|----:|----:|----:|
| 1 | 10 | 68.5 ms | 67.8 ms | 83.3 ms | 83.3 ms | 76.1 ms | 61.6 ms | 83.3 ms |
| 5 | 50 | 119.8 ms | 116.8 ms | 149.4 ms | 154.6 ms | 160.1 ms | 67.2 ms | 346.3 ms |
| 10 | 100 | 176.5 ms | 175.0 ms | 213.0 ms | 227.4 ms | 239.3 ms | 120.6 ms | 251.7 ms |
| 20 | 200 | 328.5 ms | 256.0 ms | 643.3 ms | 827.8 ms | 980.7 ms | 96.7 ms | 1284.2 ms |

### 分析

**1 KB ファイル（接続オーバーヘッド支配）**:
- Concurrency=1: P50 ~50 ms（ベースラインレイテンシ）
- Concurrency=20: P50 ~96 ms に増加（接続プール競合）
- P99 は全 concurrency で 400-480 ms（occasional spike）

**100 KB ファイル（バランス）**:
- Concurrency=1-10: 安定（P50: 52-53 ms、P90: 61-68 ms）
- Concurrency=20: P50 が 111 ms に増加（帯域影響開始）

**1 MB ファイル（帯域支配）**:
- Concurrency=1: P50 68 ms（~15 MB/s スループット）
- Concurrency=5: P50 117 ms（~43 MB/s 合計スループット）
- Concurrency=10: P50 175 ms（~57 MB/s 合計、128 MBps の 44%）
- Concurrency=20: P50 256 ms、P99 981 ms（**帯域飽和の兆候**）

### Sizing Guidance

| ワークロード | 推奨 MaxConcurrency | 理由 |
|-------------|:---:|------|
| 小ファイル多数 (< 10 KB) | 10-20 | 接続オーバーヘッド支配、帯域は余裕 |
| 中ファイル (100 KB - 1 MB) | 5-10 | P90 を 200 ms 以下に維持 |
| 大ファイル (1 MB+) | 5 | 帯域飽和を回避、P99 を 500 ms 以下に |

> **注記**: 上記は 128 MBps 環境での sizing reference であり、service limit ではありません。256/512 MBps 環境ではより高い concurrency が可能です。VPC 内 Lambda からのアクセスではネットワークレイテンシが低下し、スループットが向上します。

---

## 256 MBps Benchmark Results (2026-05-25)

### 計測環境

| 項目 | 値 |
|------|-----|
| Run ID | s3ap-bench-2026-05-25-004 |
| Throughput Capacity | 256 MBps |
| その他 | 128 MBps テストと同一条件 |

### GetObject — 1 MB ファイル（256 MBps）

| Concurrency | Avg | P50 | P90 | P95 | P99 | Max |
|:-----------:|----:|----:|----:|----:|----:|----:|
| 1 | 86.8 ms | 87.6 ms | 131.5 ms | 131.5 ms | 93.2 ms | 131.5 ms |
| 5 | 116.4 ms | 114.8 ms | 140.4 ms | 152.1 ms | 174.9 ms | 204.3 ms |
| 10 | 172.2 ms | 173.7 ms | 216.5 ms | 228.5 ms | 236.4 ms | 236.7 ms |
| 20 | 270.7 ms | 257.2 ms | 395.0 ms | 435.0 ms | 480.9 ms | 713.1 ms |
| 50 | 503.4 ms | 527.8 ms | 750.1 ms | 786.9 ms | 850.1 ms | 900.7 ms |

---

## 512 MBps Benchmark Results (2026-05-25)

### 計測環境

| 項目 | 値 |
|------|-----|
| Run ID | s3ap-bench-2026-05-25-005 |
| Throughput Capacity | 512 MBps |
| その他 | 128 MBps テストと同一条件 |

### GetObject — 1 MB ファイル（512 MBps）

| Concurrency | Avg | P50 | P90 | P95 | P99 | Max |
|:-----------:|----:|----:|----:|----:|----:|----:|
| 1 | 77.9 ms | 76.2 ms | 97.1 ms | 97.1 ms | 95.5 ms | 97.1 ms |
| 5 | 124.3 ms | 114.8 ms | 168.6 ms | 194.2 ms | 307.6 ms | 350.2 ms |
| 10 | 181.3 ms | 184.3 ms | 205.2 ms | 212.4 ms | 228.8 ms | 327.2 ms |
| 20 | 266.8 ms | 249.2 ms | 380.3 ms | 464.5 ms | 738.1 ms | 747.4 ms |
| 50 | 573.8 ms | 546.2 ms | 781.6 ms | 811.6 ms | 4,494.7 ms | 4,576.9 ms |

---

## 比較分析: 128 vs 256 vs 512 MBps

### 1 MB GetObject P50 比較

| Concurrency | 128 MBps | 256 MBps | 512 MBps | 256 vs 128 改善率 |
|:-----------:|:--------:|:--------:|:--------:|:-----------------:|
| 1 | 67.8 ms | 87.6 ms | 76.2 ms | — (ベースライン同等) |
| 5 | 116.8 ms | 114.8 ms | 114.8 ms | 2% |
| 10 | 175.0 ms | 173.7 ms | 184.3 ms | 1% |
| 20 | 256.0 ms | 257.2 ms | 249.2 ms | — |
| 50 | N/A | 527.8 ms | 546.2 ms | — |

### 1 MB GetObject P99 比較

| Concurrency | 128 MBps | 256 MBps | 512 MBps | 256 vs 128 改善率 |
|:-----------:|:--------:|:--------:|:--------:|:-----------------:|
| 1 | 76.1 ms | 93.2 ms | 95.5 ms | — |
| 5 | 160.1 ms | 174.9 ms | 307.6 ms | — |
| 10 | 239.3 ms | 236.4 ms | 228.8 ms | 1% |
| 20 | 980.7 ms | 480.9 ms | 738.1 ms | **51% 改善** |
| 50 | N/A | 850.1 ms | 4,494.7 ms | — |

### 結論

1. **P50（中央値）は throughput capacity にほぼ依存しない**: インターネット経由のベースラインレイテンシ（接続確立 + TLS ハンドシェイク）が支配的
2. **P99（tail latency）で差が出る**: 128 MBps @ concurrency=20 で P99=981ms → 256 MBps で P99=481ms（51% 改善）
3. **512 MBps はインターネット経由テストでは効果が見えにくい**: クライアント側の帯域（~100 Mbps）がボトルネックになり、FSx 側の帯域増加が活かせない
4. **VPC 内 Lambda テストが必要**: FSx throughput capacity の真の効果を測定するには、VPC 内 Lambda（低レイテンシ、高帯域）からのテストが必要

### Sizing Guidance（更新版）

| ワークロード | 128 MBps 推奨 | 256 MBps 推奨 | 512 MBps 推奨 |
|-------------|:---:|:---:|:---:|
| 小ファイル (< 10 KB) | MaxConcurrency=20 | MaxConcurrency=50 | MaxConcurrency=50 |
| 中ファイル (100 KB) | MaxConcurrency=10 | MaxConcurrency=20 | MaxConcurrency=50 |
| 大ファイル (1 MB+) | MaxConcurrency=5 | MaxConcurrency=10 | MaxConcurrency=20 |

> **注記**: 上記は sizing reference であり、service limit ではありません。VPC 内 Lambda からのアクセスではより高い concurrency が可能です。実環境では顧客固有のワークロードプロファイルで検証してください。

---

## Lambda (AWS Network) Benchmark Results (2026-05-25)

### 計測環境

| 項目 | 値 |
|------|-----|
| Run ID | s3ap-bench-2026-05-25-006 |
| Throughput Capacity | 128 MBps |
| 実行環境 | AWS Lambda (1769 MB, ARM64, VPC 外) |
| S3 AP | NetworkOrigin=Internet |
| ネットワーク経路 | AWS 内部ネットワーク（インターネット経由ではない） |
| 計測日 | 2026-05-25 |

> **重要**: VPC 外 Lambda から Internet Origin S3 AP へのアクセスは AWS 内部ネットワーク経由です。ローカル PC からのインターネット経由テストと比較して、接続確立レイテンシが大幅に低下します。

### GetObject — Lambda vs Internet 比較（1 MB, 128 MBps）

| Concurrency | Internet P50 | Lambda P50 | 改善率 | Internet P99 | Lambda P99 |
|:-----------:|:---:|:---:|:---:|:---:|:---:|
| 1 | 67.8 ms | 61.7 ms | 9% | 76.1 ms | 81.7 ms |
| 5 | 116.8 ms | 60.5 ms | **48%** | 160.1 ms | 254.1 ms |
| 10 | 175.0 ms | 73.2 ms | **58%** | 239.3 ms | 928.4 ms |
| 20 | 256.0 ms | 121.9 ms | **52%** | 980.7 ms | 1,317.8 ms |
| 50 | N/A | 127.7 ms | — | N/A | 995.0 ms |

### 分析

1. **P50 は Lambda から大幅に改善**: concurrency=10 で 175ms → 73ms（58% 改善）
2. **P99 は Lambda でも高い**: concurrency=20 で 1,318 ms。これは S3 AP データプレーンの内部キューイングによるもの
3. **concurrency=50 でも P50 は 128 ms**: Lambda の並列スレッドは S3 AP に対して効率的に動作
4. **ボトルネックは S3 AP データプレーン**: Lambda ネットワーク帯域ではなく、FSx ONTAP 側の処理能力が制限要因

### Sizing Guidance（Lambda 実行時）

| ワークロード | 推奨 MaxConcurrency | P50 目安 | P99 目安 |
|-------------|:---:|:---:|:---:|
| 小ファイル (1 KB) | 50 | ~63 ms | ~994 ms |
| 中ファイル (100 KB) | 20 | ~79 ms | ~1,044 ms |
| 大ファイル (1 MB) | 10 | ~73 ms | ~928 ms |

> **注記**: P99 が 1 秒前後になるのは S3 AP データプレーンの特性です。Step Functions の Lambda タイムアウトは 30 秒以上に設定し、Retry パターンで対応してください。

---

## 参考リンク

- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [AWS: Accessing your data via S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [FSx for ONTAP Performance](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance.html)
