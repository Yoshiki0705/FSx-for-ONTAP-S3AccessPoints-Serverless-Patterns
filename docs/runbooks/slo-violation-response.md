# SLO Violation Response Runbook

## Overview

本ランブックは、FSxN S3AP Serverless Patterns の 4 つの SLO アラームが発報した際の初動対応手順を定義する。各アラームに対して AWS 側診断と ONTAP 側診断の両方を含む。

**対象アラーム**:
1. `fsxn-s3ap-slo-ingestion-latency` — Event Ingestion Latency (P99 > 5,000ms)
2. `fsxn-s3ap-slo-success-rate` — Processing Success Rate (< 99.5%)
3. `fsxn-s3ap-slo-reconnect-time` — FPolicy Reconnect Time (> 30s)
4. `fsxn-s3ap-slo-replay-completion` — Replay Completion Time (> 300s)

**エスカレーション基準**:
- AWS 側の問題（Lambda/Fargate/SQS/EventBridge）→ AWS Support
- ONTAP 側の問題（FPolicy/Persistent Store/SVM）→ NetApp Support
- 両方に跨る問題 → 両方に同時エスカレーション

---

## 1. EventIngestionLatency SLO Alarm

**閾値**: P99 > 5,000ms（3 連続評価期間）

### 初動確認（5 分以内）

#### AWS 側診断

```bash
# SQS メッセージ滞留確認
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessagesVisible,ApproximateAgeOfOldestMessage

# FPolicy サーバー Lambda/Fargate ログ確認（直近 30 分）
aws logs filter-log-events \
  --log-group-name /aws/ecs/${PROJECT_PREFIX}-fpolicy-server \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"

# Bridge Lambda エラー確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/${PROJECT_PREFIX}-bridge \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"
```

#### ONTAP 側診断

```bash
# FPolicy エンジン接続状態
fpolicy show-engine -vserver ${SVM_NAME}

# FPolicy イベント関連 EMS ログ
event log show -messagename *fpolicy* -time >30m

# Persistent Store キュー状態
fpolicy persistent-store show -vserver ${SVM_NAME}
```

### 判断フロー

| 症状 | 原因候補 | 対応 |
|------|---------|------|
| SQS Age > 5s, FPolicy ログ正常 | Bridge Lambda スロットリング | Lambda 同時実行数確認 |
| FPolicy ログに接続エラー | Fargate → ONTAP 接続断 | Security Group / IP 確認 |
| ONTAP EMS に disconnect | FPolicy サーバー IP 変更 | FPolicy engine IP 更新 |
| Persistent Store に大量キュー | リプレイ中 | 完了まで待機（SLO 一時的違反） |

---

## 2. ProcessingSuccessRate SLO Alarm

**閾値**: < 99.5%（3 連続評価期間）

### 初動確認（5 分以内）

#### AWS 側診断

```bash
# Step Functions 失敗実行の確認
aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --status-filter FAILED \
  --max-results 10

# 失敗実行の詳細
aws stepfunctions describe-execution \
  --execution-arn $FAILED_EXECUTION_ARN

# UC Lambda エラーログ
aws logs filter-log-events \
  --log-group-name /aws/lambda/${PROJECT_PREFIX}-${UC_ID} \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"

# Bedrock / 外部依存のスロットリング確認
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name ThrottledCount \
  --start-time $(date -d '1 hour ago' --iso-8601=seconds) \
  --end-time $(date --iso-8601=seconds) \
  --period 300 \
  --statistics Sum
```

### 判断フロー

| 症状 | 原因候補 | 対応 |
|------|---------|------|
| Step Functions FAILED | UC Lambda エラー | Lambda ログ確認 |
| Bedrock ThrottledCount > 0 | モデル呼び出し制限 | クォータ引き上げ申請 |
| S3 PutObject 失敗 | 出力先バケットポリシー | IAM / バケットポリシー確認 |
| タイムアウト | Lambda メモリ / タイムアウト不足 | 設定値引き上げ |

---

## 3. ReconnectTime SLO Alarm

**閾値**: > 30s（3 連続評価期間）

### 初動確認（5 分以内）

#### AWS 側診断

```bash
# ECS サービスイベント確認
aws ecs describe-services \
  --cluster ${ECS_CLUSTER} \
  --services ${FPOLICY_SERVICE} \
  --query 'services[0].events[:10]'

# Fargate タスク状態確認
aws ecs list-tasks \
  --cluster ${ECS_CLUSTER} \
  --service-name ${FPOLICY_SERVICE}

aws ecs describe-tasks \
  --cluster ${ECS_CLUSTER} \
  --tasks $TASK_ARN

# FPolicy サーバーログ（再接続関連）
aws logs filter-log-events \
  --log-group-name /aws/ecs/${PROJECT_PREFIX}-fpolicy-server \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "NEGO_REQ OR reconnect OR disconnect"
```

#### ONTAP 側診断

```bash
# FPolicy エンジン接続状態
fpolicy show-engine -vserver ${SVM_NAME}

# FPolicy ポリシー状態
fpolicy show -vserver ${SVM_NAME} -fields policy-name,status

# ネットワーク接続テスト
network ping -node ${NODE_NAME} -destination ${FARGATE_IP}
```

### 判断フロー

