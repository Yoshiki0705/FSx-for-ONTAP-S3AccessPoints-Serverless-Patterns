# UC14: 保険 / 損害査定 — 事故写真損害評価・見積書 OCR・査定レポート

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **ドキュメント**: [アーキテクチャ図](docs/architecture.md) | [デモガイド](docs/demo-guide.md)

## 概要

FSx for NetApp ONTAP の S3 Access Points を活用し、事故写真の損害評価、見積書の OCR テキスト抽出、保険金請求レポートの自動生成を実現するサーバーレスワークフローです。

### このパターンが適しているケース

- 事故写真や見積書が FSx ONTAP 上に蓄積されている
- Rekognition による事故写真の損害検出（車両損害ラベル、重大度指標、影響箇所）を自動化したい
- Textract による見積書の OCR（修理項目、費用、工数、部品）を実施したい
- 写真ベース損害評価と見積書データを相関させた包括的保険金請求レポートが必要
- 損害ラベル未検出時の手動レビューフラグ管理を自動化したい

### このパターンが適さないケース

- リアルタイムの保険金請求処理システムが必要
- 完全な保険金査定エンジン（専用ソフトウェアが適切）
- 大規模な不正検知モデルのトレーニングが必要
- ONTAP REST API へのネットワーク到達性が確保できない環境

### 主な機能

- S3 AP 経由で事故写真（.jpg, .jpeg, .png）と見積書（.pdf, .tiff）を自動検出
- Rekognition による損害検出（damage_type, severity_level, affected_components）
- Bedrock による構造化損害評価生成
- Textract（クロスリージョン）による見積書 OCR（修理項目、費用、工数、部品）
- Bedrock による包括的保険金請求レポート生成（JSON + 人間可読形式）
- SNS 通知による結果の即時共有

## アーキテクチャ

```mermaid
graph LR
    subgraph "Step Functions ワークフロー"
        D[Discovery Lambda<br/>事故写真/見積書検出]
        DA[Damage Assessment Lambda<br/>Rekognition + Bedrock 損害評価]
        EO[Estimate OCR Lambda<br/>Textract 見積書抽出]
        CR[Claims Report Lambda<br/>Bedrock 請求レポート生成]
    end

    D -->|Manifest| DA
    D -->|Manifest| EO
    DA -->|Damage Assessment| CR
    EO -->|Estimate Data| CR

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    DA -.->|GetObject| S3AP
    DA -.->|DetectLabels| Rekog[Amazon Rekognition]
    DA -.->|InvokeModel| Bedrock[Amazon Bedrock]
    EO -.->|Cross-Region| Textract[Amazon Textract<br/>us-east-1]
    CR -.->|InvokeModel| Bedrock
    CR -.->|PutObject| S3OUT[S3 Output Bucket]
    CR -.->|Publish| SNS[SNS Topic]
```

### ワークフローステップ

1. **Discovery**: S3 AP から事故写真と見積書を検出
2. **Damage Assessment**: Rekognition で損害検出、Bedrock で構造化損害評価生成
3. **Estimate OCR**: Textract（クロスリージョン）で見積書からテキスト・テーブル抽出
4. **Claims Report**: Bedrock で損害評価と見積書データを相関させた包括的レポートを生成

## 前提条件

- AWS アカウントと適切な IAM 権限
- FSx for NetApp ONTAP ファイルシステム（ONTAP 9.17.1P4D3 以上）
- S3 Access Point が有効化されたボリューム（事故写真・見積書を格納）
- VPC、プライベートサブネット
- Amazon Bedrock モデルアクセスが有効（Claude / Nova）
- **クロスリージョン**: Textract は ap-northeast-1 非対応のため、us-east-1 へのクロスリージョン呼び出しが必要

## デプロイ手順

### 1. クロスリージョンパラメータの確認

Textract は東京リージョン非対応のため、`CrossRegionTarget` パラメータでクロスリージョン呼び出しを設定します。

### 2. CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file insurance-claims/template.yaml \
  --stack-name fsxn-insurance-claims \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="rate(1 hour)" \
    NotificationEmail=<your-email@example.com> \
    CrossRegionTarget=us-east-1 \
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
| `CrossRegionTarget` | Textract のターゲットリージョン | `us-east-1` | |
| `MapConcurrency` | Map ステートの並列実行数 | `10` | |
| `LambdaMemorySize` | Lambda メモリサイズ (MB) | `512` | |
| `LambdaTimeout` | Lambda タイムアウト (秒) | `300` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints の有効化 | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms の有効化 | `false` | |

## クリーンアップ

```bash
aws s3 rm s3://fsxn-insurance-claims-output-${AWS_ACCOUNT_ID} --recursive

aws cloudformation delete-stack \
  --stack-name fsxn-insurance-claims \
  --region ap-northeast-1

aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-insurance-claims \
  --region ap-northeast-1
```

## Supported Regions

UC14 は以下のサービスを使用します:

| サービス | リージョン制約 |
|---------|-------------|
| Amazon Rekognition | ほぼ全リージョンで利用可能 |
| Amazon Textract | ap-northeast-1 非対応。`TEXTRACT_REGION` パラメータで対応リージョン（us-east-1 等）を指定 |
| Amazon Bedrock | 対応リージョンを確認（[Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)） |
| AWS X-Ray | ほぼ全リージョンで利用可能 |
| CloudWatch EMF | ほぼ全リージョンで利用可能 |

> Cross-Region Client 経由で Textract API を呼び出します。データレジデンシー要件を確認してください。詳細は [リージョン互換性マトリックス](../docs/region-compatibility.md) を参照。

## 参考リンク

- [FSx ONTAP S3 Access Points 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Amazon Rekognition ラベル検出](https://docs.aws.amazon.com/rekognition/latest/dg/labels.html)
- [Amazon Textract ドキュメント](https://docs.aws.amazon.com/textract/latest/dg/what-is.html)
- [Amazon Bedrock API リファレンス](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html)
