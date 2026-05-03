# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Amazon FSx for NetApp ONTAP の S3 Access Points を活用した、業界別サーバーレス自動化パターン集です。

> **本リポジトリの位置づけ**: これは「設計判断を学ぶためのリファレンス実装」です。一部ユースケースは AWS 環境で E2E 検証済みであり、その他のユースケースも CloudFormation デプロイ、共通 Discovery Lambda、主要コンポーネントの動作確認を実施しています。PoC から本番環境への段階的な適用を想定し、コスト最適化、セキュリティ、エラーハンドリングの設計判断を具体的なコードで示すことを目的としています。

## 関連記事

本リポジトリは以下の記事の実践的なコンパニオンです:

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

記事ではアーキテクチャの設計思想とトレードオフを解説し、本リポジトリでは具体的な再利用可能な実装パターンを提供します。

## 概要

本リポジトリは、FSx for NetApp ONTAP に保存されたエンタープライズデータを **S3 Access Points** 経由でサーバーレスに処理する **5 つの業界別パターン** を提供します。

各ユースケースは独立した CloudFormation テンプレートで完結し、共通モジュール（ONTAP REST API クライアント、FSx ヘルパー、S3 AP ヘルパー）を `shared/` に配置して再利用しています。

### 主な特徴

- **ポーリングベースアーキテクチャ**: FSx ONTAP S3 AP が `GetBucketNotificationConfiguration` 非対応のため、EventBridge Scheduler + Step Functions による定期実行
- **共通モジュール分離**: OntapClient / FsxHelper / S3ApHelper を全ユースケースで再利用
- **CloudFormation ネイティブ**: 各ユースケースは独立した CloudFormation テンプレートで完結
- **セキュリティファースト**: TLS 検証デフォルト有効、最小権限 IAM、KMS 暗号化
- **コスト最適化**: 高コストの常時稼働リソース（VPC Endpoints 等）をオプショナル化

## アーキテクチャ

```mermaid
graph TB
    subgraph "スケジューリング層"
        EBS[EventBridge Scheduler<br/>cron/rate 式]
    end

    subgraph "オーケストレーション層"
        SFN[Step Functions<br/>State Machine]
    end

    subgraph "コンピュート層（VPC 内）"
        DL[Discovery Lambda<br/>オブジェクト検出]
        PL[Processing Lambda<br/>AI/ML 処理]
        RL[Report Lambda<br/>レポート生成・通知]
    end

    subgraph "データソース"
        FSXN[FSx ONTAP Volume]
        S3AP[S3 Access Point]
        ONTAP_API[ONTAP REST API]
    end

    subgraph "AWS サービス"
        SM[Secrets Manager]
        S3OUT[S3 Output Bucket<br/>SSE-KMS 暗号化]
        BEDROCK[Amazon Bedrock]
        TEXTRACT[Amazon Textract]
        COMPREHEND[Amazon Comprehend]
        REKOGNITION[Amazon Rekognition]
        ATHENA[Amazon Athena]
        SNS[SNS Topic]
    end

    subgraph "VPC Endpoints（オプショナル）"
        VPCE_S3[S3 Gateway EP<br/>無料]
        VPCE_IF[Interface EPs<br/>Secrets Manager / FSx /<br/>CloudWatch / SNS]
    end

    EBS -->|Trigger| SFN
    SFN -->|Step 1| DL
    SFN -->|Step 2 Map| PL
    SFN -->|Step 3| RL

    DL -->|ListObjectsV2| S3AP
    DL -->|REST API| ONTAP_API
    PL -->|GetObject| S3AP
    PL -->|PutObject| S3OUT

    S3AP -.->|Exposes| FSXN

    DL --> VPCE_S3
    DL --> VPCE_IF --> SM
    RL --> SNS
```

### ワークフロー概要

```
EventBridge Scheduler (定期実行)
  └─→ Step Functions State Machine
       ├─→ Discovery Lambda: S3 AP からオブジェクト一覧取得 → Manifest 生成
       ├─→ Map State (並列処理): 各オブジェクトを AI/ML サービスで処理
       └─→ Report/Notification: 結果レポート生成 → SNS 通知
```

## ユースケース一覧

