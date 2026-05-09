# SAM CLI ローカルテストガイド

## 概要

本ガイドでは、SAM CLI を使用して Lambda 関数をローカル環境でテストする方法を説明します。ローカルテストにより、AWS にデプロイせずに Lambda 関数の動作を検証できます。

## 前提条件

### 必須ソフトウェア

| ソフトウェア | バージョン | 用途 |
|-------------|-----------|------|
| SAM CLI | v1.93.0+ | Lambda ローカル実行 |
| Docker or Finch | 最新版 | コンテナランタイム |
| Python | 3.13+ | Lambda ランタイム |
| AWS CLI | v2 | 認証情報管理 |

### インストール

```bash
# SAM CLI (macOS)
brew install aws-sam-cli

# SAM CLI (pip)
pip install aws-sam-cli

# バージョン確認
sam --version
# SAM CLI, version 1.93.0+
```

### Finch のインストール（Docker 代替）

Finch は AWS が提供する Docker 互換のコンテナランタイムです。Docker Desktop のライセンスが不要です。

```bash
# macOS
brew install --cask finch

# 初期化
finch vm init
finch vm start

# SAM CLI が Finch を使用するよう設定
export DOCKER_HOST=unix://$HOME/.finch/finch.sock
```

SAM CLI v1.93.0+ では Finch が自動検出されます。

## クイックスタート

### 1. 単一 UC のテスト

```bash
# UC01: 法務・コンプライアンス の Discovery Lambda をテスト
sam local invoke \
  --template legal-compliance/template-deploy.yaml \
  --event events/uc01-legal-compliance/discovery-event.json \
  --env-vars events/env.json \
  --region ap-northeast-1 \
  DiscoveryFunction
```

### 2. 一括テストスクリプト

```bash
# 全 UC の Discovery Lambda をテスト
./scripts/local-test.sh

# 特定の UC のみテスト
./scripts/local-test.sh 01    # UC01
./scripts/local-test.sh 06    # UC06
```

## sam local invoke の使い方

### 基本構文

```bash
sam local invoke \
  --template <テンプレートパス> \
  --event <イベントJSONパス> \
  --env-vars <環境変数JSONパス> \
  --region <リージョン> \
  <論理リソース名>
```

### パラメータ説明

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| `--template` | CloudFormation テンプレートのパス | `legal-compliance/template-deploy.yaml` |
| `--event` | Lambda に渡すイベント JSON | `events/uc01-legal-compliance/discovery-event.json` |
| `--env-vars` | 環境変数の JSON ファイル | `events/env.json` |
| `--region` | AWS リージョン | `ap-northeast-1` |
| `--skip-pull-image` | Docker イメージのプルをスキップ | - |
| `--debug-port` | デバッガ接続ポート | `5678` |
| `--docker-network` | Docker ネットワーク名 | `sam-local-network` |

### 各 UC の Lambda 関数名

| UC | Discovery | その他の関数 |
|----|-----------|-------------|
| UC01 | `DiscoveryFunction` | `AclCollectionFunction`, `AthenaAnalysisFunction`, `ReportGenerationFunction` |
| UC02 | `DiscoveryFunction` | `OcrFunction`, `EntityExtractionFunction`, `SummaryFunction` |
| UC03 | `DiscoveryFunction` | `TransformFunction`, `AthenaAnalysisFunction`, `AnomalyDetectionFunction` |
| UC04 | `DiscoveryFunction` | `JobSubmitFunction`, `QualityCheckFunction` |
| UC05 | `DiscoveryFunction` | `DicomParseFunction`, `PiiDetectionFunction`, `AnonymizationFunction` |
| UC06 | `DiscoveryFunction` | `MetadataExtractionFunction`, `DrcAggregationFunction`, `ReportGenerationFunction` |
| UC07 | `DiscoveryFunction` | `QcFunction`, `VariantAggregationFunction`, `AthenaAnalysisFunction`, `SummaryFunction` |
| UC08 | `DiscoveryFunction` | `SeismicParseFunction`, `QcFunction`, `VisualizationFunction` |
| UC09 | `DiscoveryFunction` | `FrameExtractionFunction`, `PointCloudQcFunction`, `AnnotationManagerFunction` |
| UC10 | `DiscoveryFunction` | `BimParseFunction`, `OcrFunction`, `SafetyCheckFunction` |
| UC11 | `DiscoveryFunction` | `ImageTaggingFunction`, `CatalogMetadataFunction`, `QualityCheckFunction` |
| UC12 | `DiscoveryFunction` | `OcrFunction`, `DataStructuringFunction`, `InventoryAnalysisFunction`, `ReportFunction` |
| UC13 | `DiscoveryFunction` | `MetadataExtractionFunction`, `PlagiarismCheckFunction`, `CitationAnalysisFunction` |
| UC14 | `DiscoveryFunction` | `DamageAssessmentFunction`, `EstimateOcrFunction`, `ClaimsReportFunction` |

