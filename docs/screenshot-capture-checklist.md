# UI/UX スクリーンショット撮影チェックリスト

**作成日**: 2026-05-11
**目的**: Phase 7 やり残しの UI/UX スクリーンショット撮影を追跡
**担当**: Kiro B（AWS 環境アクセス + ブラウザ撮影）

---

## 撮影方針

- **対象**: エンドユーザーが日常業務で実際に見る UI/UX 画面
- **除外**: Step Functions グラフ（全17UC撮影済み）、CloudFormation スタックイベント
- **マスク**: v7 OCR マスク（`python3 scripts/mask_uc_demos.py <dir>`）
- **検証**: `python3 scripts/_check_sensitive_leaks.py` で 0 leak 確認
- **保存先**: `docs/screenshots/masked/uc*-demo/`

---

## ステータス凡例

- ✅ 撮影済み + マスク済み + demo-guide に埋め込み済み
- 📸 撮影対象として定義済み（未撮影）
- ➖ 該当なし

---

## UC 別チェックリスト

### 完了済み（UI/UX スクリーンショットあり）

| UC | 撮影済み画面 | ステータス |
|----|-------------|-----------|
| UC6 (semiconductor-eda) | FSx Volumes, S3 output, Athena query, Bedrock review | ✅ 4枚 |
| UC11 (retail-catalog) | Product tags, S3 output | ✅ 2枚 |
| UC14 (insurance-claims) | Claims report, S3 output | ✅ 2枚 |

### 要撮影（プレースホルダーあり）

| UC | 推奨撮影リスト | ステータス |
|----|---------------|-----------|
| UC2 (financial-idp) | S3 output, Textract OCR, Comprehend entities, Bedrock summary | 📸 |
| UC3 (manufacturing-analytics) | S3 output, Athena query, Rekognition labels, Quality report | 📸 |
| UC4 (media-vfx) | （再検証時に定義） | 📸 |
| UC5 (healthcare-dicom) | S3 output, Comprehend Medical, DICOM metadata | 📸 |
| UC7 (genomics-pipeline) | S3 output, Athena query, Comprehend Medical, Bedrock report | 📸 |
| UC8 (energy-seismic) | S3 output, Athena query, Rekognition labels, Anomaly report | 📸 |
| UC9 (autonomous-driving) | S3 output, Rekognition keyframes, LiDAR QC, COCO JSON | 📸 |
| UC10 (construction-bim) | S3 output, Textract OCR, BIM diff, Bedrock safety check | 📸 |
| UC12 (logistics-ocr) | S3 output, Textract OCR, Rekognition labels, Delivery report | 📸 |
| UC13 (education-research) | S3 output, Textract OCR, Comprehend entities, Network report | 📸 |

### 要撮影（Phase 7 新規 UC — セクション追加済み）

| UC | 推奨撮影リスト | ステータス |
|----|---------------|-----------|
| UC15 (defense-satellite) | S3 output, Rekognition detections, GeoEnrichment, SNS alert, FSx output | 📸 |
| UC16 (government-archives) | S3 output, Textract OCR, Redaction, DynamoDB retention, FOIA SNS, OpenSearch | 📸 |
| UC17 (smart-city-geospatial) | S3 output, Bedrock report, DynamoDB landuse, Risk map, FSx output | 📸 |

---

## 撮影不要（Step Functions Graph のみで十分な UC）

| UC | 理由 |
|----|------|
| UC1 (legal-compliance) | Phase 1 スクリーンショット + SFN graph で十分 |

---

## 撮影の優先順位（推奨）

1. **UC15/16/17** — Phase 7 新規 UC、記事公開に直結
2. **UC2/UC9** — 金融 IDP と自動運転は読者関心が高い
3. **UC3/UC5/UC7/UC8/UC10/UC12/UC13** — 残り全 UC

---

## デプロイ戦略（コスト最適化）

全 UC を同時にデプロイすると VPC/NAT Gateway コストが嵩む。以下のバッチ方式を推奨:

### Batch 1: UC15/16/17（Public Sector）
```bash
bash scripts/deploy_generic_ucs.sh UC15 UC16 UC17
# → 撮影 → マスク → leak check → commit
bash scripts/cleanup_generic_ucs.sh UC15 UC16 UC17
```

### Batch 2: UC2/UC9（高優先度）
```bash
bash scripts/deploy_generic_ucs.sh UC2 UC9
# → 撮影 → マスク → leak check → commit
bash scripts/cleanup_generic_ucs.sh UC2 UC9
```

### Batch 3: UC3/UC5/UC7/UC8（残り前半）
```bash
bash scripts/deploy_generic_ucs.sh UC3 UC5 UC7 UC8
# → 撮影 → マスク → leak check → commit
bash scripts/cleanup_generic_ucs.sh UC3 UC5 UC7 UC8
```

### Batch 4: UC4/UC10/UC12/UC13（残り後半）
```bash
bash scripts/deploy_generic_ucs.sh UC4 UC10 UC12 UC13
# → 撮影 → マスク → leak check → commit
bash scripts/cleanup_generic_ucs.sh UC4 UC10 UC12 UC13
```

---

## 撮影後の作業

1. `python3 scripts/mask_uc_demos.py <uc-dir>` で v7 OCR マスク
2. `python3 scripts/_check_sensitive_leaks.py` で 0 leak 確認
3. demo-guide.md に `![...]()` 形式で埋め込み
4. 8 言語版 demo-guide にも同じ画像参照を追加（パスは共通）
5. git commit + push（論理単位で分割）

---

## Phase 8 tasks.md との対応

このチェックリストは Phase 8 Theme D（タスク 12-15）に対応。
B セッションが Phase 8 実装と並行して撮影する場合、以下に注意:

- 撮影対象 UC のスタックが Phase 8 で変更されている場合、Phase 8 版で撮影する
- demo-guide.md の編集は A セッションの exclusive region（ドキュメント）
- screenshots/ ディレクトリへの画像追加は B セッションの exclusive region（AWS 操作）
