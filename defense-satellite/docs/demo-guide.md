# UC15 デモスクリプト（30 分枠）

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

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

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

UC15 defense-satellite は 2026-05-11 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: 衛星画像タイリング / 物体検出 / Geo enrichment

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${AWS::StackName}-output-${AWS::AccountId}`）を作成し、
AI 成果物をそこに書き込みます。Discovery Lambda の manifest のみ S3 Access Point
に書き込まれます（従来通り）。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" パターン）
タイリング metadata、物体検出 JSON、Geo enrichment 済み検出結果を、FSxN S3 Access Point
経由でオリジナル衛星画像と**同一の FSx ONTAP ボリューム**に書き戻します。
分析担当者が SMB/NFS の既存ディレクトリ構造内で AI 成果物を直接参照できます。
標準 S3 バケットは作成されません。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
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
- AlertGeneration Lambda は SNS のみを使用するため `OutputDestination` の影響を受けません
- AWS 仕様上の制約は
  [プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
  および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ✅ **E2E 検証**: SUCCEEDED（Phase 7 Extended Round, commit b77fc3b）
- 📸 **UI/UX 再撮影**: 未実施

### 既存スクリーンショット（Phase 7 検証時）

![UC15 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc15-demo/uc15-stepfunctions-graph.png)

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（detections/、geo-enriched/、alerts/）
- Rekognition 衛星画像物体検出結果 JSON プレビュー
- GeoEnrichment 座標付き検出結果
- SNS アラート通知メール
- FSx ONTAP ボリューム上の AI 成果物（FSXN_S3AP モード時）

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=defense-satellite bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC15` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `satellite-imagery/` プレフィックスにサンプル GeoTIFF をアップロード
   - Step Functions `fsxn-defense-satellite-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-defense-satellite-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（detections, geo-enriched）
   - SNS メール通知（AlertGeneration からの通知）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py defense-satellite-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC15` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
