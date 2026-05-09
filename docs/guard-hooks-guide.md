# CloudFormation Guard Hooks ガイド

## 概要

CloudFormation Guard Hooks は、CloudFormation スタックのデプロイ時にポリシーを強制するサーバーサイドのガバナンス機能です。cfn-guard ルールを CloudFormation Hook として登録し、リソース作成・更新時に自動的にポリシーチェックを実行します。

### サーバーサイド vs クライアントサイドの違い

| 項目 | サーバーサイド (Guard Hooks) | クライアントサイド (CI/CD cfn-lint) |
|------|---------------------------|----------------------------------|
| 実行タイミング | デプロイ時（CloudFormation 内部） | ビルド時（CI/CD パイプライン内） |
| バイパス可能性 | 不可（AWS 側で強制） | 可能（パイプラインスキップ） |
| 対象範囲 | アカウント内の全スタック | パイプライン経由のデプロイのみ |
| フィードバック速度 | デプロイ時（数分） | コミット時（数秒） |
| 用途 | 最終防衛線（ガバナンス） | 早期検出（開発者体験） |

**推奨**: 両方を併用する。CI/CD で早期検出 + Guard Hooks で最終防衛線。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│ CloudFormation Stack Deploy                              │
│                                                          │
│  1. テンプレート受信                                      │
│  2. Guard Hook 呼び出し (PRE_PROVISION)                   │
│     ├── S3 から .guard ルール読み込み                     │
│     ├── リソースプロパティをルールで評価                   │
│     └── PASS / FAIL 判定                                 │
│  3. PASS → リソース作成続行                               │
│     FAIL → FailureMode に応じて:                         │
│       - FAIL: デプロイ中止 + ロールバック                 │
│       - WARN: 警告ログ出力 + デプロイ続行                 │
└─────────────────────────────────────────────────────────┘
```

## 有効化手順

### 前提条件

- AWS CLI v2 がインストール済み
- 適切な IAM 権限（CloudFormation, S3, IAM, Logs）
- `security/cfn-guard-rules/` にルールファイルが存在

### Step 1: デプロイスクリプト実行

```bash
# 本番環境（FAIL モード — ルール違反でデプロイブロック）
./scripts/deploy-hooks.sh --failure-mode FAIL

# テスト環境（WARN モード — 警告のみ）
./scripts/deploy-hooks.sh --failure-mode WARN --stack-name guard-hooks-test

# ドライラン（S3 アップロードのみ）
./scripts/deploy-hooks.sh --dry-run
```

### Step 2: 動作確認

```bash
# Hook の登録状態確認
aws cloudformation describe-type \
  --type HOOK \
  --type-name "fsxn-s3ap-guard-hooks::Guard::Hook" \
  --region ap-northeast-1

# スタック出力確認
aws cloudformation describe-stacks \
  --stack-name fsxn-s3ap-guard-hooks \
  --query "Stacks[0].Outputs" \
  --region ap-northeast-1
```

### Step 3: テストデプロイ

意図的にルール違反するテンプレートでブロック確認:

```yaml
# test-violation.yaml — 暗号化なし S3 バケット（encryption-required.guard 違反）
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  UnsafeBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: test-no-encryption-bucket
      # BucketEncryption が未設定 → Guard Hook でブロックされるはず
```

```bash
# テストデプロイ（FAIL モードならブロックされる）
aws cloudformation deploy \
  --template-file test-violation.yaml \
  --stack-name test-guard-violation \
  --region ap-northeast-1
```

## 適用ルール一覧

本プロジェクトでは以下の cfn-guard ルールを適用:

| ルールファイル | 内容 |
|---------------|------|
| `encryption-required.guard` | S3, DynamoDB, Logs の暗号化必須 |
| `iam-least-privilege.guard` | IAM ポリシーのワイルドカード制限 |
| `lambda-limits.guard` | Lambda メモリ・タイムアウト上限 |
| `no-public-access.guard` | S3 パブリックアクセスブロック必須 |
| `sagemaker-security.guard` | SageMaker エンドポイントのセキュリティ設定 |

## CI/CD（Phase 5）との使い分け

```
開発フロー:
  コード変更 → CI/CD (cfn-lint + cfn-guard validate) → Guard Hooks → デプロイ完了
              ↑ 早期検出（秒単位）                    ↑ 最終防衛線（分単位）
```

| シナリオ | CI/CD | Guard Hooks |
|---------|-------|-------------|
| 開発者がローカルでテスト | ✅ `cfn-lint` で即座にフィードバック | ❌ デプロイしないと検出不可 |
| パイプライン経由のデプロイ | ✅ ビルドステージでブロック | ✅ デプロイステージでもブロック |
| コンソールからの手動デプロイ | ❌ パイプラインを通らない | ✅ 必ずブロック |
| 別チームのスタック | ❌ 別パイプライン | ✅ アカウント全体に適用 |

## FailureMode の切り替え

```bash
# WARN → FAIL に変更（本番適用）
./scripts/deploy-hooks.sh --failure-mode FAIL

# FAIL → WARN に変更（一時的に緩和）
./scripts/deploy-hooks.sh --failure-mode WARN
```

## トラブルシューティング

### Hook 失敗時のデバッグ

1. **CloudWatch Logs 確認**:
   ```bash
   aws logs tail "/aws/cloudformation/hooks/fsxn-s3ap-guard-hooks" \
     --region ap-northeast-1 \
     --since 1h
   ```

2. **スタックイベント確認**:
   ```bash
   aws cloudformation describe-stack-events \
     --stack-name <failed-stack-name> \
     --region ap-northeast-1 \
     --query "StackEvents[?ResourceStatus=='CREATE_FAILED']"
   ```

3. **Hook 実行結果確認**:
   ```bash
   aws cloudformation describe-type \
     --type HOOK \
     --type-name "fsxn-s3ap-guard-hooks::Guard::Hook" \
     --region ap-northeast-1 \
     --query "TypeTestsStatus"
   ```

### よくある問題

| 問題 | 原因 | 解決策 |
|------|------|--------|
| Hook が実行されない | HookStatus が DISABLED | `HookStatus: ENABLED` を確認 |
| S3 アクセスエラー | IAM ロールの権限不足 | HookExecutionRole のポリシーを確認 |
| ルール評価エラー | .guard ファイルの構文エラー | `cfn-guard validate` でローカル検証 |
| 全スタックがブロックされる | TargetFilters が広すぎる | TargetNames を絞り込む |

### Hook の一時無効化

緊急時に Hook を無効化する場合:

```bash
# 方法 1: WARN モードに変更（推奨）
./scripts/deploy-hooks.sh --failure-mode WARN

# 方法 2: スタック削除（完全無効化）
aws cloudformation delete-stack \
  --stack-name fsxn-s3ap-guard-hooks \
  --region ap-northeast-1
```

## ルールの追加・更新

1. `security/cfn-guard-rules/` に `.guard` ファイルを追加
2. ローカルで検証:
   ```bash
   cfn-guard validate \
     --rules security/cfn-guard-rules/new-rule.guard \
     --data autonomous-driving/template-deploy.yaml
   ```
3. デプロイスクリプトを再実行:
   ```bash
   ./scripts/deploy-hooks.sh
   ```

## 関連ドキュメント

- [AWS CloudFormation Guard Hooks ドキュメント](https://docs.aws.amazon.com/cloudformation-cli/latest/hooks-userguide/hooks-guard.html)
- [cfn-guard ルール構文](https://docs.aws.amazon.com/cfn-guard/latest/ug/writing-rules.html)
- [CI/CD ガイド](./ci-cd-guide.md)