| # | ディレクトリ | 業界 | パターン | 使用 AI/ML サービス | ap-northeast-1 検証 |
|---|-------------|------|---------|-------------------|-------------------|
| UC1 | `legal-compliance/` | 法務・コンプライアンス | ファイルサーバー監査・データガバナンス | Athena, Bedrock | ✅ E2E 成功 |
| UC2 | `financial-idp/` | 金融・保険 | 契約書・請求書の自動処理 (IDP) | Textract ⚠️, Comprehend, Bedrock | ⚠️ Textract 非対応 |
| UC3 | `manufacturing-analytics/` | 製造業 | IoT センサーログ・品質検査画像の分析 | Athena, Rekognition | ✅ E2E 成功 |
| UC4 | `media-vfx/` | メディア | VFX レンダリングパイプライン | Rekognition, Deadline Cloud | ⚠️ Deadline Cloud 要設定 |
| UC5 | `healthcare-dicom/` | 医療 | DICOM 画像の自動分類・匿名化 | Rekognition, Comprehend Medical ⚠️ | ⚠️ Comprehend Medical 非対応 |

> **リージョン制約**: Amazon Textract と Amazon Comprehend Medical は ap-northeast-1（東京）で利用できません。UC2 は us-east-1 等の対応リージョンでのデプロイを推奨します。UC5 の Comprehend Medical も同様です。Rekognition, Comprehend, Bedrock, Athena は ap-northeast-1 で利用可能です。
> 
> 参考: [Textract 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/textract.html) | [Comprehend Medical 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html)

### スクリーンショット

> 以下は検証環境での撮影例です。環境固有情報（アカウント ID 等）はマスク処理済みです。

#### 全 5 UC の Step Functions ワークフロー

![Step Functions 全ワークフロー](docs/screenshots/masked/step-functions-all-succeeded.png)

#### AI/ML サービス画面

##### Amazon Bedrock — モデルカタログ

![Bedrock モデルカタログ](docs/screenshots/masked/bedrock-model-catalog.png)

##### Amazon Rekognition — ラベル検出

![Rekognition ラベル検出](docs/screenshots/masked/rekognition-label-detection.png)

##### Amazon Comprehend — エンティティ検出

![Comprehend コンソール](docs/screenshots/masked/comprehend-console.png)

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| 言語 | Python 3.12 |
| IaC | CloudFormation (YAML) |
| コンピュート | AWS Lambda (VPC 内) |
| オーケストレーション | AWS Step Functions |
| スケジューリング | Amazon EventBridge Scheduler |
| ストレージ | FSx for ONTAP (S3 AP) + S3 出力バケット (SSE-KMS) |
| 通知 | Amazon SNS |
| 分析 | Amazon Athena + AWS Glue Data Catalog |
| AI/ML | Amazon Bedrock, Textract, Comprehend, Rekognition |
| セキュリティ | Secrets Manager, KMS, IAM 最小権限 |
| テスト | pytest + Hypothesis (PBT), moto, cfn-lint, ruff |

## 前提条件

- **AWS アカウント**: 有効な AWS アカウントと適切な IAM 権限
- **FSx for NetApp ONTAP**: デプロイ済みのファイルシステム
  - ONTAP バージョン: S3 Access Points をサポートするバージョン（9.17.1P4D3 で検証済み）
  - S3 Access Point が有効化されたボリューム（network origin: `internet` 推奨）
- **ネットワーク**: VPC、プライベートサブネット、ルートテーブル
- **Secrets Manager**: ONTAP REST API 認証情報（`{"username":"fsxadmin","password":"..."}` 形式）を事前登録
- **S3 バケット**: Lambda デプロイパッケージ格納用バケットを事前作成（例: `fsxn-s3ap-deploy-<account-id>`）
- **Python 3.12+**: ローカル開発・テスト用
- **AWS CLI v2**: デプロイ・管理用

### 事前準備コマンド

```bash
# 1. デプロイ用 S3 バケット作成
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb "s3://fsxn-s3ap-deploy-${ACCOUNT_ID}" --region $AWS_DEFAULT_REGION

# 2. ONTAP 認証情報を Secrets Manager に登録
aws secretsmanager create-secret \
  --name fsxn-ontap-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-ontap-password>"}' \
  --region $AWS_DEFAULT_REGION

# 3. 既存の S3 Gateway Endpoint を確認（重複作成を防ぐ）
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" "Name=service-name,Values=com.amazonaws.${AWS_DEFAULT_REGION}.s3" \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,State:State}' \
  --output table
# → 結果がある場合は EnableS3GatewayEndpoint=false でデプロイ
```

### VPC 内 Lambda から S3 AP にアクセスする場合の注意事項

