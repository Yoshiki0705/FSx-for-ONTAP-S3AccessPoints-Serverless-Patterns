# UC17: スマートシティ — 地理空間データ解析・都市計画

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **ドキュメント**: [アーキテクチャ](docs/architecture.md) | [デモスクリプト](docs/demo-guide.md) | [トラブルシューティング](../docs/phase7-troubleshooting.md)

## 概要

FSx for ONTAP S3 Access Points を活用した地理空間データ（GIS）の
自動解析パイプライン。都市計画、インフラ監視、災害対応のための
衛星画像・LiDAR・IoT センサーデータを統合処理する。

## ユースケース

地方自治体・都市計画機関が、複数ソースの地理空間データを統合し、
都市インフラの状態監視、変化検出、災害リスク評価を自動化する。

### 処理フロー

```
FSx for ONTAP (GIS データ格納 — 部署別アクセス制御)
  → S3 Access Point
    → Step Functions ワークフロー
      → Discovery: 新規データ検出（GeoTIFF, Shapefile, GeoJSON, LAS）
      → Preprocessing: 座標系変換・正規化（EPSG 統一、EPSG:4326）
      → LandUseClassification: 土地利用分類（ML 推論）
      → ChangeDetection: 時系列変化検出（建物新築、緑地減少）
      → InfraAssessment: インフラ劣化評価（道路、橋梁、LAS 点群）
      → RiskMapping: 災害リスクマップ生成（洪水、地震、土砂崩れ）
      → ReportGeneration: 都市計画レポート生成（Bedrock Nova Lite）
```

### 対象データ

| データ形式 | 説明 | 典型サイズ |
|-----------|------|-----------|
| GeoTIFF | 航空写真・衛星画像 | 100 MB – 10 GB |
| Shapefile (.shp) | ベクターデータ（道路、建物、区画） | 1 – 500 MB |
| GeoJSON | 軽量ベクターデータ | 1 KB – 100 MB |
| LAS / LAZ | LiDAR 点群（地形・建物 3D） | 100 MB – 5 GB |
| GeoPackage (.gpkg) | OGC 標準 GIS データベース | 10 MB – 2 GB |

### AWS サービス

| サービス | 用途 |
|---------|------|
| FSx for ONTAP | GIS データの永続ストレージ（部署別 NTFS ACL） |
| S3 Access Points | サーバーレスからのデータアクセス |
| Step Functions | ワークフローオーケストレーション |
| Lambda | 前処理、座標変換、メタデータ抽出 |
| SageMaker (Batch Transform) | 土地利用分類、変化検出 ML 推論（オプション） |
| Amazon Rekognition | 航空写真からの物体検出（建物、車両） |
| Amazon Bedrock Nova Lite | 日本語都市計画レポート生成 |
| DynamoDB | 時系列土地利用履歴、変化検出 |
| SNS | 異常検出アラート |
| CloudWatch | 可観測性 |

### Public Sector 適合性

- **INSPIRE 指令対応**（EU 地理空間データ基盤）
- **OGC 標準準拠**: WMS, WFS, WCS, GeoPackage
- **オープンデータ**: 処理結果を市民向けポータルに公開可能
- **災害対応**: リアルタイム被害状況マッピング
- **データ主権**: 自治体データはリージョン内で完結

### 活用シナリオ

| シナリオ | 入力データ | 出力 |
|---------|-----------|------|
| 都市緑化モニタリング | 衛星画像（時系列） | 緑地面積変化レポート |
| 不法投棄検出 | ドローン画像 | アラート + 位置情報 |
| 道路劣化評価 | 車載カメラ画像 | 補修優先度マップ |
| 洪水リスク評価 | LiDAR + 降雨データ | 浸水予測マップ |
| 建築確認支援 | 航空写真 + 建築申請 | 差分検出レポート |

## 検証済みの画面（スクリーンショット）

### 1. GIS データの格納（S3 Access Point 経由）

自治体 GIS 担当者から見た、解析対象データの配置確認画面。
`gis/YYYY/MM/` プレフィックス配下に GeoTIFF / Shapefile / LAS を配置。

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     内容: S3 AP の gis/ プレフィックス一覧、ファイル形式が混在
     マスク: アカウント ID、S3 AP ARN、実座標由来のファイル名 -->
