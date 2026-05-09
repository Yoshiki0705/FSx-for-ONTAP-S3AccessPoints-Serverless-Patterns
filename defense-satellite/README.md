# UC15: 防衛・宇宙 — 衛星画像解析パイプライン

## 概要

FSx for NetApp ONTAP S3 Access Points を活用した衛星画像（SAR / 光学）の
自動解析パイプライン。大容量の衛星画像データを FSx ONTAP に格納し、
S3 Access Points 経由でサーバーレス処理を実行する。

## ユースケース

防衛・インテリジェンス機関および宇宙関連組織が、衛星から取得した
地球観測データ（Earth Observation）を自動的に処理・分析する。

### 処理フロー

```
FSx ONTAP (衛星画像格納)
  → S3 Access Point
    → Step Functions ワークフロー
      → Discovery: 新規画像検出（GeoTIFF, NITF, HDF5）
      → Tiling: 大画像をタイル分割（Cloud Optimized GeoTIFF 変換）
      → ObjectDetection: Rekognition / SageMaker で物体検出
      → ChangeDetection: 時系列比較による変化検出
      → GeoEnrichment: メタデータ付与（座標、撮影日時、解像度）
      → AlertGeneration: 異常検出時のアラート生成
```

### 対象データ

| データ形式 | 説明 | 典型サイズ |
|-----------|------|-----------|
| GeoTIFF | 光学衛星画像 | 100 MB – 10 GB |
| NITF | 軍事標準画像形式 | 500 MB – 50 GB |
| HDF5 | SAR データ（Sentinel-1 等） | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | タイル化済み画像 | 10 – 500 MB |

### AWS サービス

| サービス | 用途 |
|---------|------|
| FSx for NetApp ONTAP | 衛星画像の永続ストレージ（NTFS ACL でアクセス制御） |
| S3 Access Points | サーバーレスからの画像アクセス |
| Step Functions | ワークフローオーケストレーション |
| Lambda | タイル分割、メタデータ抽出、アラート生成 |
| SageMaker (Batch Transform) | 物体検出・変化検出 ML 推論 |
| Amazon Rekognition | ラベル検出（車両、建物、船舶） |
| Amazon Bedrock | 画像キャプション生成、レポート要約 |
| DynamoDB | 処理状態管理、検出結果インデックス |
| SNS | アラート通知 |
| CloudWatch | 可観測性 |

### Public Sector 適合性

- **DoD CC SRG**: FSx for ONTAP は Impact Level 2/4/5 認証済み（GovCloud）
- **CSfC**: NetApp ONTAP は Commercial Solutions for Classified 認証済み
- **FedRAMP**: AWS GovCloud で FedRAMP High 準拠
- **データ主権**: リージョン内でデータ完結（ap-northeast-1 / us-gov-west-1）

## デプロイ

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM
```

## ディレクトリ構成

```
defense-satellite/
├── template.yaml              # SAM テンプレート（開発用）
├── template-deploy.yaml       # CloudFormation テンプレート（デプロイ用）
├── functions/
│   ├── discovery/handler.py   # 新規衛星画像検出
│   ├── tiling/handler.py      # タイル分割 + COG 変換
│   ├── object_detection/handler.py  # 物体検出（Rekognition / SageMaker）
│   ├── change_detection/handler.py  # 時系列変化検出
│   ├── geo_enrichment/handler.py    # 地理メタデータ付与
│   └── alert_generation/handler.py  # アラート生成
├── tests/
│   └── test_discovery.py
└── README.md
```
