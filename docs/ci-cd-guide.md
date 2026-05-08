# CI/CD パイプラインガイド

FSxN S3 Access Points Serverless Patterns プロジェクトの CI/CD パイプライン設計・運用ガイド。

## パイプラインアーキテクチャ概要

本プロジェクトでは GitHub Actions を使用した 2 つのワークフローで CI/CD を実現する:

```
┌─────────────────────────────────────────────────────────────┐
│  CI ワークフロー (ci.yml)                                     │
│  トリガー: Pull Request → main                               │
│                                                             │
│  ┌──────┐   ┌──────┐   ┌──────────┐   ┌──────────────┐    │
│  │ Lint │ → │ Test │ → │ Security │ → │ Report/Gate  │    │
│  └──────┘   └──────┘   └──────────┘   └──────────────┘    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Deploy ワークフロー (deploy.yml)                             │
│  トリガー: Push → main (マージ後)                             │
│                                                             │
│  ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐ │
│  │ Detect  │ → │ Staging │ → │  Smoke   │ → │Production│ │
│  │ Changes │   │ Deploy  │   │  Test    │   │  Deploy  │ │
│  └─────────┘   └─────────┘   └──────────┘   └──────────┘ │
│                                              (手動承認必須)  │
└─────────────────────────────────────────────────────────────┘
```

## CI ワークフロー ステージ詳細

### Stage 1: Lint (cfn-lint)

CloudFormation テンプレートの静的解析を実行する。

- **ツール**: cfn-lint
- **対象**: プロジェクト内の全 `*.yaml` テンプレート
- **除外**: `node_modules/` 配下
- **失敗条件**: cfn-lint エラーが 1 件以上

```yaml
- run: pip install cfn-lint
- run: cfn-lint **/*.yaml --ignore-templates '**/node_modules/**'
```

### Stage 2: Test (pytest + Hypothesis)

ユニットテストとプロパティベーステストを実行する。

- **ツール**: pytest + Hypothesis
- **カバレッジ閾値**: 80%（`--cov-fail-under=80`）
- **キャッシュ**: pip + `.hypothesis` ディレクトリ
- **レポート**: XML カバレッジレポート生成

```yaml
- run: pip install -r requirements-dev.txt
- run: pytest --cov=shared --cov-report=xml --cov-fail-under=80
```

### Stage 3: Security (cfn-guard + Bandit + pip-audit)

セキュリティコンプライアンスチェックを実行する。

- **cfn-guard**: IAM least-privilege、暗号化必須、パブリックアクセス禁止
- **Bandit**: Python コードのセキュリティ脆弱性スキャン
- **pip-audit**: 依存パッケージの CVE チェック

```yaml
- run: cfn-guard validate -r security/cfn-guard-rules/ -d **/*.yaml
- run: bandit -r shared/ use-cases/ scripts/ -ll -c .bandit
- run: pip-audit -r requirements.txt
```

### Stage 4: Report / Gate

全ステージの結果を集約し、最終判定を行う。

- **ゲーティングルール**: いずれかのステージが失敗した場合、PR マージをブロック
- **アーティファクト**: カバレッジレポートを PR にアップロード
- **通知**: 失敗時に PR コメントで詳細を報告

## Deploy ワークフロー ステージ詳細

### 変更検出

`git diff` で変更された CloudFormation テンプレートを特定し、影響範囲を限定する。

### Staging デプロイ

- **スタック名**: `{stack-name}-staging` サフィックス
- **パラメータ**: `params/staging.json` を使用
- **OIDC 認証**: GitHub Actions → AWS IAM Role（長期クレデンシャル不使用）

### スモークテスト

- Step Functions テストデータを使用した E2E 検証
- 失敗時: CloudFormation 自動ロールバック実行

### Production デプロイ

- **前提条件**: Staging デプロイ成功 + スモークテスト成功
- **承認**: GitHub Actions Environment Protection Rules（最低 1 名承認）
- **パラメータ**: `params/production.json` を使用

## OIDC セットアップ手順

GitHub Actions から AWS リソースにアクセスするために OIDC (OpenID Connect) を使用する。長期クレデンシャル（Access Key）は使用しない。

### 1. AWS IAM Identity Provider 作成

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. IAM ロール作成（信頼ポリシー）

信頼ポリシーの `Condition` で対象リポジトリ・ブランチを制限する:

- `token.actions.githubusercontent.com:aud` → `sts.amazonaws.com`
- `token.actions.githubusercontent.com:sub` → `repo:{OWNER}/{REPO}:ref:refs/heads/main`

```bash
aws iam create-role \
  --role-name github-actions-deploy-role \
  --assume-role-policy-document file://trust-policy.json
```

### 3. ワークフローでの使用

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::{ACCOUNT_ID}:role/github-actions-deploy-role
      aws-region: ap-northeast-1
