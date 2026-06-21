# ローカルテスト クイックスタート

## shared/ モジュールの解決方法

本リポジトリの Lambda 関数は `shared/` ディレクトリの共通モジュールを使用しています。
ローカルでテストする際は以下の方法で解決します。

### ユニットテスト実行時

```bash
# リポジトリルートから実行（PYTHONPATH に自動追加される）
python3 -m pytest solutions/industry/semiconductor-eda/tests/ -v

# または明示的に PYTHONPATH を設定
PYTHONPATH=. python3 -m pytest solutions/sap/erp-adjacent/tests/ -v
```

### sam build 時

SAM CLI は `CodeUri` で指定されたディレクトリを Lambda パッケージとしてビルドします。
`shared/` モジュールは以下のいずれかの方法で解決されます:

1. **Lambda Layer（推奨）**: `shared/` を Layer としてデプロイし、各関数から参照
2. **requirements.txt 内の相対パス**: `../shared` を editable install
3. **コピー方式**: `sam build` 前に `shared/` を各関数ディレクトリにコピー

現在の実装では **conftest.py の sys.path 操作** でテスト時に解決し、
**SAM build 時は Layer または CodeUri の親ディレクトリ指定** で解決しています。

```python
# conftest.py（各パターンの tests/ に配置）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # リポジトリルート
sys.path.insert(0, str(Path(__file__).parent.parent / "functions" / "discovery"))
```

### IDE 設定（VS Code / PyCharm）

```json
// .vscode/settings.json
{
  "python.analysis.extraPaths": [".", "./shared"],
  "python.autoComplete.extraPaths": [".", "./shared"]
}
```

## Prerequisites チェック

以下のコマンドで前提条件を確認してください:

```bash
#!/bin/bash
# prerequisites-check.sh
echo "=== Prerequisites Check ==="

# AWS CLI
echo -n "AWS CLI: "
aws --version 2>/dev/null && echo "✅" || echo "❌ Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"

# SAM CLI
echo -n "SAM CLI: "
sam --version 2>/dev/null && echo "✅" || echo "❌ Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"

# Python 3.12
echo -n "Python 3.12: "
python3.12 --version 2>/dev/null && echo "✅" || echo "⚠️ Python 3.12 recommended (3.9+ required)"

# Docker (for sam local)
echo -n "Docker: "
docker --version 2>/dev/null && echo "✅" || echo "⚠️ Required for sam local invoke"

# AWS credentials
echo -n "AWS Credentials: "
aws sts get-caller-identity --query Account --output text 2>/dev/null && echo "✅" || echo "❌ Configure: aws configure"

# Region
echo -n "Region: "
aws configure get region 2>/dev/null || echo "❌ Set: aws configure set region ap-northeast-1"

echo ""
echo "=== Service-Specific Checks ==="

# Bedrock model access
echo -n "Bedrock Model Access: "
aws bedrock list-foundation-models --query 'modelSummaries[?modelId==`amazon.nova-lite-v1:0`].modelId' --output text 2>/dev/null && echo "✅" || echo "⚠️ Enable in Bedrock console"

echo ""
echo "=== Done ==="
```

## sam local invoke の使い方

### 1. ビルド

```bash
cd <pattern-directory>
sam build
```

### 2. Discovery Lambda のローカル実行

```bash
# events/ ディレクトリのサンプルイベントを使用
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 環境変数をオーバーライド
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 3. env.json の例

```json
{
  "DiscoveryFunction": {
    "S3_ACCESS_POINT_ALIAS": "your-s3ap-alias-ext-s3alias",
    "ONTAP_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds",
    "OUTPUT_BUCKET": "your-output-bucket",
    "POWERTOOLS_SERVICE_NAME": "local-test"
  }
}
```

### 4. Step Functions ローカルテスト

Step Functions のローカルテストには [AWS Step Functions Local](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-local.html) を使用:

```bash
# Docker で Step Functions Local を起動
docker run -p 8083:8083 \
  amazon/aws-stepfunctions-local

# ステートマシンを作成
aws stepfunctions create-state-machine \
  --endpoint-url http://localhost:8083 \
  --definition file://statemachine/workflow.asl.json \
  --name local-test \
  --role-arn arn:aws:iam::123456789012:role/dummy
```

### 5. ユニットテスト実行

```bash
# パターンディレクトリから
cd <pattern-directory>
python3 -m pytest tests/ -v

# 全パターンのテスト（リポジトリルートから）
python3 -m pytest */tests/ --tb=short -q
```

## 注意事項

- `sam local invoke` は Docker を使用するため、初回実行時にイメージダウンロードが発生します
- S3 Access Point へのアクセスはローカルではモックされません（moto を使用したユニットテストを推奨）
- ONTAP REST API へのアクセスは VPN/Direct Connect 経由が必要です
- Bedrock API はローカルからも呼び出し可能ですが、モデルアクセスの有効化が必要です

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `sam build` 失敗 | Python バージョン不一致 | `--use-container` オプションを追加 |
| Docker エラー | Docker Desktop 未起動 | Docker Desktop を起動 |
| Timeout | Lambda タイムアウト設定が短い | `--timeout` オプションで延長 |
| ImportError | 依存パッケージ不足 | `requirements.txt` を確認、`sam build` を再実行 |
| AccessDenied | AWS 認証情報の問題 | `aws sts get-caller-identity` で確認 |
