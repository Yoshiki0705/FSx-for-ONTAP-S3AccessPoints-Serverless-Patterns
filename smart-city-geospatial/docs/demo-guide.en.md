# UC17 デモスクリプト（30 分枠）

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is an auto-generated draft based on the Japanese original. Contributions to improve translation quality are welcome.

## 前提

- AWS アカウント、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Bedrock Nova Lite v1:0 モデル利用可能化

## タイムライン

### 0:00 - 0:05 イントロ（5 分）

- 自治体の課題: 都市計画、災害対応、インフラ保全で GIS データ活用増加
- 従来課題: GIS 解析は ArcGIS / QGIS の専門ソフトウェア中心
- 提案: FSxN S3AP + サーバーレスで自動化

### 0:05 - 0:10 アーキテクチャ（5 分）

- CRS 正規化の重要性（混在するデータソース）
- Bedrock による都市計画レポート生成
- リスクモデル（洪水・地震・土砂崩れ）の計算式

### 0:10 - 0:15 デプロイ（5 分）

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-uc17-demo \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### 0:15 - 0:22 処理実行（7 分）

```bash
# サンプル航空写真アップロード（仙台市の一画）
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

結果確認:
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json`（CRS 情報）
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json`（土地利用分布）
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json`（災害リスクスコア）
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md`（Bedrock 生成レポート）

### 0:22 - 0:27 リスクマップ解説（5 分）

- DynamoDB `landuse-history` テーブルで時系列変化確認
- Bedrock 生成レポートのマークダウンを表示
- 洪水・地震・土砂リスクスコアの可視化

### 0:27 - 0:30 Wrap-up（3 分）

- Amazon Location Service との連携可能性
- 本格運用時の点群処理（LAS Layer デプロイ）
- 次ステップ: MapServer 連携、市民向けポータル

## よくある質問と回答

**Q. CRS 変換は実際に行われる？**  
A. rasterio / pyproj Layer 配置時のみ。`PYPROJ_AVAILABLE` チェックでフォールバック。

**Q. Bedrock モデルの選択基準？**  
A. Nova Lite はコスト/精度バランス良好。長文が必要なら Claude Sonnet 推奨。