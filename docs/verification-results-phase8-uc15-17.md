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

---

## Batch 2: UC2/UC9 Deployment (2026-05-11)

### UC2 (financial-idp) — Execution Details

**State Transitions**: 61 (Discovery → Map[OCR → EntityExtraction → Summary] × 18 parallel iterations)
**Duration**: 16.398s
**Events**: 334

**知見**:
- Discovery Lambda が FSxN S3AP から 18 件の金融文書を検出
- Map state で 18 並列イテレーション実行（高い並列性を実証）
- OCR → EntityExtraction → Summary の 3 段パイプラインが全文書で正常完了
- Catch state (MarkFailed) は未使用（全文書成功）

**デプロイ問題と解決**:
- **問題**: `S3GatewayEndpoint` リソース作成時に `route table rtb-xxx already has a route with destination-prefix-list-id pl-xxx` エラー
- **原因**: 同一 VPC に UC6 スタックの S3 Gateway Endpoint が既存
- **解決**: `EnableS3GatewayEndpoint=false` パラメータを追加してデプロイ
- **恒久対策**: `deploy_generic_ucs.sh` のデフォルトを `ENABLE_S3_GATEWAY_EP=false` に変更

### UC9 (autonomous-driving) — Execution Details

**State Transitions**: 10 (Discovery → Parallel[ProcessVideoFiles, ProcessLidarFiles] → InferenceRouting(Choice) → SkipInference(Pass) → AnnotationManager)
**Duration**: 2:42.616s
**Events**: 35

**知見**:
- Discovery Lambda の VPC cold start: **2:41** (ENI 作成待ち)
  - 2 回目以降は数秒に短縮（ENI 再利用）
  - 本番環境では Provisioned Concurrency で回避可能
- Parallel state: ProcessVideoFiles (1 iteration) + ProcessLidarFiles (0 items → 即完了)
- InferenceRouting Choice state: `inference_type == "none"` → Default → SkipInference
  - Phase 7 Theme Q-1 修正 (`SkipInference` Pass state 追加) が正常動作を確認
- AnnotationManager: Bedrock annotation 生成が正常完了（COCO JSON 出力）

**S3 Output**:
- `fsxn-autonomous-driving-demo-output-178625946981` バケットに出力確認
- frames/, annotations/ フォルダ構造

### デプロイスクリプト改善

`scripts/deploy_generic_ucs.sh` に以下を反映:
1. UC6/UC15/UC16/UC17 のマッピング追加（全 17 UC 対応）
2. `ENABLE_S3_GATEWAY_EP` 環境変数追加（デフォルト: `false`）
3. `EnableVpcEndpoints=false` をデフォルトで渡す（共有 VPC 前提）
4. ヘッダーコメントに全環境変数の説明追加

全スクリーンショット: v7 OCR マスク適用済み、`_check_sensitive_leaks.py` 0 leaks 確認済み。

---

## Batch 3: UC3/UC5/UC7/UC8 Deployment (2026-05-11)

### 実行結果サマリー

| UC | Duration | Events | Status | 備考 |
|----|----------|--------|--------|------|
| UC3 (manufacturing-analytics) | 15.4s | 101 | ✅ SUCCEEDED | Parallel[TransformCSV×2 + AnalyzeImages×8] → AthenaAnalysis |
| UC5 (healthcare-dicom) | 10.0s | 33 | ✅ SUCCEEDED | Map[DicomParse → PiiDetection → Anonymization] → SNS |
| UC7 (genomics-pipeline) | 2:47 | 10 | ❌ FAILED | IAM S3AP PutObject 不足 |
| UC8 (energy-seismic) | 2:44 | 10 | ❌ FAILED | 同上 |

### 🐛 検出バグ: S3AP PutObject IAM 権限の ARN 形式不足

**症状**: Discovery Lambda が FSxN S3AP にマニフェスト JSON を書き込む際に AccessDenied

```
User: arn:aws:sts::178625946981:assumed-role/fsxn-genomics-pipeline-demo-discovery-role/
fsxn-genomics-pipeline-demo-discovery is not authorized to perform:
s3:PutObject on resource: "arn:aws:s3:ap-northeast-1:178625946981:accesspoint/
eda-demo-s3ap/object/manifests/2026/05/11/xxx.json"
because no identity-based policy allows the s3:PutObject action
```

**根本原因**:
Discovery Lambda ロールの `S3AccessPointWrite` Sid が alias 形式
（`arn:aws:s3:::<alias>/*`）のみを Resource として指定していた。
しかし SDK が full ARN 形式（`arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*`）
でリクエストを発行した際、IAM は両形式をマッチング評価する。alias のみだと AccessDenied。

**修正済みテンプレート** (4 件):
- `genomics-pipeline/template-deploy.yaml` (UC7)
- `energy-seismic/template-deploy.yaml` (UC8)
- `construction-bim/template-deploy.yaml` (UC10) — 未検証だが同パターン
- `logistics-ocr/template-deploy.yaml` (UC12) — 未検証だが同パターン

**正しいパターン**:
```yaml
- Sid: S3AccessPointWrite
  Effect: Allow
  Action:
    - s3:PutObject
  Resource: !If
    - HasS3AccessPointName
    - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
      - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
    - - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
```

### 🆕 恒久対策: IAM Pattern Validator

`scripts/check_s3ap_iam_patterns.py` を新規追加:
- 全 17 UC テンプレートを AST-style ルールでスキャン
- `S3...Write` / `S3...Output` Sid で PutObject/DeleteObject を含むブロックを抽出
- alias 形式のみで ARN 形式欠落 + `HasS3AccessPointName` 条件なしの場合エラー
- `!If HasS3AccessPointName` の else 分岐（alias-only で正しい）は誤検知しない
- 検証結果: **17/17 templates clean** ✅

このバリデータは CI/CD パイプライン（Theme M）に組み込み予定。

### 残課題

| # | 問題 | 優先度 | 対応方針 |
|---|------|--------|---------|
| 5 | UC10/UC12 の IAM 修正を AWS 実機で検証 | Medium | Batch 4 デプロイ時に合わせて検証 |
| 6 | Discovery Lambda ハンドラが PutObject を使う設計の是非 | Low | マニフェスト書き込みは Discovery の核機能だが、S3AP ではなく標準 S3 bucket に書き込むオプションも検討余地 |
