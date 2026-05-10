# UC17 デモスクリプト（30 分枠）

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

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
A. Nova Lite は日本語レポート生成でコスト効率が高い。Claude 3 Haiku は精度優先時の代替。

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

UC17 smart-city-geospatial は 2026-05-11 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: CRS 正規化メタデータ / 土地利用分類 / インフラ評価 / リスクマップ / Bedrock 生成レポート

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${AWS::StackName}-output-${AWS::AccountId}`）を作成し、
AI 成果物をそこに書き込みます。Discovery Lambda の manifest のみ S3 Access Point
に書き込まれます（従来通り）。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" パターン）
CRS 正規化メタデータ、土地利用分類結果、インフラ評価、リスクマップ、Bedrock が生成する
都市計画レポート（Markdown）を、FSxN S3 Access Point 経由でオリジナル GIS データと
**同一の FSx ONTAP ボリューム**に書き戻します。
都市計画担当者が SMB/NFS の既存ディレクトリ構造内で AI 成果物を直接参照できます。
標準 S3 バケットは作成されません。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**注意事項**:

- `S3AccessPointName` の指定を強く推奨（Alias 形式と ARN 形式の両方で IAM 許可する）
- 5GB 超のオブジェクトは FSxN S3AP では不可（AWS 仕様）、マルチパートアップロード必須
- ChangeDetection Lambda は DynamoDB のみを使用するため `OutputDestination` の影響を受けません
- Bedrock レポートは Markdown（`text/markdown; charset=utf-8`）として書き出されるため、SMB/NFS
  クライアントのテキストエディタで直接閲覧可能
- AWS 仕様上の制約は
  [プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
  および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照
