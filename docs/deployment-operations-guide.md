# デプロイ・運用ガイド — 全パターン共通

## 概要

このガイドは、全パターンのデプロイ・検証・クリーンアップで共通して適用される運用知見をまとめたもの。
Phase 18 (HA LifeKeeper Monitoring) の実デプロイから得られた教訓を反映している。

---

## デプロイ手順（共通）

### samconfig.toml の利用

```bash
# 1. テンプレートをコピーして編集
cd solutions/<category>/<pattern-name>
cp samconfig.toml.example samconfig.toml

# 2. 値を編集（エディタで開く）
# - stack_name: 識別可能な名前に
# - region: デプロイ先リージョン
# - parameter_overrides: 各パラメータを設定
# - NotificationEmail: 通知先メールアドレス

# 3. ビルド＆デプロイ
sam build
sam deploy
```

### CLI 直接指定 vs samconfig.toml

| 方式 | 利点 | 注意点 |
|------|------|--------|
| `samconfig.toml` | スペース含む値が安全に渡せる、再現性が高い | ファイルにメールアドレス等が含まれるため git にコミットしない |
| `--parameter-overrides` | ワンライナーで実行可能 | `rate(5 minutes)` などスペース含む値でパースエラーが起きやすい |

**推奨**: 常に `samconfig.toml` を使用する。`.gitignore` に `samconfig.toml` が含まれているため、誤コミットのリスクは低い。

---

## クリーンアップ手順（共通）

### 重要: S3 バケットの事前削除

CloudFormation は**オブジェクトが残存する S3 バケットを削除できない**。
スタック削除前に必ずバケットを空にする。

```bash
# 1. OutputBucket を空にして削除
aws s3 rb s3://<output-bucket-name> --force

# 2. スタック削除
aws cloudformation delete-stack \
  --stack-name <stack-name> \
  --region ap-northeast-1

# 3. 完了待機（通常 1-3 分。タイムアウトする場合は数分後に再確認）
aws cloudformation wait stack-delete-complete \
  --stack-name <stack-name> \
  --region ap-northeast-1

# 4. 削除確認（"does not exist" が表示されれば成功）
aws cloudformation describe-stacks \
  --stack-name <stack-name> \
  --region ap-northeast-1 2>&1
```

### DELETE_FAILED 時の対処

| リソース | 失敗原因 | 対応 |
|----------|----------|------|
| S3 Bucket | オブジェクトが残存 | `aws s3 rb --force` で先に削除、その後スタックを再度 delete |
| Lambda@Edge | レプリカが残存 | 数時間待機後にリトライ |
| Log Group | RetentionPolicy で保護 | 手動で CloudWatch Log Group を削除 |
| Security Group | 他リソースから参照されている | 参照元を先に削除 |

### sam delete vs aws cloudformation delete-stack

- `sam delete`: 対話的にバケット削除オプションあり。通常はこちらが便利。
- `aws cloudformation delete-stack`: エラー時の原因特定が容易。スクリプト化に向く。

---

## DemoMode デプロイの注意事項

### 共通ルール

1. **OntapSecretArn を省略する**: DemoMode では ONTAP 接続不要。空文字列 `OntapSecretArn=` を渡すと CloudFormation がバリデーションエラーを出す。samconfig.toml からその行自体を削除する。
2. **OutputBucketName にユニーク名を使う**: S3 バケット名はグローバルユニーク。`<pattern>-output-$(date +%Y%m%d)` パターンが実用的。
3. **Bedrock モデルアクセス**: デプロイ前にターゲットリージョンで使用するモデルのアクセスを有効化する。
4. **SNS サブスクリプション確認**: `NotificationEmail` を指定した場合、確認メールを承認しないとアラートが配信されない。

### samconfig.toml のセキュリティ

- `samconfig.toml` は `.gitignore` に登録済み（リポジトリルートレベル）
- メールアドレス、アカウント固有の値が含まれるため、絶対にコミットしない
- 各パターンに `samconfig.toml.example` がプレースホルダー付きで用意されている

---

## コスト管理

### デプロイ後に忘れがちなリソース

| リソース | 課金 | 対策 |
|----------|------|------|
| EventBridge Schedule | 実行ごとに Lambda / Step Functions が課金 | 検証後はスタック削除またはスケジュール無効化 |
| S3 バケット | ストレージ + リクエスト課金 | 検証後にバケットごと削除 |
| CloudWatch Logs | ストレージ課金（永続保存の場合） | LogRetentionInDays を 7 や 14 に設定 |
| SNS トピック | 通知ごとに少額課金 | スタック削除で自動削除される |
| NAT Gateway (VPC パターン) | 時間課金 + データ転送 | VPC パターンは検証後すぐ削除 |

### スクリーンショット撮影のためだけのデプロイ

ドキュメント用スクリーンショット取得が目的の場合：
1. DemoMode でデプロイ
2. Step Functions を手動実行して SUCCEEDED を確認
3. コンソールでスクリーンショット取得
4. **即座にスタック削除**（EventBridge Schedule が動き続けるのを防ぐ）

---

## Step Functions 実行のデバッグ

```bash
# 実行一覧（最新 5 件）
aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --max-results 5 \
  --query 'executions[].{name:name,status:status,start:startDate}' \
  --output table

# 特定実行の詳細
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --query '{status:status,output:output}'

# 失敗したステップの特定
aws stepfunctions get-execution-history \
  --execution-arn <execution-arn> \
  --query 'events[?type==`TaskFailed`]'
```

---

## 検証完了チェックリスト

デモ検証の完了時に以下を確認:

- [ ] Step Functions が SUCCEEDED で完了
- [ ] 期待される出力（レポート、ヘルススコア等）が生成されている
- [ ] スクリーンショット取得済み（必要な場合）
- [ ] **スタック削除完了**（`describe-stacks` で "does not exist"）
- [ ] **S3 バケット削除完了**
- [ ] `samconfig.toml` をローカルから削除（再利用予定がなければ）
- [ ] コスト発生リソースがないことを確認

---

## Related Documents

- [Demo Mode Guide](demo-mode-guide.md) — FSx for ONTAP なしでの実行方法
- [Local Testing Quick Start](local-testing-quick-start.md) — pytest + moto でのローカルテスト
- [Cost Calculator](cost-calculator.md) — 月次コスト見積もり
- 各パターンの `docs/demo-guide.md` — パターン固有のデプロイ手順
