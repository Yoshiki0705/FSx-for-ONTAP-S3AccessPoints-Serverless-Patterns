# Operational Acceptance Criteria

## Purpose

本番運用開始前に満たすべき検証項目セット。全項目が Pass であることを確認してから本番トラフィックを受け入れる。

## Validation Frequency

- **初回デプロイ時**: 全項目を検証
- **四半期ごと**: 全項目を再検証（環境変更がなくても）
- **重大変更後**: 影響を受ける項目を再検証

---

## Acceptance Criteria

| # | Criterion | Validation Method | Pass/Fail | Evidence | Last Validated |
|---|-----------|-------------------|-----------|----------|----------------|
| 1 | fsxadmin Secrets Rotation が 4 ステップ完了する | `aws secretsmanager rotate-secret --secret-id $SECRET_ARN` 実行後、AWSCURRENT が新パスワードに更新されること | | | |
| 2 | FPolicy E2E イベントが SLO 内で SQS に到達する | NFS ファイル作成 → SQS メッセージ受信が P99 < 5 秒であること | | | |
| 3 | Persistent Store が全イベントをリプレイする | Fargate 停止 → ファイル作成 → 再起動 → SQS で全イベント受信（ロス 0）| | | |
| 4 | SLO Dashboard が表示され全アラームが OK | CloudWatch コンソールでダッシュボード表示 + 4 アラーム全て OK 状態 | | | |
| 5 | BREAK_GLASS モード遷移が 60 秒以内に SNS アラートを発報する | `GUARDRAIL_MODE=BREAK_GLASS` 設定 → SNS メッセージ受信確認 | | | |
| 6 | SQS バックログアラームが発報しランブック手順が実行可能 | SQS に意図的にメッセージ滞留 → アラーム発報 → ランブック手順実行 | | | |
| 7 | S3AP モニタリングパスが検証済み | VPC-external Lambda が `S3APHealthCheck=1` メトリクスを発行すること | | | |

---

## Validation Procedures

### Criterion 1: Secrets Rotation

```bash
# 実行
aws secretsmanager rotate-secret --secret-id $SECRET_ARN --region $REGION

# 検証（60 秒待機後）
aws secretsmanager describe-secret --secret-id $SECRET_ARN --region $REGION \
  --query 'VersionIdsToStages'

# 期待結果: AWSCURRENT が新しい VersionId に紐づいていること
```

### Criterion 2: FPolicy E2E Latency

```bash
# ファイル作成（タイムスタンプ記録）
START=$(date +%s%3N)
ssh $BASTION "echo test > /mnt/fpolicy_vol/acceptance_test_$(date +%s).txt"

# SQS メッセージ受信待ち（最大 10 秒）
MSG=$(aws sqs receive-message --queue-url $SQS_QUEUE_URL --wait-time-seconds 10)
END=$(date +%s%3N)

# レイテンシ計算
LATENCY=$((END - START))
echo "E2E Latency: ${LATENCY}ms (SLO: < 5000ms)"
```

### Criterion 3: Persistent Store Replay

```bash
# 1. Fargate タスク停止
TASK_ARN=$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $FPOLICY_SERVICE --query 'taskArns[0]' --output text)
aws ecs stop-task --cluster $ECS_CLUSTER --task $TASK_ARN

# 2. ダウンタイム中にファイル作成
for i in $(seq 1 5); do
  ssh $BASTION "echo test > /mnt/fpolicy_vol/replay_acceptance_${i}.txt"
done

# 3. ECS 自動復旧待ち（最大 3 分）
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $FPOLICY_SERVICE

# 4. FPolicy engine IP 更新
# (ONTAP CLI で実行)

# 5. SQS メッセージ確認（5 件全て受信）
COUNT=$(aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessagesVisible \
  --query 'Attributes.ApproximateNumberOfMessagesVisible' --output text)
echo "Messages in queue: $COUNT (expected: 5)"
```

### Criterion 4: SLO Dashboard

```bash
# アラーム状態確認
aws cloudwatch describe-alarms \
  --alarm-name-prefix "${PROJECT_PREFIX}-slo-" \
  --query 'MetricAlarms[].[AlarmName,StateValue]' \
  --output table

# 期待結果: 全て OK
```

### Criterion 5: BREAK_GLASS Alert

```bash
# BREAK_GLASS モードで操作実行
# (guardrails.py の check_and_execute を BREAK_GLASS モードで呼び出し)

# SNS メッセージ確認（60 秒以内）
# メールまたは SQS サブスクリプションで受信確認
```

### Criterion 6: SQS Backlog Alarm

```bash
# 意図的にメッセージ滞留（FPolicy サーバー停止 + ファイル大量作成）
# アラーム発報確認
aws cloudwatch describe-alarms \
  --alarm-names "${PROJECT_PREFIX}-slo-ingestion-latency" \
  --query 'MetricAlarms[0].StateValue'

# ランブック手順実行
# docs/runbooks/slo-violation-response.md の手順に従う
```

### Criterion 7: S3AP Monitoring

```bash
# Lambda 手動実行
aws lambda invoke \
  --function-name "${PROJECT_PREFIX}-s3ap-ext-monitor" \
  --payload '{}' \
  /tmp/s3ap_health_result.json

cat /tmp/s3ap_health_result.json
# 期待結果: {"healthy": true, "metric_value": 1, ...}

# メトリクス確認
aws cloudwatch get-metric-statistics \
  --namespace "FSxN-S3AP-Patterns/Canary" \
  --metric-name S3APHealthCheck \
  --dimensions Name=CheckType,Value=VPC-External \
  --start-time $(date -d '10 minutes ago' --iso-8601=seconds) \
  --end-time $(date --iso-8601=seconds) \
  --period 300 \
  --statistics Minimum
```
