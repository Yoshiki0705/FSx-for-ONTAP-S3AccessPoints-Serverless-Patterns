# クリエイティブアセット管理 — アセットカタログ化とブランドコンプライアンスチェック Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、広告クリエイティブアセットの自動カタログ化とブランドコンプライアンスチェックパイプラインを実演する。Rekognition によるビジュアル分析と Bedrock によるブランドガイドライン準拠チェックで、広告制作の品質管理を自動化する。

**デモの核心メッセージ**: クリエイティブアセットを AI が自動分析し、ブランドガイドライン準拠を検証、アセットカタログを自動生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | クリエイティブオペレーションマネージャー / ブランドマネージャー |
| **日常業務** | アセット管理、ブランドガイドライン準拠確認、コンプライアンスレビュー |
| **課題** | 大量のクリエイティブアセットのブランド準拠を効率的に確認し、問題コンテンツを早期発見したい |
| **期待する成果** | アセットカタログ作成工数の削減とコンプライアンス違反の早期検出 |

### Persona: 佐藤さん（クリエイティブオペレーションマネージャー）

- 日々数百件のクリエイティブアセット（バナー、動画、SNS 用画像）を管理
- 「ブランドガイドラインに反するアセットを事前に自動検出し、レビュー負荷を軽減したい」
- アセットのメタデータ付与とカタログ化を自動化して検索性を向上させたい

---

## Demo Scenario: クリエイティブアセットのカタログ化とコンプライアンスチェック

### ワークフロー全体像

```
クリエイティブアセット  →  自動検出  →  ビジュアル分析 / ブランドチェック  →  アセットカタログ
 (FSx ONTAP)              S3 AP        Rekognition / Textract / Bedrock     S3 + SNS アラート
```

---

## ステップバイステップ デプロイ・検証手順

### Step 1: 前提条件の確認

```bash
# AWS CLI バージョン確認
aws --version   # v2.x 必須

# SAM CLI バージョン確認
sam --version   # 1.x 以上

# Python バージョン確認
python3 --version  # 3.9 以上

# AWS 認証情報確認
aws sts get-caller-identity
```

### Step 2: リポジトリのクローンとディレクトリ移動

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/adtech-creative-management
```

### Step 3: テスト用サンプルデータの配置

FSx ONTAP ボリューム上に以下の構造でサンプルデータを配置します:

```
/creative-assets/
  campaigns/
    summer-2026/
      banner-001.jpeg       # Web バナー広告
      banner-002.png        # SNS 用画像
      video-001.mp4         # 動画広告（15秒）
  brand/
    logo-usage-001.png      # ロゴ使用例
    product-shot-001.tiff   # 商品撮影画像
```

**ブランドガイドライン JSON（output バケットに配置）**:
```json
{
  "brand_name": "SampleBrand",
  "required_terms": ["SampleBrand", "公式"],
  "prohibited_terms": ["最安値", "No.1", "業界初"],
  "required_disclaimers": ["※個人の感想です", "※効果には個人差があります"],
  "prohibited_moderation_categories": ["Explicit Nudity", "Violence", "Drugs"],
  "dimension_constraints": {
    "min_width": 300,
    "min_height": 250,
    "max_file_size_mb": 5000
  }
}
```


**NFS マウントとファイル配置例:**

```bash
# FSx ONTAP NFS マウント
sudo mount -t nfs <FSxN-DATA-LIF-IP>:/vol1 /mnt/fsxn

