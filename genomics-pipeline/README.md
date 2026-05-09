# UC7: ゲノミクス / バイオインフォマティクス — 品質チェック・バリアントコール集計

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **ドキュメント**: [アーキテクチャ図](docs/architecture.md) | [デモガイド](docs/demo-guide.md)

## 概要

FSx for NetApp ONTAP の S3 Access Points を活用し、FASTQ/BAM/VCF ゲノムデータの品質チェック、バリアントコール統計集計、研究サマリー生成を自動化するサーバーレスワークフローです。

### このパターンが適しているケース

- 次世代シーケンサーの出力データ（FASTQ/BAM/VCF）が FSx ONTAP 上に蓄積されている
- シーケンスデータの品質メトリクス（リード数、品質スコア、GC 含量）を定期的に監視したい
- バリアントコール結果の統計集計（SNP/InDel 比率、Ti/Tv 比）を自動化したい
- Comprehend Medical によるバイオメディカルエンティティ（遺伝子名、疾患、薬剤）の自動抽出が必要
- 研究サマリーレポートを自動生成したい

### このパターンが適さないケース

- リアルタイムのバリアントコーリングパイプライン（BWA/GATK 等）の実行が必要
- 大規模ゲノムアライメント処理（EC2/HPC クラスタが適切）
- GxP 規制下で完全なバリデーション済みパイプラインが必要
- ONTAP REST API へのネットワーク到達性が確保できない環境

### 主な機能

- S3 AP 経由で FASTQ/BAM/VCF ファイルを自動検出
- ストリーミングダウンロードによる FASTQ 品質メトリクス抽出
- VCF バリアント統計集計（total_variants, snp_count, indel_count, ti_tv_ratio）
- Athena SQL による品質閾値未満サンプルの特定
- Comprehend Medical（クロスリージョン）によるバイオメディカルエンティティ抽出
- Amazon Bedrock による研究サマリー生成

## アーキテクチャ

```mermaid
graph LR
    subgraph "Step Functions ワークフロー"
        D[Discovery Lambda<br/>FASTQ/BAM/VCF 検出]
        QC[QC Lambda<br/>品質メトリクス抽出]
        VA[Variant Aggregation Lambda<br/>バリアント統計集計]
        ATH[Athena Analysis Lambda<br/>品質閾値分析]
        SUM[Summary Lambda<br/>Bedrock + Comprehend Medical]
    end

    D -->|Manifest| QC
    QC -->|QC Metrics| VA
    VA -->|Variant Stats| ATH
    ATH -->|Analysis Results| SUM

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    QC -.->|Streaming Download| S3AP
    ATH -.->|SQL Query| Athena[Amazon Athena]
    SUM -.->|InvokeModel| Bedrock[Amazon Bedrock]
    SUM -.->|Cross-Region| CM[Comprehend Medical<br/>us-east-1]
    SUM -.->|Publish| SNS[SNS Topic]
```

### ワークフローステップ

1. **Discovery**: S3 AP から .fastq, .fastq.gz, .bam, .vcf, .vcf.gz ファイルを検出
2. **QC**: ストリーミングダウンロードで FASTQ ヘッダーを取得し、品質メトリクスを抽出
3. **Variant Aggregation**: VCF ファイルのバリアント統計を集計
4. **Athena Analysis**: 品質閾値未満サンプルを SQL で特定
5. **Summary**: Bedrock で研究サマリー生成、Comprehend Medical でエンティティ抽出

## 前提条件

- AWS アカウントと適切な IAM 権限
- FSx for NetApp ONTAP ファイルシステム（ONTAP 9.17.1P4D3 以上）
- S3 Access Point が有効化されたボリューム（ゲノムデータを格納）
- VPC、プライベートサブネット
- Amazon Bedrock モデルアクセスが有効（Claude / Nova）
- **クロスリージョン**: Comprehend Medical は ap-northeast-1 非対応のため、us-east-1 へのクロスリージョン呼び出しが必要

## デプロイ手順

### 1. クロスリージョンパラメータの確認

Comprehend Medical は東京リージョン非対応のため、`CrossRegionServices` パラメータでクロスリージョン呼び出しを設定します。

### 2. CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file genomics-pipeline/template.yaml \
  --stack-name fsxn-genomics-pipeline \
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

### 3. クロスリージョン設定の確認

デプロイ後、Lambda 環境変数 `CROSS_REGION_TARGET` が `us-east-1` に設定されていることを確認してください。

## 設定パラメータ一覧

| パラメータ | 説明 | デフォルト | 必須 |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx ONTAP S3 AP Alias（入力用） | — | ✅ |
| `S3AccessPointName` | S3 AP 名（ARN ベースの IAM 権限付与用。省略時は Alias ベースのみ） | `""` | ⚠️ 推奨 |
| `ScheduleExpression` | EventBridge Scheduler のスケジュール式 | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | プライベートサブネット ID リスト | — | ✅ |
| `NotificationEmail` | SNS 通知先メールアドレス | — | ✅ |
| `CrossRegionTarget` | Comprehend Medical のターゲットリージョン | `us-east-1` | |
| `MapConcurrency` | Map ステートの並列実行数 | `10` | |
| `LambdaMemorySize` | Lambda メモリサイズ (MB) | `1024` | |
| `LambdaTimeout` | Lambda タイムアウト (秒) | `300` | |
| `EnableVpcEndpoints` | Interface VPC Endpoints の有効化 | `false` | |
| `EnableCloudWatchAlarms` | CloudWatch Alarms の有効化 | `false` | |

## クリーンアップ

```bash
# S3 バケットを空にする
aws s3 rm s3://fsxn-genomics-pipeline-output-${AWS_ACCOUNT_ID} --recursive

# CloudFormation スタックの削除
aws cloudformation delete-stack \
  --stack-name fsxn-genomics-pipeline \
  --region ap-northeast-1

aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-genomics-pipeline \
  --region ap-northeast-1
```

## Supported Regions

UC7 は以下のサービスを使用します:

| サービス | リージョン制約 |
|---------|-------------|
| Amazon Athena | ほぼ全リージョンで利用可能 |
| Amazon Bedrock | 対応リージョンを確認（[Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)） |
| Amazon Comprehend Medical | 限定リージョンのみ対応。`COMPREHEND_MEDICAL_REGION` パラメータで対応リージョン（us-east-1 等）を指定 |
| AWS X-Ray | ほぼ全リージョンで利用可能 |
| CloudWatch EMF | ほぼ全リージョンで利用可能 |

> Cross-Region Client 経由で Comprehend Medical API を呼び出します。データレジデンシー要件を確認してください。詳細は [リージョン互換性マトリックス](../docs/region-compatibility.md) を参照。

## 参考リンク

- [FSx ONTAP S3 Access Points 概要](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Amazon Comprehend Medical](https://docs.aws.amazon.com/comprehend-medical/latest/dev/what-is.html)
- [FASTQ フォーマット仕様](https://en.wikipedia.org/wiki/FASTQ_format)
- [VCF フォーマット仕様](https://samtools.github.io/hts-specs/VCFv4.3.pdf)