## sam local start-lambda の使い方

`sam local start-lambda` は Lambda 関数をローカルの HTTP エンドポイントとして起動します。Step Functions のローカルテストや、他のサービスからの呼び出しをシミュレートする際に便利です。

### 起動

```bash
sam local start-lambda \
  --template legal-compliance/template-deploy.yaml \
  --env-vars events/env.json \
  --region ap-northeast-1 \
  --host 127.0.0.1 \
  --port 3001
```

### 呼び出し

```bash
# AWS CLI で呼び出し（エンドポイントをローカルに向ける）
aws lambda invoke \
  --function-name DiscoveryFunction \
  --endpoint-url http://127.0.0.1:3001 \
  --payload file://events/uc01-legal-compliance/discovery-event.json \
  output.json

cat output.json
```

### Step Functions Local との連携

```bash
# Step Functions Local を起動（別ターミナル）
docker run -p 8083:8083 \
  -e AWS_DEFAULT_REGION=ap-northeast-1 \
  -e LAMBDA_ENDPOINT=http://host.docker.internal:3001 \
  amazon/aws-stepfunctions-local

# State Machine を作成
aws stepfunctions create-state-machine \
  --endpoint-url http://localhost:8083 \
  --name "local-test" \
  --role-arn "arn:aws:iam::123456789012:role/dummy" \
  --definition file://state-machine-definition.json

# 実行
aws stepfunctions start-execution \
  --endpoint-url http://localhost:8083 \
  --state-machine-arn "arn:aws:states:ap-northeast-1:123456789012:stateMachine:local-test" \
  --input '{}'
```

## 環境変数の設定

### env.json の構造

```json
{
  "DiscoveryFunction": {
    "S3_ACCESS_POINT": "your-volume-name-xxxxx-ext-s3alias",
    "ONTAP_SECRET_NAME": "fsxn-ontap-credentials",
    "ONTAP_MANAGEMENT_IP": "10.0.0.1",
    "SVM_UUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "VERIFY_SSL": "false",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
    "LOG_LEVEL": "DEBUG"
  }
}
```

### 環境変数の優先順位

1. `--env-vars` で指定した JSON ファイル（最優先）
2. テンプレートの `Environment.Variables`
3. シェルの環境変数

## Finch 対応ガイダンス

### Finch とは

Finch は AWS が開発したオープンソースのコンテナ開発ツールです。Docker Desktop の代替として使用でき、Docker Desktop のライセンス費用が不要です。

### SAM CLI + Finch の設定

```bash
# 1. Finch のインストールと起動
brew install --cask finch
finch vm init
finch vm start

# 2. 環境変数の設定
export DOCKER_HOST=unix://$HOME/.finch/finch.sock

# 3. SAM CLI の接続タイムアウト設定（推奨）
export SAM_CLI_CONTAINER_CONNECTION_TIMEOUT=30

# 4. 動作確認
sam local invoke --help
```

### Finch 使用時の注意事項

1. **初回起動が遅い**: Finch VM の起動に 30–60 秒かかる場合がある
2. **ネットワーク**: `host.docker.internal` の代わりに `host.lima.internal` を使用する場合がある
3. **ボリュームマウント**: macOS のファイルシステムマウントは Docker と同様に動作
4. **イメージキャッシュ**: `finch pull` でイメージを事前にプルしておくと高速化

### Docker / Finch の切り替え

```bash
# Docker を使用
unset DOCKER_HOST

# Finch を使用
export DOCKER_HOST=unix://$HOME/.finch/finch.sock
```

