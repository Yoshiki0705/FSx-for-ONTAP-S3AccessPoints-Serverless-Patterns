# UC11: 小売 / EC — 商品画像自動タグ付け・カタログメタデータ生成

## 概要

FSx for NetApp ONTAP の S3 Access Points を活用し、商品画像の自動タグ付け、カタログメタデータ生成、画像品質チェックを自動化するサーバーレスワークフローです。

### このパターンが適しているケース

- 商品画像が FSx ONTAP 上に大量に蓄積されている
- Rekognition による商品画像の自動ラベル付け（カテゴリ、色、素材）を実施したい
- 構造化カタログメタデータ（product_category, color, material, style_attributes）を自動生成したい
- 画像品質メトリクス（解像度、ファイルサイズ、アスペクト比）の自動検証が必要
- 低信頼度ラベルの手動レビューフラグ管理を自動化したい

### このパターンが適さないケース

- リアルタイムの商品画像処理（API Gateway + Lambda が適切）
- 大規模な画像変換・リサイズ処理（MediaConvert / EC2 が適切）
- 既存の PIM（Product Information Management）システムとの直接統合が必要
- ONTAP REST API へのネットワーク到達性が確保できない環境

### 主な機能

- S3 AP 経由で商品画像（.jpg, .jpeg, .png, .webp）を自動検出
- Rekognition DetectLabels によるラベル検出と信頼度スコア取得
- 信頼度閾値（デフォルト: 70%）未満の場合に手動レビューフラグを設定
- Bedrock による構造化カタログメタデータ生成
- 画像品質メトリクス検証（最小解像度、ファイルサイズ範囲、アスペクト比）

## アーキテクチャ

```mermaid
graph LR
    subgraph "Step Functions ワークフロー"
        D[Discovery Lambda<br/>商品画像検出]
        IT[Image Tagging Lambda<br/>Rekognition ラベル検出]
        CM[Catalog Metadata Lambda<br/>Bedrock メタデータ生成]
        QC[Quality Check Lambda<br/>画像品質検証]
    end

    D -->|Manifest| IT
    IT -->|Labels + Confidence| CM
    CM -->|Structured Metadata| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    IT -.->|GetObject| S3AP
    IT -.->|DetectLabels| Rekog[Amazon Rekognition]
    CM -.->|InvokeModel| Bedrock[Amazon Bedrock]
    QC -.->|PutObject| S3OUT[S3 Output Bucket]
    QC -.->|Publish| SNS[SNS Topic]
```

### ワークフローステップ

1. **Discovery**: S3 AP から .jpg, .jpeg, .png, .webp ファイルを検出
2. **Image Tagging**: Rekognition でラベル検出、信頼度閾値未満は手動レビューフラグ設定
3. **Catalog Metadata**: Bedrock で構造化カタログメタデータを生成
4. **Quality Check**: 画像品質メトリクスを検証し、閾値未満の画像をフラグ

## 前提条件

- AWS アカウントと適切な IAM 権限
- FSx for NetApp ONTAP ファイルシステム（ONTAP 9.17.1P4D3 以上）
- S3 Access Point が有効化されたボリューム（商品画像を格納）
- VPC、プライベートサブネット
- Amazon Bedrock モデルアクセスが有効（Claude / Nova）

## デプロイ手順

### 1. CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file retail-catalog/template.yaml \
  --stack-name fsxn-retail-catalog \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="rate(1 hour)" \
    NotificationEmail=<your-email@example.com> \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

## 設定パラメータ一覧

| パラメータ | 説明 | デフォルト | 必須 |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx ONTAP S3 AP Alias（入力用） | — | ✅ |
| `S3AccessPointName` | S3 AP 名（ARN ベースの IAM 権限付与用。省略時は Alias ベースのみ） | `""` | ⚠️ 推奨 |
| `ScheduleExpression` | EventBridge Scheduler のスケジュール式 | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | プライベートサブネット ID リスト | — | ✅ |
| `NotificationEmail` | SNS 通知先メールアドレス | — | ✅ |
| `ConfidenceThreshold` | Rekognition ラベル信頼度閾値 (%) | `70` | |
| `MapConcurrency` | Map ステートの並列実行数 | `10` | |
| `LambdaMemorySize` | Lambda メモリサイズ (MB) | `512` | |
| `LambdaTimeout` | Lambda タイムアウト (秒) | `300` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints の有効化 | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms の有効化 | `false` | |

## クリーンアップ

```bash
aws s3 rm s3://fsxn-retail-catalog-output-${AWS_ACCOUNT_ID} --recursive

aws cloudformation delete-stack \
  --stack-name fsxn-retail-catalog \
  --region ap-northeast-1

aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-retail-catalog \
  --region ap-northeast-1
```

## 参考リンク

- [FSx ONTAP S3 Access Points 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Amazon Rekognition DetectLabels](https://docs.aws.amazon.com/rekognition/latest/dg/labels-detect-labels-image.html)
- [Amazon Bedrock API リファレンス](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html)
- [ストリーミング vs ポーリング選択ガイド](../docs/streaming-vs-polling-guide.md)

## Kinesis ストリーミングモード（Phase 3）

Phase 3 では、EventBridge ポーリングに加えて **Kinesis Data Streams によるニアリアルタイム処理** をオプトインで利用できます。

### 有効化

```bash
aws cloudformation deploy \
  --template-file retail-catalog/template.yaml \
  --stack-name fsxn-retail-catalog \
  --parameter-overrides \
    EnableStreamingMode=true \
    ... # 他のパラメータ
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
```

### ストリーミングモードのアーキテクチャ

```
EventBridge (rate(1 min)) → Stream Producer Lambda
  → DynamoDB 状態テーブルと比較 → 変更検知
  → Kinesis Data Stream → Stream Consumer Lambda
  → 既存 ImageTagging + CatalogMetadata パイプライン
```

### 主な特徴

- **変更検知**: 1 分間隔で S3 AP オブジェクト一覧と DynamoDB 状態テーブルを比較し、新規・変更・削除ファイルを検出
- **冪等処理**: DynamoDB conditional writes による重複処理防止
- **障害ハンドリング**: bisect-on-error + DynamoDB dead-letter テーブルで失敗レコードを退避
- **既存パスとの共存**: ポーリングパス（EventBridge + Step Functions）は変更なし。ハイブリッド運用が可能

### パターン選択

どちらのパターンを選択すべきかは [ストリーミング vs ポーリング選択ガイド](../docs/streaming-vs-polling-guide.md) を参照してください。

## Supported Regions

UC11 は以下のサービスを使用します:

| サービス | リージョン制約 |
|---------|-------------|
| Amazon Rekognition | ほぼ全リージョンで利用可能 |
| Amazon Bedrock | 対応リージョンを確認（[Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)） |
| Kinesis Data Streams | ほぼ全リージョンで利用可能（シャード料金はリージョンにより異なる） |
| AWS X-Ray | ほぼ全リージョンで利用可能 |
| CloudWatch EMF | ほぼ全リージョンで利用可能 |

> Kinesis ストリーミングモードを有効化する場合、シャード料金がリージョンにより異なる点に注意してください。詳細は [リージョン互換性マトリックス](../docs/region-compatibility.md) を参照。
