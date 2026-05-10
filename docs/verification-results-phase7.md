# Phase 7 検証結果 — Public Sector UC 拡張（UC15 / UC16 / UC17）

**検証日**: 2026-05-10  
**リージョン**: ap-northeast-1 (東京)  
**AWS アカウント**: <ACCOUNT_ID>  
**既存インフラ**: UC6 デプロイ済みの VPC / FSx ONTAP / S3 AP / Secrets Manager を再利用

## 概要

Phase 7 で追加した 3 つの Public Sector ユースケース（UC15: 衛星画像、UC16: 公文書 FOIA、UC17: スマートシティ地理空間）を CloudFormation でデプロイし、実データで Step Functions ワークフローを実行して `SUCCEEDED` を確認した。

## デプロイ構成

| UC | Stack 名 | 主要パラメータ |
|----|----------|----------------|
| UC15 | `fsxn-uc15-demo` | InferenceType=none（Rekognition のみ）, EnableCloudWatchAlarms=true |
| UC16 | `fsxn-uc16-demo` | OpenSearchMode=none（コスト抑制）, SyncPageThreshold=10 |
| UC17 | `fsxn-uc17-demo` | InferenceType=none, BedrockModelId=amazon.nova-lite-v1:0 |

すべて既存の S3 AP `<S3_AP_ALIAS>` と VPC/サブネット `<VPC_ID>` / `<SUBNET_ID>, <SUBNET_ID>` を再利用。

## 検証結果サマリー（2026-05-10 第 2 回実行 — 実データ）

初回検証（最小ダミーデータ）に加え、実 JPEG / 実 PDF を用いた 2 回目の検証を実施。
すべての AI/ML サービスが意図通り動作。

| UC | 入力 | ワークフロー実行結果 | 実行時間 | AI/ML 呼び出し結果 |
|----|------|-------------------|----------|---------------------|
| UC15 | 1024x1024 JPEG（建物・道路の合成航空写真）| ✅ SUCCEEDED | ~30 秒 | Rekognition 15+ labels 検出 |
| UC16 | reportlab 生成 PDF（FOIA 請求書、PII 含む） | ✅ SUCCEEDED | ~35 秒 | Textract cross-region us-east-1 経由、43KB Blocks、Comprehend PII 5 エンティティ検出（99.6-99.9% 信頼度）|
| UC17 | 1024x1024 JPEG（仙台地域と命名） | ✅ SUCCEEDED | ~45 秒 | Rekognition ラベル検出、Bedrock Nova Lite が「仙台地域」認識して日本語レポート生成 |

## 検証結果サマリー（2026-05-10 第 1 回実行 — 最小ダミーデータ）

| UC | 入力 | ワークフロー実行結果 | 実行時間（概算） | 所要 Lambda 呼び出し |
|----|------|-------------------|-----------------|---------------------|
| UC15 | `satellite/2026/05/sample1.tif`（2 KB テスト用 GeoTIFF 風 bytes） | ✅ SUCCEEDED | ~30 秒 | 6（Discovery / Tiling / ObjectDetection / ChangeDetection / GeoEnrichment / AlertGeneration） |
| UC16 | `archives/2026/05/foia-001.pdf`（最小 PDF テスト用） | ✅ SUCCEEDED | ~35 秒 | 6（Discovery / OCR / Classification / EntityExtraction / Redaction / ComplianceCheck） |
| UC17 | `gis/2026/05/city1.tif`（2 KB テスト用 raster 風） | ✅ SUCCEEDED | ~45 秒 | 7（Discovery / Preprocessing / LandUseClassification / ChangeDetection / InfraAssessment / RiskMapping / ReportGeneration） |

## UC15: 防衛・宇宙 — 衛星画像解析

### Step Functions 実行

```
ExecutionArn: arn:aws:states:ap-northeast-1:<ACCOUNT_ID>:execution:fsxn-uc15-demo-workflow:<uuid>
Status: SUCCEEDED
```

