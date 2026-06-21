# HA LifeKeeper Monitoring — デモガイド

## 概要

このガイドでは、DemoMode を使用して FSx for ONTAP なしで HA LifeKeeper Monitoring パターンをデプロイ・検証する手順を説明する。

---

## 前提条件

- AWS アカウント + SAM CLI インストール済み
- Python 3.12
- Amazon Bedrock で `amazon.nova-pro-v1:0` のモデルアクセスが有効化済み
- 所要時間: 約 10 分

---

## Step 1: リポジトリ取得

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/ha/lifekeeper-monitoring
```

---

## Step 2: デモ用 S3 バケット作成とサンプルログ配置

```bash
# バケット作成
DEMO_BUCKET="lifekeeper-demo-$(date +%s)"
aws s3 mb s3://$DEMO_BUCKET

# サンプルログをアップロード
aws s3 cp ../../../test-data/ha-lifekeeper-monitoring/ s3://$DEMO_BUCKET/lifekeeper/logs/ --recursive
```

---

## Step 3: デプロイ

```bash
sam build
sam deploy --guided \
  --stack-name ha-lifekeeper-monitoring-demo \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=$DEMO_BUCKET \
    OutputBucketName=$DEMO_BUCKET \
    NotificationEmail=your@email.com \
    ClusterName=demo-cluster \
    TriggerMode=POLLING \
    ScheduleExpression="rate(5 minutes)"
```

---

## Step 4: 手動実行

```bash
# Step Functions ARN を取得
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name ha-lifekeeper-monitoring-demo \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
  --output text)

# 手動実行
aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Step 5: 結果確認

### S3 レポート確認

```bash
aws s3 ls s3://$DEMO_BUCKET/reports/ --recursive
aws s3 cp s3://$DEMO_BUCKET/reports/latest-report.md - | head -50
```

### CloudWatch ログ確認

AWS コンソールの CloudWatch Logs で以下のロググループを確認:
- `/aws/lambda/ha-lifekeeper-monitoring-demo-Discovery`
- `/aws/lambda/ha-lifekeeper-monitoring-demo-Processing`
- `/aws/lambda/ha-lifekeeper-monitoring-demo-Report`

### 期待される結果

- Discovery: 5 ファイル検出 (failover-event × 1, health-check × 1, comm-path × 1, recovery-kit × 1, general × 1)
- Processing: ヘルススコア 40/100 — サンプルログにはフェイルオーバーイベントや異常パターンが意図的に含まれており、スコアリングパイプラインが正しく減点することを確認するためのデータセット
- Report: Markdown レポート生成 + SNS 通知条件判定

> **注意**: スコア 40/100 はサンプルデータの検出結果であり、LifeKeeper や FSx for ONTAP の品質指標ではない。実環境ではログ内容に応じてスコアが変動する。

---

## Step 6: フェイルオーバーアラートテスト

```bash
# FailoverAlertSeverity を WARNING に変更して再デプロイ
sam deploy --parameter-overrides \
  DemoMode=true \
  S3AccessPointAlias=$DEMO_BUCKET \
  OutputBucketName=$DEMO_BUCKET \
  NotificationEmail=your@email.com \
  FailoverAlertSeverity=WARNING

# 再実行 → WARNING 以上のイベントがあるため SNS 通知が発火
aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

メール受信を確認。

---

## Step 7: クリーンアップ

**重要**: S3 バケットにオブジェクトが残っている場合、CloudFormation スタック削除が `DELETE_FAILED` になる。先にバケットを空にしてからスタックを削除する。

```bash
# 1. 出力バケットを空にして削除（スタック削除前に必須）
aws s3 rb s3://$DEMO_BUCKET --force

# 2. スタック削除
aws cloudformation delete-stack --stack-name ha-lifekeeper-monitoring-demo --region ap-northeast-1

# 3. 削除完了を待機（通常 1-3 分）
aws cloudformation wait stack-delete-complete --stack-name ha-lifekeeper-monitoring-demo --region ap-northeast-1

# 4. 削除確認
aws cloudformation describe-stacks --stack-name ha-lifekeeper-monitoring-demo --region ap-northeast-1 2>&1
# "does not exist" と表示されれば完了
```

> **Tips**: `sam delete` コマンドも利用可能だが、S3 バケット内にオブジェクトがある場合は事前の `--force` 削除が必要な点は同じ。`aws cloudformation delete-stack` の方がエラー時の原因特定が容易。

---

## トラブルシューティング

| 症状 | 原因 | 対応 |
|------|------|------|
| Discovery で 0 ファイル検出 | サンプルログが配置されていない | Step 2 の s3 cp を再実行 |
| Processing で Bedrock エラー | モデルアクセスが未有効化 | Bedrock コンソールでモデルアクセス申請 |
| SNS 通知が届かない | メール未確認 | SNS サブスクリプション確認メールを承認 |
| Lambda タイムアウト | 大量ログ or Bedrock レイテンシ | MaxFilesPerExecution を小さく設定 |
| `sam deploy` で `Invalid value` エラー | `OntapSecretArn=` (空文字) をパラメータに含めている | DemoMode ではこのパラメータを省略する（samconfig.toml から行を削除） |
| `ScheduleExpression` が `rate(5` で切れる | CLI からのスペース含むパラメータが正しくクォートされていない | `samconfig.toml` 経由でデプロイする（CLI の `--parameter-overrides` ではスペース含む値は問題になりやすい） |
| スタック削除が `DELETE_FAILED` | OutputBucket にオブジェクトが残存 | `aws s3 rb s3://bucket --force` でバケットを先に空にしてからリトライ |
| `wait stack-delete-complete` が exit 1 | 削除に時間がかかっている（タイムアウト） | 数分後に `describe-stacks` で状態を再確認。大抵は正常に完了する |
| ヘルススコアが 40/100 | サンプルログにフェイルオーバーイベントが含まれている | 正常な動作。実環境ではログ内容に応じてスコアが変動する |

### デプロイ時の注意事項

1. **samconfig.toml を使う**: CLI の `--parameter-overrides` でスペースを含む値（`rate(5 minutes)` 等）を渡すと解析エラーになりやすい。`samconfig.toml` の配列形式が安全。
2. **OutputBucketName の命名**: S3 バケット名はグローバルユニークが必要。`$(date +%Y%m%d)` やアカウント ID を含めるパターンが実用的。
3. **Bedrock モデルアクセス**: デプロイ前に `amazon.nova-pro-v1:0` のモデルアクセスを有効化する。初回は承認に数分かかる。
4. **SNS サブスクリプション確認**: `NotificationEmail` を指定すると確認メールが届く。承認しないとアラート通知が配信されない。
5. **DemoMode では OntapSecretArn を省略**: 空文字列 `OntapSecretArn=` を渡すと SAM CLI / CloudFormation がバリデーションエラーを出す。samconfig.toml からその行自体を削除する。

---

## 次のステップ

- 本番環境: FSx for ONTAP S3 AP を使用し `DemoMode=false` でデプロイ
- HYBRID モード: FPolicy イベント駆動を併用して即時検知を実現
- カスタム分析: Bedrock プロンプトをカスタマイズして自社固有の障害パターンを学習