# サンプルデータ配置
cp -r sample-data/* /mnt/fsxn/<prefix>/
```

### Step 4: SAM ビルドとデプロイ

```bash
# SAM ビルド
sam build

# デプロイ（samconfig.toml.example をコピーして編集）
cp samconfig.toml.example samconfig.toml
# samconfig.toml の parameter_overrides を編集

# または直接デプロイ
sam deploy \
  --stack-name fsxn-adtech-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    BrandGuidelinesS3Key=brand-guidelines.json \
    ModerationConfidenceThreshold=80 \
    MaxTagsPerAsset=50 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: デプロイの確認

```bash
# スタック状態確認
aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1

# Lambda 関数一覧確認
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'adtech')].FunctionName" \
  --region ap-northeast-1
```

### Step 6: ワークフローの手動実行

```bash
# Step Functions ARN を取得
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

# ワークフローを手動実行
EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 \
  --query "executionArn" \
  --output text)

echo "Execution ARN: $EXECUTION_ARN"
```

### Step 7: 実行状態の監視

```bash
# 実行状態の確認
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN \
  --query "status" \
  --region ap-northeast-1

# ステップ別の実行履歴確認
aws stepfunctions get-execution-history \
  --execution-arn $EXECUTION_ARN \
  --region ap-northeast-1 \
  --output table
```

### Step 8: 出力結果の確認

```bash
# 出力バケット名を取得
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

# 実行 ID でレポートを確認
EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/ --region ap-northeast-1

# アセットカタログ（JSON）を確認
aws s3 cp \
  s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool

# フラグ付きアセット（モデレーション違反）を確認
aws s3 cp \
  s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/flagged-assets.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

### Step 9: CloudWatch メトリクスの確認

```bash
# 処理統計メトリクスを確認
aws cloudwatch get-metric-statistics \
  --namespace FSxN-S3AP-Patterns \
  --metric-name SuccessCount \
  --dimensions Name=UseCase,Value=adtech-creative-management \
  --start-time $(date -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --region ap-northeast-1
```

---

## 検証チェックリスト

| チェック項目 | 確認方法 | 期待される結果 |
|------------|---------|--------------|
| メディアファイル検出 | Step Functions 実行ログ | Discovery ステップがアセットファイル数を返す |
| ラベル抽出 | `asset-catalog.json` 確認 | 各アセットに最大 50 タグが付与されている |
| モデレーション検査 | `flagged-assets.json` 確認 | 問題コンテンツがフラグ付きで一覧化されている |
| テキスト抽出 | アセットカタログ確認 | テキストオーバーレイが抽出されている |
| ブランド準拠チェック | カタログの compliance_status 確認 | compliant / non-compliant が正しく判定 |
| SNS アラート | メール受信確認 | モデレーション違反がある場合のみ通知メールが届く |

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Discovery Lambda タイムアウト | VPC 内から S3 AP へのアクセス失敗 | NetworkOrigin 設定を確認。Internet Origin AP の場合は VPC 外実行か NAT Gateway 経由が必要 |
| Rekognition 呼び出しエラー | リージョン非対応 or モデルアクセス未許可 | Rekognition がリージョンで利用可能か確認 |
| Textract 呼び出しエラー | クロスリージョン設定不備 | shared/cross_region_client.py の us-east-1 設定を確認 |
| Bedrock 呼び出し失敗 | モデルアクセス未許可 | Bedrock コンソールでモデルアクセスを有効化 |
| `AccessDenied` on S3 AP | IAM ポリシーの ARN 形式が誤り | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用しているか確認 |
| ブランドガイドライン未検出 | S3 キーが間違い | `BrandGuidelinesS3Key` パラメータと output バケット内のファイルパスを確認 |

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 日々数百件のクリエイティブアセットが制作される。手動でのブランドガイドライン準拠確認は工数がかかり、問題コンテンツの見逃しリスクがある。

**Key Visual**: クリエイティブアセット一覧、ブランドガイドライン PDF

### Section 2: Data Discovery（0:45–1:30）

**ナレーション要旨**:
> EventBridge Scheduler が毎日 00:00 UTC にワークフローを起動。Discovery Lambda が S3 AP 経由でクリエイティブアセットを自動検出。5 GB 以下のメディアファイルをフィルタリング。

**Key Visual**: Step Functions グラフ、Discovery ステップの実行ログ

### Section 3: Visual Analysis（1:30–2:30）

**ナレーション要旨**:
> Visual Analyzer が Rekognition で各アセットを分析。ラベル抽出（最大 50 タグ）、テキスト検出、モデレーション検査を実行。問題コンテンツには自動でフラグ付け。

**Key Visual**: Rekognition ラベル結果、モデレーション検出結果

### Section 4: Brand Compliance（2:30–3:45）

**ナレーション要旨**:
> Textract がテキストオーバーレイを抽出。Bedrock がブランド用語ガイドラインと照合し、準拠/非準拠を判定。禁止用語や必須免責事項の有無をチェック。

**Key Visual**: テキスト抽出結果、ブランド準拠チェック結果（compliant / non-compliant）

### Section 5: Asset Catalog（3:45–5:00）

**ナレーション要旨**:
> Report Lambda がアセットカタログを JSON + CSV で自動生成。モデレーション違反アセットは "requires-review" でフラグ付けされ、SNS でアラート。レビュー担当者は問題アセットのみ確認すれば良い。

**Key Visual**: アセットカタログ JSON、CSV ファイル、SNS 通知メール

---

## クリーンアップ

```bash
# 出力バケットのデータ削除
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

# スタック削除
aws cloudformation delete-stack \
  --stack-name fsxn-adtech-demo \
  --region ap-northeast-1

# 削除完了まで待機
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-adtech-demo \
  --region ap-northeast-1

echo "クリーンアップ完了"
```

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション（並列 Map State） |
| Lambda (Discovery) | S3 AP からのメディアファイル検出 |
| Lambda (Visual Analyzer) | Rekognition ラベル + モデレーション + テキスト検出 |
| Lambda (Text Compliance) | Textract テキスト抽出 + Bedrock ブランドチェック |
| Lambda (Report) | アセットカタログ生成 + SNS アラート |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| Rekognition 呼び出し失敗 | exponential backoff 3 回リトライ後にエラー記録 |
| Textract 抽出失敗 | exponential backoff 3 回リトライ後にエラー記録 |
| Bedrock 推論失敗 | exponential backoff 3 回リトライ後に SNS 通知 |
| ファイル破損・未対応フォーマット | エラー記録し、残りファイルを継続処理 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*
---

## 出力先について: OutputDestination で選択可能

本パターンは `OutputDestination` パラメータで AI 成果物の書き込み先を選択できます。

| モード | 説明 |
|--------|------|
| `STANDARD_S3`（デフォルト） | 新しい S3 バケットに書き込み |
| `FSXN_S3AP` | FSx for ONTAP S3 AP 経由で同一ボリュームに書き戻し（NFS/SMB ユーザーが直接参照可能） |

```bash
# STANDARD_S3 モード（デフォルト）
sam deploy --parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP モード（no data movement）
sam deploy --parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/ ...
```

詳細は [output-destination-patterns.md](../../docs/output-destination-patterns.md) を参照。

---

## 検証済みの UI/UX スクリーンショット

### 検証ステータス

- ⏳ **E2E 検証**: 未実施（デプロイ・実行予定）
- 📸 **UI/UX 撮影**: 未実施（検証後に撮影予定）

### 推奨撮影リスト

以下の画面を検証時に撮影する予定です:

- Step Functions ワークフロー実行成功画面
- S3 出力バケットのディレクトリ構造
- AI/ML 処理結果の JSON プレビュー
- SNS 通知メール
- CloudWatch メトリクスダッシュボード

---

## 撮影ガイド

### 事前準備

```bash
# Lambda パッケージ作成
cd adtech-creative-management
sam build

# デプロイ
sam deploy --guided
```

### 撮影手順

1. **サンプルデータ配置**: S3 AP 経由でテストファイルをアップロード
2. **ワークフロー実行**: Step Functions を手動実行
3. **画面撮影**:
   - Step Functions 実行グラフ（SUCCEEDED 状態）
   - S3 出力バケットの俯瞰
   - AI 処理結果 JSON のプレビュー
   - SNS 通知メール（受信確認）
4. **マスク処理**: `python3 scripts/mask_uc_demos.py <stack-name>` で自動マスク

### マスク対象

- AWS アカウント ID（12 桁）
- リソース ID（vpc-xxx, subnet-xxx 等）
- IP アドレス
- メールアドレス
- ブラウザのユーザー名表示

> 詳細は [`docs/screenshots/MASK_GUIDE.md`](../../docs/screenshots/MASK_GUIDE.md) を参照。