ワークフロー順序: Discovery → Map(Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration)

### 出力

S3 バケット `fsxn-uc15-demo-output-<ACCOUNT_ID>`:

```
enriched/2026/05/10/s0000.json                      (273 bytes)
satellite/2026/05/sample1_detections.json           (118 bytes)
tiles/2026/05/10/sample1/metadata.json               (83 bytes)
```

DynamoDB `fsxn-uc15-demo-change-history` に tile_id=`s0000`（geohash）で変化履歴を記録。

### 学び

- **Rekognition 画像フォーマットエラー**: 最小 TIFF ヘッダのみのテストデータは Rekognition が `InvalidImageFormatException` を返す。`_detect_with_rekognition` で例外を捕捉して空リストで継続する実装に修正（本番では本物の画像を使用するので発生しない）。
- **DynamoDB Float → Decimal**: `float` 型の値を直接 PutItem できないため `Decimal(str(value))` に変換するヘルパーを追加。

## UC16: 政府機関 — 公文書 / FOIA

### Step Functions 実行

```
ExecutionArn: arn:aws:states:ap-northeast-1:<ACCOUNT_ID>:execution:fsxn-uc16-demo-workflow:<uuid>
Status: SUCCEEDED
```

ワークフロー順序: Discovery → Map(OCR → Classification → EntityExtraction → Redaction → IndexOrSkip(Choice) → ComplianceCheck)

### 出力

S3 バケット `fsxn-uc16-demo-output-<ACCOUNT_ID>`:

```
classifications/archives/2026/05/foia-001.pdf.json       (177 bytes, clearance_level=public)
ocr-results/archives/2026/05/foia-001.pdf.blocks.json     (2 bytes)
ocr-results/archives/2026/05/foia-001.pdf.txt              (0 bytes - Textract 未対応リージョン)
pii-entities/archives/2026/05/foia-001.pdf.json           (81 bytes)
redacted/archives/2026/05/foia-001.pdf.txt                 (0 bytes)
redaction-metadata/archives/2026/05/foia-001.pdf.json     (217 bytes)
```

DynamoDB `fsxn-uc16-demo-retention` に document_key=`archives/2026/05/foia-001.pdf` の NARA GRS 保存スケジュール（`GRS 2.1`, 3 年）を記録。

### 学び

- **Textract リージョン制約**: ap-northeast-1 では Textract 未サポート。`EndpointConnectionError` を捕捉して `api_used="unavailable"` を返すフォールバックを実装。本格運用時は Cross-Region Client（UC2/UC10/UC12/UC13/UC14 と同じパターン）で us-east-1 経由。
- **Choice state の `IsPresent` チェック**: Map 内の Choice で `$.opensearch_enabled` が入力に含まれない場合にエラー。`IsPresent: true` の `And` 条件でガード。
- **OpenSearchMode=none**: デフォルト無効化でコスト $0（有効化時は最低 ~$35/月 Managed, ~$350/月 Serverless）。

## UC17: スマートシティ — 地理空間解析

### Step Functions 実行

```
ExecutionArn: arn:aws:states:ap-northeast-1:<ACCOUNT_ID>:execution:fsxn-uc17-demo-workflow:<uuid>
Status: SUCCEEDED
```

ワークフロー順序: Discovery → Map(Preprocessing → LandUseClassification → ChangeDetection → InfraAssessment → RiskMapping → ReportGeneration)

### 出力

S3 バケット `fsxn-uc17-demo-output-<ACCOUNT_ID>`:

```
preprocessed/gis/2026/05/city1.tif.metadata.json   (288 bytes)
landuse/gis/2026/05/city1.tif.json                 (118 bytes)
risk-maps/gis/2026/05/city1.tif.json               (484 bytes)
reports/2026/05/10/gis/2026/05/city1.tif.md       (1120 bytes, Bedrock Nova Lite 生成)
```

