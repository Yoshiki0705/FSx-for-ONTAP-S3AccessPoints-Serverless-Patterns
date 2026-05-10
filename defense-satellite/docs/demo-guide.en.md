# UC15 デモスクリプト（30 分枠）

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is an auto-generated draft based on the Japanese original. Contributions to improve translation quality are welcome.

## 前提

- AWS アカウント、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `defense-satellite/template-deploy.yaml` をデプロイ済み（`EnableSageMaker=false`）

## タイムライン

### 0:00 - 0:05 イントロ（5 分）

- ユースケース背景: 衛星画像データの増加（Sentinel, Landsat, 商用 SAR）
- 従来型 NAS への課題: コピーベースワークフローで時間・コストがかかる
- FSxN S3AP のメリット: zero-copy、NTFS ACL 連動、サーバーレス処理

### 0:05 - 0:10 アーキテクチャ解説（5 分）

- Mermaid 図で Step Functions ワークフロー紹介
- 画像サイズでの Rekognition / SageMaker 切替ロジック
- geohash による変化検出の仕組み

### 0:10 - 0:15 ライブデプロイ（5 分）

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-uc15-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:20 サンプル画像処理（5 分）

```bash
# サンプル GeoTIFF アップロード
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- AWS コンソールで Step Functions グラフを見せる（Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration）
- SUCCEEDED までの実行時間を確認（通常 2-3 分）

### 0:20 - 0:25 結果確認（5 分）

- S3 出力バケットの階層を見せる:
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- CloudWatch Logs で EMF メトリクス確認
- DynamoDB `change-history` テーブルで変化検出履歴

### 0:25 - 0:30 Q&A + Wrap-up（5 分）

- Public Sector 規制対応（DoD CC SRG, CSfC, FedRAMP）
- GovCloud 移行パス（同じテンプレートで `ap-northeast-1` → `us-gov-west-1`）
- コスト最適化（SageMaker Endpoint は実運用時のみ有効化）
- 次ステップ: 多衛星プロバイダ統合、Sentinel-1/2 Hub 連携

## よくある質問と回答

**Q. SAR データ（Sentinel-1 の HDF5）はどう扱う？**  
A. Discovery Lambda で `image_type=sar` に分類、Tiling は HDF5 パーサ実装可（rasterio or h5py）。Object Detection は専用 SAR 解析モデル（SageMaker）必須。

**Q. 画像サイズ閾値（5MB）の根拠？**  
A. Rekognition DetectLabels API の Bytes パラメータ上限。S3 経由なら 15MB まで可。プロトタイプは Bytes ルートを採用。

**Q. 変化検出の精度は？**  
A. 現行実装は bbox 面積ベースの簡易比較。本格運用では SageMaker のセマンティックセグメンテーション推奨。