```

## デプロイ用 IAM ロール要件

デプロイロールに必要な権限: `cloudformation:*`, `s3:*`（テンプレートバケット）, `lambda:*`, `iam:PassRole`, `states:*`, `dynamodb:*`, `sagemaker:*`, `events:*`

**重要**: `iam:CreateRole`, `iam:AttachRolePolicy` 等の IAM ロール/ポリシー直接変更権限は付与しない。Permission Boundary を必ず設定し、最小権限の原則を厳守する。

## Environment Protection Rules 設定

### GitHub リポジトリ設定

1. **Settings** → **Environments** → **New environment**
2. 環境名: `production`
3. **Protection rules** を設定:
   - ✅ Required reviewers: 最低 1 名
   - ✅ Wait timer: 0 分（即時承認可能）
   - ✅ Deployment branches: `main` のみ

### ワークフローでの参照

```yaml
jobs:
  deploy-production:
    environment: production
    needs: [smoke-test]
    steps:
      - name: Deploy to production
        run: |
          aws cloudformation deploy \
            --template-file template.yaml \
            --stack-name ${STACK_NAME} \
            --parameter-overrides file://params/production.json
```

## ブランチ戦略

```
feature/xxx ──PR──→ main (staging 自動デプロイ) ──手動承認──→ production
     │                    │
     │                    ├── CI テスト自動実行
     │                    ├── Staging デプロイ
     │                    └── スモークテスト
     │
     └── ローカル開発・テスト
```

### フロー

1. **feature ブランチ作成**: `feature/add-serverless-inference`
2. **PR 作成**: `main` ブランチへの Pull Request
3. **CI 自動実行**: Lint → Test → Security → Report
4. **レビュー・マージ**: CI 全パス + レビュー承認後にマージ
5. **Staging 自動デプロイ**: main マージで自動トリガー
6. **スモークテスト**: Staging 環境で E2E テスト実行
7. **Production 手動承認**: Environment Protection Rules による承認
8. **Production デプロイ**: 承認後に自動実行

### ブランチ命名規則

| プレフィックス | 用途 |
|--------------|------|
| `feature/` | 新機能追加 |
| `fix/` | バグ修正 |
| `docs/` | ドキュメント更新 |
| `refactor/` | リファクタリング |
| `test/` | テスト追加・修正 |

## トラブルシューティング

### cfn-lint エラー

**症状**: CI の Lint ステージが失敗

**一般的な原因と対処**:

| エラーコード | 原因 | 対処 |
|------------|------|------|
| E3001 | リソースタイプ不正 | AWS ドキュメントで正しいリソースタイプを確認 |
| E3012 | プロパティ値の型不一致 | パラメータの型（String/Number）を確認 |
| W2001 | 未使用パラメータ | パラメータを使用するか削除 |
| E1001 | YAML 構文エラー | インデント・構文を修正 |

**ローカルでの事前確認**:

```bash
pip install cfn-lint
cfn-lint shared/cfn/*.yaml use-cases/*/template-deploy.yaml
```

### テスト失敗

**症状**: CI の Test ステージが失敗

**対処手順**:

1. ローカルでテスト再現:
   ```bash
   pip install -r requirements-dev.txt
   pytest shared/tests/ -v --tb=long
   ```

2. Hypothesis テスト失敗時:
   - `.hypothesis/examples/` にカウンターエグザンプルが保存される
   - 失敗入力を確認し、ロジックを修正

3. カバレッジ不足時:
   ```bash
   pytest --cov=shared --cov-report=html
   open htmlcov/index.html
   ```

### デプロイタイムアウト

**症状**: CloudFormation スタック更新がタイムアウト

**対処**:

1. CloudFormation イベントを確認:
   ```bash
   aws cloudformation describe-stack-events \
     --stack-name {STACK_NAME} \
     --query 'StackEvents[?ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_FAILED`]'
   ```

2. 一般的な原因: Lambda パッケージサイズ過大、SageMaker Endpoint 起動遅延、DynamoDB Global Tables レプリケーション設定

### ロールバック手順

**自動ロールバック**: スモークテスト失敗時に CloudFormation `--rollback-configuration` で自動実行。

**手動ロールバック**:

```bash
# 前回成功コミットを特定してチェックアウト
git log --oneline -5
git checkout {COMMIT_HASH}

# 再デプロイ
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name {STACK_NAME} \
  --parameter-overrides file://params/production.json
```

### OIDC 認証エラー

**症状**: `Error: Not authorized to perform sts:AssumeRoleWithWebIdentity`

**対処**:
- IAM ロールの信頼ポリシーで `sub` 条件がリポジトリ名・ブランチと一致しているか確認
- GitHub Actions の `permissions` ブロックに `id-token: write` が設定されているか確認
- OIDC プロバイダーのサムプリントが最新か確認

## ローカル開発での CI 再現

```bash
# 依存パッケージインストール
pip install -r requirements-dev.txt

# CI と同じチェックを順番に実行
cfn-lint shared/cfn/*.yaml                                          # Lint
pytest --cov=shared --cov-report=term-missing --cov-fail-under=80   # Test
cfn-guard validate -r security/cfn-guard-rules/ -d shared/cfn/*.yaml # Security
bandit -r shared/ -ll -c .bandit                                    # Bandit
pip-audit -r requirements.txt                                       # Audit
```

## 関連ファイル

| ファイル | 説明 |
|---------|------|
| `.github/workflows/ci.yml` | CI ワークフロー定義 |
| `.github/workflows/deploy.yml` | Deploy ワークフロー定義 |
| `security/cfn-guard-rules/` | cfn-guard セキュリティルール |
| `.bandit` | Bandit 設定ファイル |
| `params/staging.json` | Staging 環境パラメータ |
| `params/production.json` | Production 環境パラメータ |
| `requirements-dev.txt` | 開発・テスト依存パッケージ |
| `pytest.ini` | pytest 設定 |
