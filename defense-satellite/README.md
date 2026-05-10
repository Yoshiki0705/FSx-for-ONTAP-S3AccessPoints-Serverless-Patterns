# UC15: 防衛・宇宙 — 衛星画像解析パイプライン

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **ドキュメント**: [アーキテクチャ](docs/architecture.md) | [デモスクリプト](docs/demo-guide.md) | [トラブルシューティング](../docs/phase7-troubleshooting.md)

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

## 検証済みの画面（スクリーンショット）

2026-05-10 に ap-northeast-1 で実際に稼働確認した際の、**一般職員が日常操作する UI**
を中心に掲載する。技術者向けのコンソール画面（Step Functions グラフ等）は
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md) 参照。

### 1. 衛星画像の格納（FSx ONTAP / S3 Access Point 経由）

ファイルサーバー管理者から見た、解析対象となる衛星画像の配置確認画面。
`satellite/YYYY/MM/` プレフィックス配下に新規画像を配置するだけで、
定期的な Step Functions ワークフローが自動的にピックアップする。

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     内容: S3 AP 経由で satellite/2026/05/*.tif を一覧表示（オブジェクト名、サイズ、更新日時）
     マスク: アカウント ID、Access Point ARN、実衛星画像名 -->
![UC15: 衛星画像配置確認](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. 解析結果の閲覧（S3 出力バケット）

検出結果（`detections/*.json`）、地理メタデータ（`enriched/*.json`）、
タイル情報（`tiles/*/metadata.json`）が整理されて格納される。

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     内容: S3 コンソールで detections/, enriched/, tiles/ の 3 プレフィックスを俯瞰
     マスク: アカウント ID、バケット名プレフィックス -->
![UC15: S3 出力バケット](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. 変化検出アラート（SNS メール通知）

一般職員（運用担当者）が受信する SNS アラートメール。
変化面積が閾値（デフォルト 1 km²）を超えた場合に自動送信される。

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     内容: メールクライアント（Gmail/Outlook）で alert_type=SATELLITE_CHANGE_DETECTED を表示
     マスク: 受信者メールアドレス、送信者アドレス、実座標、tile_id -->
![UC15: SNS アラート通知メール](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. 検出結果 JSON の内容

検出結果（ラベル、信頼度、bbox）のクリーンな JSON ビューア。

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     内容: S3 コンソールでオブジェクトプレビュー、detections JSON の中身
     マスク: アカウント ID -->
![UC15: 検出結果 JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)

## デプロイ

### 事前検証

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### ワンショットデプロイ

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### 手動デプロイ

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM
```

**重要**: `S3AccessPointName` は S3 AP の IAM 権限付与に必須。
詳細は [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md) 参照。

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
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```
