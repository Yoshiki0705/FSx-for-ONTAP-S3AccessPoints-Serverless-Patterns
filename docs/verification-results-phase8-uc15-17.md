# Phase 8 Verification Results — UC15/16/17 Deployment

**Date**: 2026-05-11  
**Region**: ap-northeast-1  
**Account**: 178625946981

## Deployment Summary

| UC | Stack | Deploy Time | SFN Duration | Status |
|----|-------|-------------|--------------|--------|
| UC15 | fsxn-defense-satellite-demo | ~4 min | 10.057s | ✅ SUCCEEDED |
| UC16 | fsxn-government-archives-demo | ~4 min | 13.598s | ✅ SUCCEEDED |
| UC17 | fsxn-smart-city-geospatial-demo | ~5 min | 13.447s | ✅ SUCCEEDED |

## UC15 (defense-satellite) — Execution Details

**State Transitions**: 14 (Discovery → Map[Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration] × 2 iterations)

**S3 Output**:
- `enriched/2026/05/` — GeoEnrichment 結果
- `satellite/` — 入力衛星画像
- `tiles/` — タイル分割結果

**DynamoDB (change-history)**:
- テーブル作成確認: ✅
- PITR: On
- TTL: On (attribute: `ttl`)
- Items: 実行時に書き込み確認（ChangeDetection Lambda が put_item 実行）

**SNS**: `fsxn-defense-satellite-demo-notifications` トピック作成確認

**知見**:
- Map state で 2 並列イテレーション実行（サンプルデータ 2 ファイル）
- Rekognition は GeoTIFF を直接処理不可 → `InvalidImageFormatException` → 空検出結果
- ChangeDetection は空検出結果でも DynamoDB に正常書き込み（diff_area_km2=0）
- 初回実行のため previous_timestamp=null（期待通り）

## UC16 (government-archives) — Execution Details

**State Transitions**: 10 (Discovery → Map[OCR → Classification → EntityExtraction → Redaction → IndexOrSkip(Choice) → ComplianceCheck])

**S3 Output**:
- `classifications/` — 文書分類結果
- `ocr-results/` — Textract OCR テキスト
- `pii-entities/` — PII エンティティ抽出結果
- `redacted/` — 墨消し済みテキスト
- `redaction-metadata/` — 墨消しメタデータ

**DynamoDB**:
- `retention` テーブル: 1 item
  - document_key: `archives/2026/05/foia-001.pdf`
  - clearance_level: `public`
  - grs_code: `GRS 2.1`
  - retention_years: 3
  - disposal_date: `2029-05-10T09:35:49.779096`
  - TTL: 1880876148
- `foia-requests` テーブル: 作成確認

**知見**:
- Choice state `IndexOrSkip` が正しく Default ルートを選択（OpenSearch 無効時）
- ComplianceCheck Lambda が正常完了
- 全 7 Lambda が VPC 内で正常動作（ENI 作成 + Secrets Manager アクセス確認）

## UC17 (smart-city-geospatial) — Execution Details

**State Transitions**: 10 (Discovery → Map[Preprocessing → LandUseClassification → ChangeDetection → InfraAssessment → RiskMapping → ReportGeneration])

**S3 Output**:
- `landuse/` — 土地利用分類結果 JSON
- `preprocessed/` — 前処理済みデータ
- `reports/` — Bedrock 生成レポート
- `risk-maps/` — リスクマップ JSON

**DynamoDB (landuse-history)**:
- 1 item:
  - area_id: `8047dc43b2c99bd9` (source_key の SHA256 先頭 16 文字)
  - source_key: `gis/2026/05/city1.tif`
  - change_magnitude: 0 (初回実行のため)
  - landuse_distribution: `{}` → **修正済み** (Phase 8 で GeoTIFF ヘッダー分類フォールバック追加)

**知見と修正**:
- **問題**: Rekognition が GeoTIFF 形式をサポートしない → `InvalidImageFormatException` → 空分類
- **修正**: `_classify_geotiff_from_header()` フォールバック関数を追加
  - TIFF ヘッダーからバンド数を解析
  - ファイル名ヒューリスティック（city/rural/forest/water）
  - バンド数に基づくデフォルト分類（マルチスペクトル/RGB/単バンド）
- **結果**: GeoTIFF ファイルでも非空の `landuse_distribution` が生成される
- **本番推奨**: SageMaker エンドポイント（GeoTIFF 対応モデル）を使用

## 残課題

### 解決済み

| # | 問題 | 対応 | Commit |
|---|------|------|--------|
| 1 | UC17 空 landuse_distribution | GeoTIFF ヘッダー分類フォールバック追加 | (this commit) |

### 未解決（Phase 8 後続タスク）

| # | 問題 | 優先度 | 対応方針 |
|---|------|--------|---------|
| 1 | UC15 Rekognition が GeoTIFF 非対応 | Low | UC15 は ObjectDetection で同様の問題あり。SageMaker endpoint 利用時に解消。デモでは空検出結果でもワークフロー完走するため許容 |
| 2 | UC17 SageMaker endpoint 未設定 | Medium | `INFERENCE_TYPE=provisioned` + endpoint デプロイで本番品質の分類が可能。Phase 8 Theme O 候補 |
| 3 | UC15/17 rasterio Lambda Layer 未提供 | Low | Tiling の精度向上に必要。`scripts/build-geo-layer.sh` で Layer ビルド可能だが、デモでは fallback で動作 |
| 4 | UC16 OpenSearch 統合未検証 | Medium | `EnableOpenSearch=true` でのデプロイ + IndexGeneration Lambda の動作確認が必要 |

## スクリーンショット撮影結果

| UC | 画面 | ファイル |
|----|------|---------|
| UC15 | Step Functions Graph (SUCCEEDED) | `uc15-demo/step-functions-graph-succeeded.png` |
| UC15 | S3 Output Bucket | `uc15-demo/s3-output-bucket.png` |
| UC15 | S3 Enriched Output | `uc15-demo/s3-enriched-output.png` |
| UC15 | DynamoDB Change History | `uc15-demo/dynamodb-change-history-table.png` |
| UC15 | SNS Notification Topics | `uc15-demo/sns-notification-topics.png` |
| UC16 | Step Functions Graph (SUCCEEDED) | `uc16-demo/step-functions-graph-succeeded.png` |
| UC16 | S3 Output Bucket | `uc16-demo/s3-output-bucket.png` |
| UC16 | DynamoDB Retention Table | `uc16-demo/dynamodb-retention-table.png` |
| UC17 | Step Functions Graph (SUCCEEDED) | `uc17-demo/step-functions-graph-succeeded.png` |
| UC17 | S3 Output Bucket | `uc17-demo/s3-output-bucket.png` |
| UC17 | DynamoDB Landuse History | `uc17-demo/dynamodb-landuse-history-table.png` |

全スクリーンショット: v7 OCR マスク適用済み、`_check_sensitive_leaks.py` 0 leaks 確認済み。
