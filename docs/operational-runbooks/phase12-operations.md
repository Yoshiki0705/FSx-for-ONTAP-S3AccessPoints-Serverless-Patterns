# Phase 12 — Operational Hardening & Observability 運用手順書

**作成日**: 2026-05-16
**対象**: Phase 12 デプロイ済みリソースの運用・トラブルシューティング

---

## 目次

1. [FPolicy パイプラインヘルスチェック](#1-fpolicy-パイプラインヘルスチェック)
2. [FPolicy エンジン IP 更新手順](#2-fpolicy-エンジン-ip-更新手順)
3. [Secrets Rotation 手動トリガー](#3-secrets-rotation-手動トリガー)
4. [Capacity Forecast 結果確認](#4-capacity-forecast-結果確認)
5. [SLO Dashboard 確認](#5-slo-dashboard-確認)
6. [トラブルシューティング](#6-トラブルシューティング)
7. [EC2 Instance Connect 手順](#7-ec2-instance-connect-手順)

---

## 1. FPolicy パイプラインヘルスチェック

FPolicy パイプラインの正常性を確認する手順。

### 1.1 ECS タスクステータス確認

```bash
# クラスター内の実行中タスク一覧
aws ecs list-tasks \
  --cluster fsxn-fpolicy-fsxn-fp-srv \
  --desired-status RUNNING \
  --region ap-northeast-1

# タスク詳細（IP アドレス、ヘルスステータス）
TASK_ARN=$(aws ecs list-tasks \
  --cluster fsxn-fpolicy-fsxn-fp-srv \
  --desired-status RUNNING \
  --query 'taskArns[0]' --output text \
  --region ap-northeast-1)

aws ecs describe-tasks \
  --cluster fsxn-fpolicy-fsxn-fp-srv \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].{status:lastStatus, health:healthStatus, ip:attachments[0].details[?name==`privateIPv4Address`].value|[0]}' \
  --region ap-northeast-1
```

### 1.2 KEEP_ALIVE ログ確認

ONTAP からの KEEP_ALIVE メッセージが 2 分間隔で届いていることを確認する。

```bash
# 直近 10 分間のログを確認
aws logs filter-log-events \
  --log-group-name "/ecs/fsxn-fpolicy-server-fsxn-fp-srv" \
  --start-time $(date -d '10 minutes ago' +%s000 2>/dev/null || date -v-10M +%s000) \
  --filter-pattern "KEEP_ALIVE" \
  --region ap-northeast-1 \
  --query 'events[].message'
```

**正常時の出力例**:
```
[KEEP_ALIVE] Received from 10.0.3.72 (session_id=1)
[KEEP_ALIVE] Sent response to 10.0.3.72
```

KEEP_ALIVE が 5 分以上途絶えている場合は、ONTAP 側の FPolicy 接続が切断されている可能性がある。

### 1.3 SQS メッセージフロー確認

```bash
# SQS キューの属性確認（メッセージ数）
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-northeast-1.amazonaws.com/178625946981/FPolicy_Q \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-northeast-1

# 直近のメッセージを確認（非破壊的ピーク）
aws sqs receive-message \
  --queue-url https://sqs.ap-northeast-1.amazonaws.com/178625946981/FPolicy_Q \
  --max-number-of-messages 1 \
  --visibility-timeout 0 \
  --region ap-northeast-1
```

### 1.4 パイプライン全体の正常性判定

| チェック項目 | 正常 | 異常 |
|-------------|------|------|
| ECS タスク | RUNNING + HEALTHY | STOPPED / UNHEALTHY |
| KEEP_ALIVE | 2分間隔で受信 | 5分以上途絶 |
| SQS メッセージ | ファイル操作後に増加 | 常に 0（イベント未到達） |

---

## 2. FPolicy エンジン IP 更新手順

Fargate タスクが再起動すると Private IP が変わる。ONTAP の FPolicy external-engine に登録された IP を更新する必要がある。

### 2.1 新しいタスク IP の取得

```bash
TASK_ARN=$(aws ecs list-tasks \
  --cluster fsxn-fpolicy-fsxn-fp-srv \
  --desired-status RUNNING \
  --query 'taskArns[0]' --output text \
  --region ap-northeast-1)

NEW_IP=$(aws ecs describe-tasks \
  --cluster fsxn-fpolicy-fsxn-fp-srv \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value|[0]' \
  --output text \
  --region ap-northeast-1)

echo "New Fargate Task IP: $NEW_IP"
```

### 2.2 ONTAP REST API で external-engine IP を更新

> **⚠️ IMPORTANT**: FPolicy ポリシーが有効（enabled）の状態では、エンジンの `primary_servers` を直接変更できない。以下の 3 ステップで更新すること:
>
> 1. **ポリシーを無効化**: `PATCH .../policies/fpolicy_aws` with `{"enabled": false}`
> 2. **エンジン IP を更新**: `PATCH .../engines/fpolicy_aws_engine` with `{"primary_servers": ["<NEW_IP>"]}`
> 3. **ポリシーを再有効化**: `PATCH .../policies/fpolicy_aws` with `{"enabled": true, "priority": 1}`
>
> ステップ 1 をスキップすると以下の ONTAP エラーが発生する:
> ```
> "code": "9764942", "message": "One or more enabled policies are using the external engine"
> ```

```bash
# ONTAP 管理 IP と認証情報
ONTAP_MGMT_IP="10.0.3.72"
SVM_NAME="FSxN_OnPre"

# Step 1: FPolicy ポリシーを無効化
curl -sk -u fsxadmin:<PASSWORD> \
  -X PATCH \
  "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/policies/fpolicy_aws" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Step 2: FPolicy external-engine の primary-servers を更新
curl -sk -u fsxadmin:<PASSWORD> \
  -X PATCH \
  "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/engines/fpolicy_aws_engine" \
  -H "Content-Type: application/json" \
  -d "{\"primary_servers\": [\"${NEW_IP}\"]}"

# Step 3: FPolicy ポリシーを再有効化
curl -sk -u fsxadmin:<PASSWORD> \
  -X PATCH \
  "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/policies/fpolicy_aws" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "priority": 1}'
```

**代替: ONTAP CLI (SSH 経由)**:

> **Note**: ONTAP 9.11+ では `vserver` プレフィックスは非推奨。以下は推奨形式。
> 旧形式（`vserver fpolicy ...`）も後方互換性のため引き続き動作する。

```
# Step 1: ポリシー無効化
fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

# Step 2: エンジン IP 更新
fpolicy policy external-engine modify \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <NEW_IP>

# Step 3: ポリシー再有効化
fpolicy enable -vserver FSxN_OnPre -policy-name fpolicy_aws -sequence-number 1
```

### 2.3 接続確認

IP 更新後、ONTAP が新しい IP に接続するまで最大 30 秒待機。ECS ログで NEGO_REQ を確認する。

```bash
aws logs filter-log-events \
  --log-group-name "/ecs/fsxn-fpolicy-server-fsxn-fp-srv" \
  --start-time $(date -d '2 minutes ago' +%s000 2>/dev/null || date -v-2M +%s000) \
  --filter-pattern "NEGO_REQ" \
  --region ap-northeast-1
```

---

## 3. Secrets Rotation 手動トリガー

### 3.1 事前確認

⚠️ **注意**: ローテーションは ONTAP fsxadmin パスワードを変更する。他のシステムが同じ認証情報を使用している場合は影響を確認すること。

```bash
# 現在のシークレットバージョン確認
aws secretsmanager describe-secret \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --region ap-northeast-1 \
  --query '{Name:Name, RotationEnabled:RotationEnabled, LastRotatedDate:LastRotatedDate}'
```

### 3.2 ローテーション実行

```bash
aws secretsmanager rotate-secret \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --region ap-northeast-1
```

### 3.3 結果確認

```bash
# ローテーション Lambda のログ確認
aws logs filter-log-events \
  --log-group-name "/aws/lambda/fsxn-s3ap-secrets-rotation" \
  --start-time $(date -d '5 minutes ago' +%s000 2>/dev/null || date -v-5M +%s000) \
  --region ap-northeast-1 \
  --query 'events[].message'

# 新しいシークレット値で ONTAP 接続テスト
aws secretsmanager get-secret-value \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --region ap-northeast-1 \
  --query 'SecretString' --output text
```

---

## 4. Capacity Forecast 結果確認

### 4.1 Lambda 手動実行

```bash
aws lambda invoke \
  --function-name fsxn-s3ap-capacity-forecast \
  --region ap-northeast-1 \
  --payload '{}' \
  /tmp/forecast-result.json

cat /tmp/forecast-result.json | python3 -m json.tool
```

**出力例**:
```json
{
  "days_until_full": 169374,
  "current_usage_pct": 0.03,
  "total_capacity_gb": 1024.0,
  "growth_rate_gb_per_day": 0.006,
  "forecast_date": "2490-02-06T06:26:42Z"
}
```

### 4.2 CloudWatch メトリクス確認

```bash
aws cloudwatch get-metric-data \
  --metric-data-queries '[{
    "Id": "duf",
    "MetricStat": {
      "Metric": {
        "Namespace": "FSxN-S3AP-Patterns",
        "MetricName": "DaysUntilFull"
      },
      "Period": 86400,
      "Stat": "Minimum"
    }
  }]' \
  --start-time $(date -d '7 days ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -v-7d +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date +%Y-%m-%dT%H:%M:%S) \
  --region ap-northeast-1
```

### 4.3 アラーム状態確認

```bash
aws cloudwatch describe-alarms \
  --alarm-names "fsxn-s3ap-days-until-full" \
  --region ap-northeast-1 \
  --query 'MetricAlarms[0].{State:StateValue, Threshold:Threshold}'
```

---

## 5. SLO Dashboard 確認

### 5.1 ダッシュボード URL

```
https://ap-northeast-1.console.aws.amazon.com/cloudwatch/home?region=ap-northeast-1#dashboards/dashboard/fsxn-s3ap-slo-dashboard
```

### 5.2 SLO アラーム一覧確認

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix "fsxn-s3ap-slo-" \
  --region ap-northeast-1 \
  --query 'MetricAlarms[].[AlarmName,StateValue,MetricName]' \
  --output table
```

**期待される SLO アラーム**:

| アラーム名 | メトリクス | 閾値 |
|-----------|----------|------|
| fsxn-s3ap-slo-ingestion-latency | EventIngestionLatency_ms | ≤ 5000ms |
| fsxn-s3ap-slo-success-rate | ProcessingSuccessRate_pct | ≥ 99.5% |
| fsxn-s3ap-slo-reconnect-time | FPolicyReconnectTime_sec | ≤ 60s |
| fsxn-s3ap-slo-replay-completion | ReplayCompletionTime_sec | ≤ 300s |

---

## 6. トラブルシューティング

### 6.1 SQS AccessDenied

**症状**: FPolicy サーバーログに `[SQS Error] AccessDenied` が記録される。

**原因**: ECS タスクロールの SQS ポリシーが実際のキュー ARN にマッチしていない。

**確認手順**:
```bash
# タスクロールのポリシー確認
aws iam get-role-policy \
  --role-name fsxn-fpolicy-task-fsxn-fp-srv \
  --policy-name FPolicyServerAccess \
  --query 'PolicyDocument.Statement[?Action[0]==`sqs:SendMessage`].Resource'

# 実際の SQS キュー ARN 確認
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-northeast-1.amazonaws.com/178625946981/FPolicy_Q \
  --attribute-names QueueArn \
  --region ap-northeast-1
```

**修正**:
```bash
# タスクロールに正しい SQS ARN を追加
aws iam put-role-policy \
  --role-name fsxn-fpolicy-task-fsxn-fp-srv \
  --policy-name SQSSendMessage \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-northeast-1:178625946981:FPolicy_Q"
    }]
  }'
```

**根本原因**: `fpolicy-server-fargate.yaml` テンプレートの SQS Resource パターンが実際のキュー名にマッチしなかった。修正済み（`*` ワイルドカード使用）。

### 6.2 Canary FAILED

**症状**: CloudWatch Synthetics Canary が FAILED 状態。

**確認手順**:
```bash
# 最新の実行結果確認
aws synthetics get-canary-runs \
  --name fsxn-s3ap-s3ap-health \
  --max-results 3 \
  --region ap-northeast-1 \
  --query 'CanaryRuns[].[Status.State,Status.StateReason,Timeline.Started]' \
  --output table
```

**よくある原因と対処**:

| 原因 | 対処 |
|------|------|
| ヘルスマーカーファイル未作成 | NFS 経由で `_health/marker.txt` を作成 |
| S3 Access Point 権限不足 | Canary ロールに S3 AP 読み取り権限を追加 |
| Synthetics SDK 形式不一致 | Canary コードを Synthetics SDK 形式に書き換え |
| ランタイムバージョン廃止 | `syn-python-selenium-11.0` 以降に更新 |

### 6.3 FPolicy 接続問題

**症状**: ONTAP から FPolicy サーバーへの接続が確立されない。

**確認手順**:
```bash
# 1. ECS タスクが RUNNING か確認
aws ecs list-tasks --cluster fsxn-fpolicy-fsxn-fp-srv \
  --desired-status RUNNING --region ap-northeast-1

# 2. Security Group のインバウンドルール確認
aws ec2 describe-security-groups \
  --group-ids sg-XXXXX \
  --query 'SecurityGroups[0].IpPermissions' \
  --region ap-northeast-1

# 3. FPolicy サーバーログで接続試行を確認
aws logs filter-log-events \
  --log-group-name "/ecs/fsxn-fpolicy-server-fsxn-fp-srv" \
  --start-time $(date -d '30 minutes ago' +%s000 2>/dev/null || date -v-30M +%s000) \
  --filter-pattern "connection" \
  --region ap-northeast-1
```

**チェックリスト**:
- [ ] Fargate タスクの Private IP が ONTAP external-engine に登録されているか
- [ ] Security Group でポート 9898 (TCP) が 10.0.0.0/8 から許可されているか
- [ ] FPolicy ポリシーが `enabled` 状態か（ONTAP CLI: `fpolicy show`）
- [ ] FPolicy scope に対象ボリュームが含まれているか
- [ ] NLB 経由ではなく直接 IP で接続しているか（NLB TCP パススルーは非互換）

**ONTAP 側の確認コマンド**:

> **Note**: ONTAP 9.11+ では `vserver` プレフィックスは非推奨。以下は推奨形式。

```
# FPolicy 接続状態
fpolicy show-engine -vserver FSxN_OnPre

# FPolicy ポリシー状態
fpolicy show -vserver FSxN_OnPre

# FPolicy スコープ確認
fpolicy policy scope show -vserver FSxN_OnPre
```

---

## 7. EC2 Instance Connect 手順

NFS テスト用 EC2 インスタンスへの接続手順。SSM エージェント未インストールのため EC2 Instance Connect を使用する。

### 7.1 接続手順

```bash
# インスタンス情報
INSTANCE_ID="i-0e4c4b579d9ffbf7e"
REGION="ap-northeast-1"

# Step 1: 公開鍵をプッシュ（60秒間有効）
aws ec2-instance-connect send-ssh-public-key \
  --instance-id "$INSTANCE_ID" \
  --instance-os-user ec2-user \
  --ssh-public-key file:///Users/yoshiki/.ssh/id_rsa.pub \
  --region "$REGION"

# Step 2: 60秒以内に SSH 接続
# ※ PubkeyAcceptedKeyTypes オプションが必要（古い鍵アルゴリズム対応）
PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text --region "$REGION")

ssh -i ~/.ssh/id_rsa \
  -o StrictHostKeyChecking=no \
  -o PubkeyAcceptedKeyTypes=+ssh-rsa \
  -o HostKeyAlgorithms=+ssh-rsa \
  ec2-user@"$PUBLIC_IP"
```

### 7.2 NFS マウントとテスト

```bash
# NFS マウント（NFSv3 推奨 — NFSv4.2 は FPolicy 非サポート）
sudo mount -t nfs -o vers=3 10.0.3.133:/vol1 /mnt/fpolicy_vol

# FPolicy テスト用ファイル作成
echo "test-$(date +%s)" > /mnt/fpolicy_vol/test_fpolicy_event.txt

# ヘルスマーカーファイル作成
sudo mkdir -p /mnt/fsxn/_health
echo "health-ok" | sudo tee /mnt/fsxn/_health/marker.txt
```

### 7.3 注意事項

- EC2 Instance Connect の公開鍵は **60 秒間のみ有効**
- IAM Instance Profile なしのため SSM Session Manager は使用不可
- NFS マウントは再起動で外れる（`/etc/fstab` 未設定）
- NFSv4.2 は ONTAP FPolicy monitoring 非サポート（`vers=3` または `vers=4.1` を使用）
