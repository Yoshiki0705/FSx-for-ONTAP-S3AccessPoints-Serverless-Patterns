# 大規模バッチ処理ガイド

## Step Functions Map State のスケーリング

本リポジトリの全 UC は Step Functions Map State (INLINE モード) を使用しています。

### INLINE モードの制限

- 最大 40 iterations/second のスループット
- 1 回の実行で処理可能な最大ペイロード: 256 KB (入力/出力)
- 大量オブジェクト (1,000+) の場合はスロットリングが発生する可能性

### 推奨事項

| オブジェクト数 | 推奨構成 |
|-------------|---------|
| < 100 | INLINE モード (デフォルト) — そのまま使用 |
| 100 - 1,000 | INLINE モード + MapConcurrency 調整 (5-20) |
| 1,000 - 10,000 | DISTRIBUTED モードへの移行を検討 |
| > 10,000 | DISTRIBUTED モード必須 + S3 バッチ分割 |

### DISTRIBUTED モードへの移行

DISTRIBUTED モードを使用する場合は、Step Functions の定義を以下のように変更します:

```json
{
  "Type": "Map",
  "ItemProcessor": {
    "ProcessorConfig": {
      "Mode": "DISTRIBUTED",
      "ExecutionType": "STANDARD"
    }
  },
  "ItemReader": {
    "Resource": "arn:aws:states:::s3:getObject",
    "ReaderConfig": {
      "InputType": "MANIFEST"
    }
  }
}
```

### FSx for ONTAP スループット共有への配慮

MapConcurrency を高く設定すると、FSx for ONTAP の Throughput Capacity を圧迫する可能性があります:

- FSx for ONTAP の Throughput Capacity は NFS/SMB/S3 AP で**共有**
- 推奨: CloudWatch メトリクス `ThroughputUtilization` を監視
- 閾値: 80% 超過が継続する場合は MapConcurrency を下げるか Throughput Capacity を増加

### Textract 同期 API の制限

Textract `AnalyzeDocument` (同期 API) は 5 MB/ドキュメントの制限があります。
5 MB を超える PDF を処理する場合は `StartDocumentAnalysis` (非同期 API) への切り替えが必要です。

## UC 別 MapConcurrency 推奨値

| UC | 想定ファイル数/実行 | 推奨 MapConcurrency | 理由 |
|----|-------------------|-------------------|------|
| UC18 (通信) | 100-1,000 | 10-20 | CDR ファイルは小さい、Athena クエリが並列化可能 |
| UC19 (広告) | 50-500 | 10 | Rekognition API の Rate Limit 考慮 |
| UC20 (旅行) | 20-200 | 10 | Textract Cross-Region の同時実行制限 |
| UC21 (農業) | 10-100 | 5-10 | 500MB 画像の読み取りスループット考慮 |
| UC22 (運輸) | 50-500 | 10-15 | 安全重要のため処理速度より正確性優先 |
| UC23 (ESG) | 10-50 | 5-10 | Bedrock 推論が主要ボトルネック |
| UC24 (NPO) | 10-100 | 10 | 標準的なドキュメント処理 |
| UC25 (電力) | 100-1,000 | 10-20 | ドローン画像は比較的小さい |
| UC26 (不動産) | 20-200 | 10 | Rekognition + Textract 並行 |
| UC27 (HR) | 10-100 | 5-10 | PII 保護処理のオーバーヘッド |
| UC28 (化学) | 10-50 | 5-10 | SDS 文書は比較的少数 |

## FSx for ONTAP Throughput Capacity 別の推奨 MapConcurrency 上限

S3 AP 経由のスループットは FSx for ONTAP の Throughput Capacity に制約されます。以下はプロビジョニング済み Throughput Capacity ごとの MapConcurrency 上限目安です。

| Throughput Capacity (MBps) | 推奨 MapConcurrency 上限 | 備考 |
|---------------------------|------------------------|------|
| 128 | 5-10 | 最小構成。他 NFS/SMB ワークロードとの共有に注意 |
| 256 | 10-15 | 小〜中規模。S3 AP + 他ワークロード混在可能 |
| 512 | 15-25 | 中規模。バッチ処理専用時間帯の設定推奨 |
| 1024 | 25-40 | 大規模。大量ファイル処理に対応 |
| 2048 | 40-60 | 最大構成。DISTRIBUTED モード + 高並列に対応 |

> **注意**: 上記はサイジング参考値であり、サービス保証値ではありません。実際のスループットはファイルサイズ、アクセスパターン、同時 NFS/SMB ワークロードにより異なります。CloudWatch メトリクス `ThroughputUtilization` を監視し、80% 超過が継続する場合は MapConcurrency を下げるか Throughput Capacity の増加を検討してください。

### Lambda /tmp ストレージの制限

Lambda のエフェメラルストレージ (`/tmp`) はデフォルト 512 MB、最大 10,240 MB (10 GB) まで拡張可能です。

| UC | 想定最大ファイルサイズ | 推奨 /tmp サイズ | テンプレート設定 |
|----|---------------------|----------------|---------------|
| UC21 (農業) | 500 MB (GeoTIFF) | 1024 MB | `EphemeralStorage: Size: 1024` |
| UC25 (電力) | FLIR thermal (~100 MB) | 512 MB (デフォルト) | — |
| その他 UC | < 50 MB | 512 MB (デフォルト) | — |

大きなファイルをメモリ内で処理する場合は `LambdaMemorySize` も合わせて増加してください（目安: ファイルサイズの 2-3 倍）。