![UC17: GIS データ格納確認](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Bedrock 生成の都市計画レポート（Markdown 表示）

**UC17 の目玉機能**: 土地利用分布・変化検出・リスク評価を統合して、
Bedrock Nova Lite が自治体担当者向けに日本語レポートを自動生成する。

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     内容: S3 コンソールで reports/*.md をレンダリング表示
     実サンプル内容:
       ### 自治体担当者向け所見レポート
       #### 都市計画上の注目点
       GISデータによると、市内の土地利用分布は安定しており...
       #### 優先すべき対策案
       1. 洪水対策の強化 ... 2. 地震対策の強化 ... 3. 斜面崩壊対策の強化 ...
     マスク: アカウント ID、自治体名（サンプル名のみ表示） -->
![UC17: Bedrock 生成レポート](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. 災害リスクマップ JSON

洪水・地震・土砂崩れの 3 種類のリスクスコアを CRITICAL / HIGH / MEDIUM / LOW
の 4 段階で判定。

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     内容: risk-maps/*.json の整形ビュー（flood, earthquake, landslide の level を強調）
     マスク: アカウント ID -->
![UC17: 災害リスクマップ](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. 土地利用分布（JSON）

Rekognition / SageMaker 推論結果から導出された土地利用クラス分布。
residential / commercial / forest / water / road 等の比率。

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     内容: landuse/*.json の中身（residential: 0.5, forest: 0.3 等）
     マスク: アカウント ID -->
![UC17: 土地利用分布](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. 時系列変化の可視化（DynamoDB Explorer）

`fsxn-uc17-demo-landuse-history` テーブル。area_id ごとに過去の土地利用分布と
現在値を比較し、change_magnitude を計算。

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     内容: DynamoDB Explorer で landuse-history テーブルの時系列項目
     マスク: アカウント ID、area_id -->
![UC17: 時系列変化テーブル](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
地理空間解析（CRS 正規化・土地利用分類・災害リスクマッピング）の自動化により、都市計画の意思決定を支援する。

### Metrics
| メトリクス | 目標値（例） |
|-----------|------------|
| 処理済みデータセット数 / 実行 | > 100 files |
| CRS 正規化成功率 | > 95% |
| 土地利用分類精度 | > 80% |
| リスクマップ生成時間 | < 10 分 |
| コスト / 実行 | < $10 |
| Human Review 対象率 | < 20%（分類不確実エリア） |

### Measurement Method
Step Functions 実行履歴、Bedrock 分析レポート、Rekognition 検出結果、S3 出力 GeoJSON、CloudWatch Metrics。

## デプロイ

### 事前検証

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### ワンショットデプロイ

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### 手動デプロイ

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

**重要**: Bedrock コンソールで `amazon.nova-lite-v1:0` のモデルアクセスを有効化してください。

## ディレクトリ構成

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS 正規化（EPSG:4326）
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ 点群解析
│   ├── risk_mapping/handler.py           # 洪水/地震/土砂リスク
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## AWS ドキュメントリンク

| サービス | ドキュメント |
|---------|------------|
| FSx for ONTAP | [ユーザーガイド](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [開発者ガイド](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [開発者ガイド](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [開発者ガイド](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [ユーザーガイド](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework 対応

| 柱 | 対応 |
|----|------|
| 運用上の優秀性 | X-Ray、EMF、土地利用変化追跡、resilience テスト |
| セキュリティ | 最小権限 IAM、KMS、部署別 NTFS ACL、INSPIRE 準拠 |
| 信頼性 | Step Functions Retry/Catch、CRS 正規化、resilience テスト |
| パフォーマンス効率 | GeoTIFF タイリング、SageMaker Batch Transform |
| コスト最適化 | サーバーレス、SageMaker スポット、DynamoDB 時系列 |
| 持続可能性 | 差分変化検出、OGC 標準準拠 |





---

## コスト見積もり（月額概算）

> **注記**: 以下は ap-northeast-1 リージョンの概算であり、実際のコストは使用量により異なります。最新の料金は [AWS Pricing Calculator](https://calculator.aws/) で確認してください。

### サーバーレスコンポーネント（従量課金）

| サービス | 単価 | 想定使用量 | 月額概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 関数 × 20 datasets/日 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/日 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/日 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/実行 | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/クエリ | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/日 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |

### 固定コスト（FSx for ONTAP — 既存環境前提）

| コンポーネント | 月額 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (既存環境を共有) |
| S3 Access Point | 追加料金なし（S3 API 料金のみ） |

### 合計概算

| 構成 | 月額概算 |
|------|---------|
| 最小構成（日次 1 回実行） | ~$5-15 |
| 標準構成（時次実行） | ~$15-50 |
| 大規模構成（高頻度 + アラーム） | ~$50-150 |

> **Governance Caveat**: コスト見積もりは概算であり、保証値ではありません。実際の請求額は使用パターン、データ量、リージョンにより異なります。

---

## ローカルテスト

### Prerequisites チェック

```bash
# 前提条件の確認
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 認証情報
```

### sam local invoke

```bash
# ビルド
sam build

# Discovery Lambda のローカル実行
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 環境変数オーバーライド付き
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### ユニットテスト

```bash
python3 -m pytest tests/ -v
```

詳細は [ローカルテスト クイックスタート](../docs/local-testing-quick-start.md) を参照してください。

---

## 出力サンプル (Output Sample)

地理空間データ解析パイプラインの出力例:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **注記**: 上記はサンプル出力であり、実際の値は環境・入力データにより異なります。ベンチマーク数値は sizing reference であり、service limit ではありません。

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。組織は適格な専門家に相談してください。

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP の互換性制約、トラブルシューティング、トリガーパターンについては [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照してください。