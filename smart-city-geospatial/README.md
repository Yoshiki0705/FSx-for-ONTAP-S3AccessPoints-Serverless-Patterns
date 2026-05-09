# UC17: スマートシティ — 地理空間データ解析・都市計画

## 概要

FSx for NetApp ONTAP S3 Access Points を活用した地理空間データ（GIS）の
自動解析パイプライン。都市計画、インフラ監視、災害対応のための
衛星画像・LiDAR・IoT センサーデータを統合処理する。

## ユースケース

地方自治体・都市計画機関が、複数ソースの地理空間データを統合し、
都市インフラの状態監視、変化検出、災害リスク評価を自動化する。

### 処理フロー

```
FSx ONTAP (GIS データ格納 — 部署別アクセス制御)
  → S3 Access Point
    → Step Functions ワークフロー
      → Discovery: 新規データ検出（GeoTIFF, Shapefile, GeoJSON, LAS）
      → Preprocessing: 座標系変換・正規化（EPSG 統一）
      → LandUseClassification: 土地利用分類（ML 推論）
      → ChangeDetection: 時系列変化検出（建物新築、緑地減少）
      → InfraAssessment: インフラ劣化評価（道路、橋梁）
      → RiskMapping: 災害リスクマップ生成（洪水、地震、土砂崩れ）
      → ReportGeneration: 都市計画レポート生成（Bedrock）
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
| FSx for NetApp ONTAP | GIS データの永続ストレージ（部署別 NTFS ACL） |
| S3 Access Points | サーバーレスからのデータアクセス |
| Step Functions | ワークフローオーケストレーション |
| Lambda | 前処理、座標変換、メタデータ抽出 |
| SageMaker (Batch Transform) | 土地利用分類、変化検出 ML 推論 |
| Amazon Rekognition | 航空写真からの物体検出（建物、車両） |
| Amazon Bedrock | レポート生成、自然言語での分析結果説明 |
| Amazon Location Service | ジオコーディング、ルート計算 |
| DynamoDB | 処理状態管理、検出結果インデックス |
| SNS | 異常検出アラート（不法投棄、無許可建築） |
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

## デプロイ

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM
```

## ディレクトリ構成

```
smart-city-geospatial/
├── template.yaml              # SAM テンプレート（開発用）
├── template-deploy.yaml       # CloudFormation テンプレート（デプロイ用）
├── functions/
│   ├── discovery/handler.py   # 新規 GIS データ検出
│   ├── preprocessing/handler.py     # 座標系変換・正規化
│   ├── land_use_classification/handler.py  # 土地利用分類
│   ├── change_detection/handler.py  # 時系列変化検出
│   ├── infra_assessment/handler.py  # インフラ劣化評価
│   ├── risk_mapping/handler.py      # 災害リスクマップ生成
│   └── report_generation/handler.py # レポート生成
├── tests/
│   └── test_discovery.py
└── README.md
```