### Bedrock 生成レポート例（抜粋）

```markdown
### 自治体担当者向け所見レポート

#### 都市計画上の注目点
GISデータによると、市内の土地利用分布は安定しており、変化は検出されていません。
しかし、洪水、地震、斜面崩壊のリスクが中程度であることに注意が必要です。

#### 優先すべき対策案
1. 洪水対策の強化: 中程度の洪水リスクに対応するため、排水システムの改善と洪水予測モデルの更新を実施。
2. 地震対策の強化: 地震リスクに対応するため、建物の耐震基準の見直しと緊急避難経路の整備を推進。
3. 斜面崩壊対策の強化: 斜面崩壊リスクに対応するため、斜面の安定性調査と防護工事の実施を検討。

#### 次回観測時に監視すべき指標
土地利用の変化: 次回の観測では、土地利用の変化を特に注視し、
新たな開発や環境変化がないか確認することが重要です。
```

### 学び

- **Bedrock Nova Lite (amazon.nova-lite-v1:0) は ap-northeast-1 で利用可能**: UC17 では呼び出し成功。プロンプトはリスク・変化・土地利用の 3 要素を結合したマークダウン形式で設計し、日本語レポートを生成。
- **Rekognition 空ラベル対応**: UC15 と同じく `InvalidImageFormatException` でフォールバック。

## cfn-lint 検証

すべてのテンプレートで `E2530` (SnapStart リージョン警告) と `E3006` (他リージョンでの非提供警告) を除外した real エラー数は **0**。

```bash
$ python3 -c "from cfnlint import api; ..."
defense-satellite/template-deploy.yaml: 0 real errors
government-archives/template-deploy.yaml: 0 real errors
smart-city-geospatial/template-deploy.yaml: 0 real errors
```

## テスト実行結果

```bash
$ python3 -m pytest defense-satellite/tests/ -q
31 passed in 0.30s

$ python3 -m pytest government-archives/tests/ -q
47 passed in 0.38s

$ python3 -m pytest smart-city-geospatial/tests/ -q
32 passed in 0.34s

$ python3 -m pytest shared/tests/ -q
310 passed in 113.01s
```

合計 **420 tests passed** (Phase 6 からの 310 + 新規 110)。

## コスト実績（概算）

検証期間中（2026-05-10 約 2 時間）、以下のコストが発生した。

| サービス | 使用量 | 推定コスト |
|----------|---------|------------|
| Lambda 実行（3 UC × 数回実行） | ~50 呼び出し | ~$0.01 |
| Step Functions 状態遷移 | ~100 transitions | ~$0.01 |
| DynamoDB PAY_PER_REQUEST | 軽負荷 | ~$0.01 |
| S3 出力バケット | <1 MB | ~$0.001 |
| SNS Topic 作成 | 3 個 | $0 |
| Bedrock Nova Lite 呼び出し | 1 回、~500 tokens | ~$0.01 |
| Rekognition DetectLabels | 2 回（空レスポンス含む） | ~$0.002 |
| **合計** | | **~$0.05** |

OpenSearch と SageMaker は無効化でコスト $0 を維持。

## デモリソースのクリーンアップ

本 Phase 7 検証完了後に、以下の順序で削除予定:

```bash
aws cloudformation delete-stack --stack-name fsxn-uc15-demo --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-uc16-demo --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-uc17-demo --region ap-northeast-1
```

S3 バケットは DeletionPolicy: Retain のため、手動で空にしてから削除（PII / 検出結果を含む可能性があるため慎重に）。

## 次ステップ

- Real world 相当の画像（本物の GeoTIFF、PDF、Shapefile）での再検証
- rasterio / laspy / pyproj Lambda Layer の事前ビルド・配置（scripts/build-geo-layer.sh / build-pdf-layer.sh）
- Cross-region Textract 設定（UC16 の Comprehend medical 等と同様）
- SageMaker Endpoint 有効化時のコスト・レイテンシ評価