## トラブルシューティング

### ポート競合

**症状**: `Address already in use` エラー

**解決**:
```bash
# 使用中のポートを確認
lsof -i :3001

# プロセスを終了
kill -9 <PID>

# 別のポートを使用
sam local start-lambda --port 3002
```

### タイムアウト

**症状**: Lambda 関数がタイムアウトする

**解決**:
```bash
# テンプレートの Timeout 値を確認（デフォルト 300 秒）
# ローカルテストでは短いタイムアウトを設定可能

# sam local invoke はテンプレートの Timeout を使用
# 必要に応じてテンプレートの値を変更
```

### 権限エラー

**症状**: `AccessDenied` や `UnauthorizedAccess` エラー

**原因**: ローカル実行では IAM ロールが適用されない。AWS CLI のデフォルトプロファイルの認証情報が使用される。

**解決**:
```bash
# AWS プロファイルを指定
export AWS_PROFILE=your-profile

# または認証情報を直接設定
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_SESSION_TOKEN=xxx
```

### Docker イメージが見つからない

**症状**: `Unable to find image` エラー

**解決**:
```bash
# Lambda ランタイムイメージを手動プル
docker pull public.ecr.aws/sam/build-python3.13:latest
docker pull public.ecr.aws/lambda/python:3.13

# Finch の場合
finch pull public.ecr.aws/sam/build-python3.13:latest
```

### Secrets Manager アクセスエラー

**症状**: ローカルテストで Secrets Manager にアクセスできない

**原因**: ローカル環境から実際の AWS Secrets Manager にアクセスするには認証情報が必要。

**解決策**:
1. AWS プロファイルを設定してリモートの Secrets Manager にアクセス
2. LocalStack を使用してローカルに Secrets Manager をモック
3. 環境変数で直接値を設定（テスト用）

```bash
# LocalStack を使用する場合
docker run -d -p 4566:4566 localstack/localstack

# シークレットを作成
aws --endpoint-url http://localhost:4566 secretsmanager create-secret \
  --name fsxn-ontap-credentials \
  --secret-string '{"username":"admin","password":"test123"}'
```

### VPC Lambda のローカルテスト

**症状**: VPC 内の Lambda 関数がローカルで動作しない

**解決**: ローカルテストでは VPC 設定は無視される。Lambda 関数は直接インターネットにアクセスできる。

```bash
# Docker ネットワークを作成（他のコンテナとの通信が必要な場合）
docker network create sam-local-network

# ネットワークを指定して実行
sam local invoke \
  --docker-network sam-local-network \
  --template legal-compliance/template-deploy.yaml \
  DiscoveryFunction
```

## ディレクトリ構造

```
events/
├── env.json                              # 共通環境変数テンプレート
├── uc01-legal-compliance/
│   └── discovery-event.json
├── uc02-financial-idp/
│   └── discovery-event.json
├── uc03-manufacturing-analytics/
│   └── discovery-event.json
├── uc04-media-vfx/
│   └── discovery-event.json
├── uc05-healthcare-dicom/
│   └── discovery-event.json
├── uc06-semiconductor-eda/
│   └── discovery-event.json
├── uc07-genomics-pipeline/
│   └── discovery-event.json
├── uc08-energy-seismic/
│   └── discovery-event.json
├── uc09-autonomous-driving/
│   └── discovery-event.json
├── uc10-construction-bim/
│   └── discovery-event.json
├── uc11-retail-catalog/
│   └── discovery-event.json
├── uc12-logistics-ocr/
│   └── discovery-event.json
├── uc13-education-research/
│   └── discovery-event.json
└── uc14-insurance-claims/
    └── discovery-event.json

samconfig.sample.toml                            # SAM CLI 設定（コピーして samconfig.toml として使用）
scripts/local-test.sh                     # 一括ローカルテスト
```

## 参考リンク

- [SAM CLI ドキュメント](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [sam local invoke リファレンス](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-local-invoke.html)
- [Finch 公式サイト](https://runfinch.com/)
- [SAM CLI + Finch 統合](https://aws.amazon.com/blogs/compute/using-finch-with-aws-sam-cli/)