| 症状 | 原因候補 | 対応 |
|------|---------|------|
| タスク STOPPED → 新タスク起動中 | Fargate タスク再起動 | IP 更新待ち |
| タスク RUNNING だが接続なし | Security Group 変更 | SG ルール確認 |
| ONTAP 側 disconnect | FPolicy engine IP 不一致 | `fpolicy policy external-engine modify` |
| ネットワーク ping 失敗 | サブネット / ルーティング | VPC 設定確認 |

---

## 4. ReplayCompletionTime SLO Alarm

**閾値**: > 300s（3 連続評価期間）

### 初動確認（5 分以内）

#### AWS 側診断

```bash
# SQS バックログ確認
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessagesVisible

# FPolicy サーバーログ（リプレイ関連）
aws logs filter-log-events \
  --log-group-name /aws/ecs/${PROJECT_PREFIX}-fpolicy-server \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "replay OR NOTI_REQ"
```

#### ONTAP 側診断

```bash
# Persistent Store 状態
fpolicy persistent-store show -vserver ${SVM_NAME}

# Persistent Store ボリューム使用量
volume show -volume ${PERSISTENT_STORE_VOLUME} -fields used,available,percent-used

# FPolicy イベントキュー
fpolicy show-engine -vserver ${SVM_NAME} -fields outstanding-requests
```

### 判断フロー

| 症状 | 原因候補 | 対応 |
|------|---------|------|
| SQS バックログ大 + リプレイ中 | 大量イベントリプレイ | 完了まで待機 |
| Persistent Store 容量不足 | ストアボリューム満杯 | ボリューム拡張 |
| リプレイスループット低下 | FPolicy サーバー CPU/メモリ | Fargate タスクサイズ引き上げ |
| outstanding-requests 高 | ONTAP 側キュー滞留 | NetApp Support エスカレーション |

---

## Diagnostic Bundle Collection Script

障害時に以下のスクリプトで診断情報を一括収集する：

```bash
#!/bin/bash
# Usage: ./scripts/collect_diagnostic_bundle.sh
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/diagnostic_bundle_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "Collecting diagnostic bundle..."

# CloudWatch Logs (last 30 min)
aws logs filter-log-events \
  --log-group-name /aws/ecs/${PROJECT_PREFIX}-fpolicy-server \
  --start-time $(date -d '30 minutes ago' +%s000) \
  > "$OUTPUT_DIR/fpolicy_server_logs.json" 2>/dev/null || true

# SQS Metrics
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names All \
  > "$OUTPUT_DIR/sqs_attributes.json" 2>/dev/null || true

# CloudWatch Alarm States
aws cloudwatch describe-alarms \
  --alarm-name-prefix "${PROJECT_PREFIX}-slo-" \
  > "$OUTPUT_DIR/slo_alarm_states.json" 2>/dev/null || true

# ECS Service Status
aws ecs describe-services \
  --cluster ${ECS_CLUSTER} \
  --services ${FPOLICY_SERVICE} \
  > "$OUTPUT_DIR/ecs_service.json" 2>/dev/null || true

# Package
tar -czf "${OUTPUT_DIR}.tar.gz" -C /tmp "diagnostic_bundle_${TIMESTAMP}"
echo "Bundle: ${OUTPUT_DIR}.tar.gz"
echo ""
echo "ONTAP CLI commands (run manually on FSx ONTAP CLI):"
echo "  fpolicy show -vserver ${SVM_NAME} -fields policy-name,status"
echo "  fpolicy show-engine -vserver ${SVM_NAME}"
echo "  fpolicy persistent-store show -vserver ${SVM_NAME}"
echo "  event log show -messagename *fpolicy* -time >30m"
```

---

## Escalation Contacts

| 問題領域 | エスカレーション先 | 情報提供 |
|---------|-----------------|---------|
| AWS サービス障害 | AWS Support (Business/Enterprise) | Diagnostic Bundle + アラーム状態 |
| ONTAP FPolicy 問題 | NetApp Support | EMS ログ + FPolicy 状態 + SVM 情報 |
| ネットワーク接続 | AWS + NetApp 両方 | VPC 設定 + Security Group + ONTAP ネットワーク |
| パフォーマンス劣化 | AWS (Fargate/Lambda) + NetApp (ONTAP) | メトリクス + ログ + 構成情報 |

---

## Common Pitfalls (Phase 13 で発見)

### fsxadmin が "User is not authorized" を返す

**原因**: SVM 管理 IP に接続している。fsxadmin はファイルシステム管理 IP でのみ認証可能。

```bash
# 正しい管理 IP を確認
aws fsx describe-file-systems --file-system-ids $FSX_FILE_SYSTEM_ID \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]' --output text
```

### S3AP が ConnectionClosedError を返す

**原因**: S3AP リソースポリシー未設定、または ONTAP データプレーン応答なし。

診断順序:
1. S3AP リソースポリシーに Lambda ロールが Allow されているか
2. S3AP attachment lifecycle が AVAILABLE か
3. ONTAP REST API (`GET /api/cluster`) が応答するか
4. 対象ボリュームが online か

### FlexClone 作成で "nas.security_style is not valid" エラー

**原因**: ONTAP REST API では FlexClone 作成時に `nas.security_style` を指定できない（親ボリュームから継承）。

**対応**: Lambda コードから `security_style` フィールドを削除する。