> **UC1 デプロイ検証（2026-05-03）で確認された重要事項**

- **S3 Gateway Endpoint のルートテーブル関連付けが必須**: `RouteTableIds` にプライベートサブネットのルートテーブル ID を指定しないと、VPC 内 Lambda から S3 / S3 AP へのアクセスがタイムアウトする
- **VPC DNS 解決の確認**: VPC の `enableDnsSupport` / `enableDnsHostnames` が有効であること
- **PoC / デモ環境では Lambda を VPC 外で実行することを推奨**: S3 AP の network origin が `internet` であれば VPC 外 Lambda から問題なくアクセス可能。VPC Endpoint 不要でコスト削減・設定簡素化が可能
- 詳細は [トラブルシューティングガイド](docs/guides/troubleshooting-guide.md#6-lambda-vpc-内実行時の-s3-ap-タイムアウト) を参照

### 必要な AWS サービスクォータ

| サービス | クォータ | 推奨値 |
|---------|---------|-------|
| Lambda 同時実行数 | ConcurrentExecutions | 100 以上 |
| Step Functions 実行数 | StartExecution/秒 | デフォルト (25) |
| S3 Access Point | アカウントあたりの AP 数 | デフォルト (10,000) |

## クイックスタート

### 1. リポジトリのクローン

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
```

### 2. 依存関係のインストール

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. テストの実行

```bash
# ユニットテスト（カバレッジ付き）
pytest shared/tests/ --cov=shared --cov-report=term-missing -v

# プロパティベーステスト
pytest shared/tests/test_properties.py -v

# リンター
ruff check .
ruff format --check .
```

### 4. ユースケースのデプロイ（例: UC1 法務・コンプライアンス）

> ⚠️ **既存環境への影響に関する重要事項**
>
> デプロイ前に以下を確認してください：
>
> | パラメータ | 既存環境への影響 | 確認方法 |
> |-----------|----------------|---------|
> | `VpcId` / `PrivateSubnetIds` | 指定した VPC/サブネットに Lambda ENI が作成される | `aws ec2 describe-network-interfaces --filters Name=group-id,Values=<sg-id>` |
> | `EnableS3GatewayEndpoint=true` | VPC に S3 Gateway Endpoint が追加される。**同一 VPC に既存の S3 Gateway Endpoint がある場合は `false` に設定** | `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc-id>` |
> | `PrivateRouteTableIds` | S3 Gateway Endpoint がルートテーブルに関連付けられる。既存のルーティングには影響なし | `aws ec2 describe-route-tables --route-table-ids <rtb-id>` |
> | `ScheduleExpression` | EventBridge Scheduler が定期的に Step Functions を実行する。**不要な実行を避けるためデプロイ後にスケジュールを無効化可能** | AWS コンソール → EventBridge → Schedules |
> | `NotificationEmail` | SNS サブスクリプション確認メールが送信される | メール受信確認 |
>
> **スタック削除時の注意**:
> - S3 バケット（Athena Results）にオブジェクトが残っている場合、削除が失敗します。事前に `aws s3 rm s3://<bucket> --recursive` で空にしてください
> - バージョニング有効バケットは `aws s3api delete-objects` で全バージョンを削除する必要があります
> - VPC Endpoints の削除に 5-15 分かかる場合があります
> - Lambda の ENI 解放に時間がかかり、セキュリティグループの削除が失敗する場合があります。数分待って再試行してください

```bash
# リージョンを設定（環境変数で管理）
export AWS_DEFAULT_REGION=us-east-1  # 全サービス対応リージョン推奨

# Lambda パッケージング
./scripts/deploy_uc.sh legal-compliance package

# CloudFormation デプロイ
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-volume-ext-s3alias> \
    ParameterKey=S3AccessPointOutputAlias,ParameterValue=<your-output-volume-ext-s3alias> \
    ParameterKey=OntapSecretName,ParameterValue=<your-ontap-secret-name> \
    ParameterKey=OntapManagementIp,ParameterValue=<your-ontap-management-ip> \
    ParameterKey=SvmUuid,ParameterValue=<your-svm-uuid> \
    ParameterKey=VolumeUuid,ParameterValue=<your-volume-uuid> \
    ParameterKey=VpcId,ParameterValue=<your-vpc-id> \
    'ParameterKey=PrivateSubnetIds,ParameterValue=<subnet-1>,<subnet-2>' \
    'ParameterKey=PrivateRouteTableIds,ParameterValue=<rtb-1>,<rtb-2>' \
    ParameterKey=NotificationEmail,ParameterValue=<your-email@example.com> \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true
```

> **注意**: `<...>` のプレースホルダーを実際の環境値に置き換えてください。
> 
> **リージョン選択**: 全 AI/ML サービスが利用可能な `us-east-1` または `us-west-2` を推奨します。`ap-northeast-1` では Textract と Comprehend Medical が利用できません（クロスリージョン呼び出しで対応可能）。詳細は [リージョン互換性マトリックス](docs/region-compatibility.md) を参照。

### 検証済み環境

| 項目 | 値 |
|------|-----|
| AWS リージョン | ap-northeast-1 (東京) |
| FSx ONTAP バージョン | ONTAP 9.17.1P4D3 |
| FSx 構成 | SINGLE_AZ_1 |
| Python | 3.12 |
| デプロイ方式 | CloudFormation (標準) |

全 5 ユースケースの CloudFormation スタックデプロイと Discovery Lambda の動作確認を実施済みです。
詳細は [検証結果記録](docs/verification-results.md) を参照してください。

## コスト構造サマリー

### 環境別コスト概算

| 環境 | 固定費/月 | 変動費/月 | 合計/月 |
|------|----------|----------|--------|
| デモ/PoC | ~$0 | ~$1〜$3 | **~$1〜$3** |
| 本番（1 UC） | ~$29 | ~$1〜$3 | **~$30〜$32** |
| 本番（全 5 UC） | ~$29 | ~$5〜$15 | **~$34〜$44** |

### コスト分類

- **リクエストベース（従量課金）**: Lambda, Step Functions, S3 API, Textract, Comprehend, Rekognition, Bedrock, Athena — 使わなければ $0
- **常時稼働（固定費）**: Interface VPC Endpoints (~$28.80/月) — **オプショナル（opt-in）**

> 詳細なコスト分析は [docs/cost-analysis.md](docs/cost-analysis.md) を参照してください。

### オプショナルリソース

高コストの常時稼働リソースは CloudFormation パラメータでオプショナル化しています。

| リソース | パラメータ | デフォルト | 月額固定費 | 説明 |
|---------|-----------|----------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints` | `false` | ~$28.80 | Secrets Manager, FSx, CloudWatch, SNS 用。本番環境では `true` 推奨 |
| CloudWatch Alarms | `EnableCloudWatchAlarms` | `false` | ~$0.10/アラーム | Step Functions 失敗率、Lambda エラー率の監視 |

> **S3 Gateway VPC Endpoint** は追加の時間課金がないため、VPC 内 Lambda から S3 AP にアクセスする構成では有効化を推奨します。ただし、既存の S3 Gateway Endpoint がある場合や、PoC / デモ用途で Lambda を VPC 外に配置する場合は `EnableS3GatewayEndpoint=false` を指定してください。

## セキュリティと認可モデル

本ソリューションは **複数の認可レイヤー** を組み合わせ、それぞれが異なる役割を担います:

| レイヤー | 役割 | 制御対象 |
|---------|------|---------|
| **IAM** | AWS サービスと S3 Access Points へのアクセス制御 | Lambda 実行ロール、S3 AP ポリシー |
| **S3 Access Point** | S3 AP に関連付けられたファイルシステムユーザーを通じてアクセス境界を定義 | S3 AP ポリシー、network origin、関連付けユーザー |
| **ONTAP ファイルシステム** | ファイルレベルの権限を強制 | UNIX パーミッション / NTFS ACL |
| **ONTAP REST API** | メタデータとコントロールプレーン操作のみ公開 | Secrets Manager 認証 + TLS |

**重要な設計上の注意点**:

- S3 API はファイルレベルの ACL を公開しません。ファイル権限情報は **ONTAP REST API 経由でのみ** 取得可能です（UC1 の ACL Collection がこのパターン）
- S3 AP 経由のアクセスは、IAM / S3 AP ポリシーで許可された後、S3 AP に関連付けられた UNIX / Windows ファイルシステムユーザーとして ONTAP 側で認可されます
- ONTAP REST API の認証情報は Secrets Manager で管理し、Lambda 環境変数には格納しません

## 互換性マトリックス

| 項目 | サポート値 |
|------|----------|
| ONTAP バージョン | 9.17.1P4D3 で検証済み（S3 Access Points をサポートするバージョンが必要） |
| 検証済みリージョン | ap-northeast-1（東京） |
| 推奨リージョン | us-east-1 / us-west-2（全 AI/ML サービス利用時） |
| Python バージョン | 3.12+ |
| CloudFormation Transform | AWS::Serverless-2016-10-31 |
| S3 AP セキュリティスタイル | UNIX (root), NTFS |

### FSx ONTAP S3 Access Points 対応 API

S3 AP 経由で利用可能な API サブセット:

| API | サポート |
|-----|---------|
| ListObjectsV2 | ✅ |
| GetObject | ✅ |
| PutObject | ✅ (最大 5 GB) |
| HeadObject | ✅ |
| DeleteObject | ✅ |
| DeleteObjects | ✅ |
| CopyObject | ✅ (同一 AP 内、同一リージョン) |
| GetObjectAttributes | ✅ |
| GetObjectTagging / PutObjectTagging | ✅ |
| CreateMultipartUpload | ✅ |
| UploadPart / UploadPartCopy | ✅ |
| CompleteMultipartUpload | ✅ |
| AbortMultipartUpload | ✅ |
| ListParts / ListMultipartUploads | ✅ |
| HeadBucket / GetBucketLocation | ✅ |
| GetBucketNotificationConfiguration | ❌（非対応 → ポーリング設計の理由） |
| Presign | ❌ |

### S3 Access Point ネットワークオリジンの制約

| ネットワークオリジン | Lambda (VPC 外) | Lambda (VPC 内) | Athena / Glue | 推奨 UC |
|-------------------|----------------|----------------|--------------|---------|
| **internet** | ✅ | ✅ (S3 Gateway EP 経由) | ✅ | UC1, UC3 (Athena 使用) |
| **VPC** | ❌ | ✅ (S3 Gateway EP 必須) | ❌ | UC2, UC4, UC5 (Athena 不使用) |

> **重要**: Athena / Glue は AWS マネージドインフラからアクセスするため、VPC origin の S3 AP にはアクセスできません。UC1（法務）と UC3（製造業）は Athena を使用するため、S3 AP は **internet** network origin で作成する必要があります。

### S3 AP の制約事項

- **PutObject 最大サイズ**: 5 GB（5 GB 超はマルチパートアップロードを使用）
- **暗号化**: SSE-FSX のみ（FSx が透過的に処理、ServerSideEncryption パラメータ指定不要）
- **ACL**: `bucket-owner-full-control` のみサポート
- **非対応機能**: Object Versioning, Object Lock, Object Lifecycle, Static Website Hosting, Requester Pays, Presigned URL

## ドキュメント

詳細なガイドとスクリーンショットは `docs/` ディレクトリに格納されています。

| ドキュメント | 説明 |
|------------|------|
| [docs/guides/deployment-guide.md](docs/guides/deployment-guide.md) | デプロイ手順書（前提条件確認 → パラメータ準備 → デプロイ → 動作確認） |
| [docs/guides/operations-guide.md](docs/guides/operations-guide.md) | 運用手順書（スケジュール変更、手動実行、ログ確認、アラーム対応） |
| [docs/guides/troubleshooting-guide.md](docs/guides/troubleshooting-guide.md) | トラブルシューティング（AccessDenied, VPC Endpoint, ONTAP タイムアウト, Athena） |
| [docs/cost-analysis.md](docs/cost-analysis.md) | コスト構造分析 |
| [docs/references.md](docs/references.md) | 参考リンク集 |
| [docs/extension-patterns.md](docs/extension-patterns.md) | 拡張パターンガイド |
| [docs/article-draft.md](docs/article-draft.md) | dev.to 記事ドラフト |
| [docs/verification-results.md](docs/verification-results.md) | AWS 環境検証結果記録 |
| [docs/screenshots/](docs/screenshots/README.md) | AWS コンソールスクリーンショット（検証後に追加） |

## ディレクトリ構造

```
fsxn-s3ap-serverless-patterns/
├── README.md                          # 本ファイル
├── LICENSE                            # MIT License
├── requirements.txt                   # 本番依存関係
├── requirements-dev.txt               # 開発依存関係
├── shared/                            # 共通モジュール
│   ├── __init__.py
│   ├── ontap_client.py               # ONTAP REST API クライアント
│   ├── fsx_helper.py                 # AWS FSx API ヘルパー
│   ├── s3ap_helper.py                # S3 Access Point ヘルパー
│   ├── exceptions.py                 # 共通例外・エラーハンドラ
│   ├── discovery_handler.py          # 共通 Discovery Lambda テンプレート
│   ├── cfn/                          # CloudFormation スニペット
│   └── tests/                        # ユニットテスト・プロパティテスト
├── legal-compliance/                  # UC1: 法務・コンプライアンス
├── financial-idp/                     # UC2: 金融・保険
├── manufacturing-analytics/           # UC3: 製造業
├── media-vfx/                         # UC4: メディア
├── healthcare-dicom/                  # UC5: 医療
├── scripts/                           # 検証・デプロイスクリプト
│   ├── deploy_uc.sh                  # UC デプロイスクリプト（汎用）
│   ├── verify_shared_modules.py      # 共通モジュール AWS 環境検証
│   └── verify_cfn_templates.sh       # CloudFormation テンプレート検証
├── .github/workflows/                 # CI/CD (lint, test)
└── docs/                              # ドキュメント
    ├── guides/                        # 操作手順書
    │   ├── deployment-guide.md       # デプロイ手順
    │   ├── operations-guide.md       # 運用手順
    │   └── troubleshooting-guide.md  # トラブルシューティング
    ├── screenshots/                   # AWS コンソールスクリーンショット
    ├── cost-analysis.md               # コスト構造分析
    ├── references.md                  # 参考リンク集
    ├── extension-patterns.md          # 拡張パターンガイド
    ├── verification-results.md        # 検証結果記録
    └── article-draft.md               # dev.to 記事ドラフト
```

## 共通モジュール (shared/)

| モジュール | 説明 |
|-----------|------|
| `ontap_client.py` | ONTAP REST API クライアント（Secrets Manager 認証、urllib3、TLS、リトライ） |
| `fsx_helper.py` | AWS FSx API + CloudWatch メトリクス取得 |
| `s3ap_helper.py` | S3 Access Point ヘルパー（ページネーション、サフィックスフィルタ） |
| `exceptions.py` | 共通例外クラス、`lambda_error_handler` デコレータ |
| `discovery_handler.py` | 共通 Discovery Lambda テンプレート（Manifest 生成） |

## 開発

### テスト実行

```bash
# 全テスト
pytest shared/tests/ -v

# カバレッジ付き
pytest shared/tests/ --cov=shared --cov-report=term-missing --cov-fail-under=80 -v

# プロパティベーステストのみ
pytest shared/tests/test_properties.py -v
```

### リンター

```bash
# Python リンター
ruff check .
ruff format --check .

# CloudFormation テンプレート検証
cfn-lint */template.yaml */template-deploy.yaml
```

## このパターン集を使うべきケース / 使うべきでないケース

### 使うべきケース

- FSx for ONTAP 上の既存 NAS データを移動せずにサーバーレス処理したい
- Lambda から NFS / SMB マウントせずにファイル一覧取得や前処理を行いたい
- S3 Access Points と ONTAP REST API の責務分離を学びたい
- 業界別の AI / ML 処理パターンを PoC として素早く検証したい
- EventBridge Scheduler + Step Functions によるポーリングベース設計が許容される

### 使うべきでないケース

- リアルタイムのファイル変更イベント処理が必須（S3 Event Notification 非対応）
- Presigned URL など、完全な S3 バケット互換性が必要
- 既に EC2 / ECS ベースの常時稼働バッチ基盤があり、NFS マウント運用が許容される
- ファイルデータが既に S3 標準バケットに存在し、S3 イベント通知で処理可能

## 本番適用時の追加検討事項

本リポジトリは本番適用を見据えた設計判断を含みますが、実際の本番環境では以下を追加で検討してください。

- 組織の IAM / SCP / Permission Boundary との整合
- S3 AP ポリシーと ONTAP 側ユーザー権限のレビュー
- Lambda / Step Functions / Bedrock / Textract 等の CloudTrail 監査ログ有効化
- CloudWatch Alarms / SNS / Incident Management 連携（`EnableCloudWatchAlarms=true`）
- データ分類、個人情報、医療情報など業界固有のコンプライアンス要件
- リージョン制約とクロスリージョン呼び出し時のデータレジデンシー確認
- Step Functions の実行履歴保持期間とログレベル設定
- Lambda の Reserved Concurrency / Provisioned Concurrency 設定

## コントリビューション

Issue や Pull Request を歓迎します。詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照してください。
