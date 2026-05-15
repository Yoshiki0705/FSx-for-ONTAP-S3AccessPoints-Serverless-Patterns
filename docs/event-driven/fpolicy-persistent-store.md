# FPolicy Persistent Store 設定 + イベントロスゼロ検証

## 概要

ONTAP 9.14.1+ の **Persistent Store** 機能は、FPolicy サーバー（ECS Fargate タスク）が切断された場合にイベントを SVM ボリュームに永続化し、再接続時に順番に送信する。これにより、Fargate タスクの再起動やスケーリング時のイベントロスをゼロにする。

## 前提条件

- ONTAP バージョン: 9.14.1+ (現在: 9.17.1P6 ✅)
- FPolicy ポリシーモード: `asynchronous` (非同期、non-mandatory)
- SVM: FSxN_OnPre (UUID: 9ae87e42-068a-11f1-b1ff-ada95e61ee66)
- 管理 IP: 10.0.3.72

## アーキテクチャ

```
                    ┌─────────────────────────────────────────┐
                    │              ONTAP SVM                   │
                    │                                         │
                    │  File Operation → FPolicy Engine        │
                    │                      │                  │
                    │         ┌────────────┼────────────┐     │
                    │         │            │            │     │
                    │         ▼            ▼            │     │
                    │  [Server Online]  [Server Offline]│     │
                    │         │            │            │     │
                    │         ▼            ▼            │     │
                    │    TCP Send    Persistent Store   │     │
                    │         │       (Volume)         │     │
                    │         │            │            │     │
                    │         │     [Server Reconnect] │     │
                    │         │            │            │     │
                    │         │            ▼            │     │
                    │         │      Replay Events     │     │
                    │         │            │            │     │
                    │         └────────────┼────────────┘     │
                    │                      │                  │
                    └──────────────────────┼──────────────────┘
                                           │
                                           ▼
                              ECS Fargate (FPolicy Server)
                                           │
                                           ▼
                                    SQS → EventBridge
```

## 設定手順

### 1. Persistent Store 用ボリューム作成

```bash
# ONTAP REST API: ボリューム作成
curl -k -u fsxadmin:PASSWORD \
  -X POST "https://10.0.3.72/api/storage/volumes" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_persistent_store",
    "svm": {"uuid": "9ae87e42-068a-11f1-b1ff-ada95e61ee66"},
    "aggregates": [{"name": "aggr1"}],
    "size": "1GB",
    "type": "rw",
    "nas": {
      "path": "/fpolicy_persistent_store",
      "security_style": "unix"
    },
    "guarantee": {"type": "none"},
    "comment": "FPolicy Persistent Store volume for event buffering"
  }'
```

### 2. Persistent Store 作成

```bash
# ONTAP REST API: Persistent Store 作成
curl -k -u fsxadmin:PASSWORD \
  -X POST "https://10.0.3.72/api/protocols/fpolicy/9ae87e42-068a-11f1-b1ff-ada95e61ee66/persistent-stores" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_aws_store",
    "volume": "fpolicy_persistent_store",
    "autoflush_enabled": true,
    "autoflush_interval": "PT120S"
  }'
```

### 3. FPolicy ポリシーに Persistent Store を関連付け

```bash
# ONTAP REST API: ポリシー更新
curl -k -u fsxadmin:PASSWORD \
  -X PATCH "https://10.0.3.72/api/protocols/fpolicy/9ae87e42-068a-11f1-b1ff-ada95e61ee66/policies/fpolicy_aws" \
  -H "Content-Type: application/json" \
  -d '{
    "persistent_store": "fpolicy_aws_store"
  }'
```

### 4. 設定確認

```bash
# Persistent Store 確認
curl -k -u fsxadmin:PASSWORD \
  "https://10.0.3.72/api/protocols/fpolicy/9ae87e42-068a-11f1-b1ff-ada95e61ee66/persistent-stores"

# ポリシー確認
curl -k -u fsxadmin:PASSWORD \
  "https://10.0.3.72/api/protocols/fpolicy/9ae87e42-068a-11f1-b1ff-ada95e61ee66/policies/fpolicy_aws"
```

## イベントロスゼロ検証手順

### テストシナリオ

1. **正常時**: ファイル作成 → FPolicy Server 受信 → SQS 到達確認
2. **タスク停止時**: ファイル作成 → Persistent Store 蓄積確認
3. **タスク再起動後**: Persistent Store → FPolicy Server → SQS 到達確認
4. **全イベント到達確認**: 作成ファイル数 = SQS メッセージ数

### 検証スクリプト

```bash
#!/bin/bash
# fpolicy-persistent-store-test.sh
# イベントロスゼロ検証

set -euo pipefail

SQS_QUEUE_URL="https://sqs.ap-northeast-1.amazonaws.com/178625946981/fsxn-fpolicy-ingestion-fsxn-fpolicy-ingestion"
ECS_CLUSTER="fsxn-fpolicy-fsxn-fp-srv"
ECS_SERVICE="fsxn-fpolicy-fpolicy-service"
TEST_DIR="/vol1/test_persistent_store"
TOTAL_FILES=50

echo "=== Phase 1: 正常時のベースライン ==="
# SQS キューを空にする
aws sqs purge-queue --queue-url "$SQS_QUEUE_URL"
sleep 5

# 10 ファイル作成（正常時）
for i in $(seq 1 10); do
  # NFS/SMB 経由でファイル作成
  echo "test content $i" > "${TEST_DIR}/normal_${i}.txt"
done
sleep 30

# SQS メッセージ数確認
NORMAL_COUNT=$(aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query "Attributes.ApproximateNumberOfMessages" --output text)
echo "正常時: ${NORMAL_COUNT}/10 メッセージ受信"

echo ""
echo "=== Phase 2: Fargate タスク停止 ==="
# ECS タスクを強制停止
TASK_ARN=$(aws ecs list-tasks --cluster "$ECS_CLUSTER" --service-name "$ECS_SERVICE" \
  --query "taskArns[0]" --output text)
aws ecs stop-task --cluster "$ECS_CLUSTER" --task "$TASK_ARN" --reason "Persistent Store test"
echo "タスク停止: $TASK_ARN"
sleep 10

echo ""
echo "=== Phase 3: タスク停止中にファイル作成 ==="
aws sqs purge-queue --queue-url "$SQS_QUEUE_URL"
sleep 5

for i in $(seq 1 $TOTAL_FILES); do
  echo "persistent store test $i" > "${TEST_DIR}/offline_${i}.txt"
done
echo "${TOTAL_FILES} ファイル作成完了（タスク停止中）"

echo ""
echo "=== Phase 4: タスク再起動待機 ==="
# ECS サービスが新しいタスクを起動するのを待つ
aws ecs wait tasks-running --cluster "$ECS_CLUSTER" \
  --tasks $(aws ecs list-tasks --cluster "$ECS_CLUSTER" --service-name "$ECS_SERVICE" \
    --query "taskArns[0]" --output text)
echo "新しいタスク起動完了"

# Persistent Store のリプレイを待つ（最大 5 分）
echo "Persistent Store リプレイ待機中..."
sleep 300

echo ""
echo "=== Phase 5: イベント到達確認 ==="
FINAL_COUNT=$(aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --query "Attributes.ApproximateNumberOfMessages" --output text)

echo "結果: ${FINAL_COUNT}/${TOTAL_FILES} メッセージ受信"
if [ "$FINAL_COUNT" -ge "$TOTAL_FILES" ]; then
  echo "✅ イベントロスゼロ検証: PASS"
else
  echo "❌ イベントロスゼロ検証: FAIL (${FINAL_COUNT}/${TOTAL_FILES})"
  exit 1
fi
```

## 設定パラメータ

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| ボリューム名 | `fpolicy_persistent_store` | Persistent Store 用ボリューム |
| ボリュームサイズ | 1 GB | イベントバッファ用（1イベント ~500B × 200万イベント） |
| Store 名 | `fpolicy_aws_store` | Persistent Store 名 |
| autoflush_enabled | true | 自動フラッシュ有効 |
| autoflush_interval | PT120S (2分) | フラッシュ間隔 |

## 容量見積もり

Persistent Store のボリュームサイズは以下の式で見積もる:

```
required_size = event_rate_per_sec × max_outage_duration_sec × avg_event_size_bytes × safety_factor
```

### 見積もり例

| シナリオ | イベント/秒 | 停止時間 | イベントサイズ | 安全係数 | 必要容量 |
|---------|-----------|---------|-------------|---------|---------|
| 低負荷（開発） | 10 | 300s | 500B | 2.0 | 3 MB |
| 中負荷（本番） | 100 | 300s | 500B | 2.0 | 30 MB |
| 高負荷（大規模） | 1000 | 600s | 500B | 2.0 | 600 MB |
| 極高負荷 | 5000 | 600s | 500B | 2.0 | 3 GB |

Phase 11 で設定した 1 GB は中〜高負荷環境に対応（約 200 万イベントバッファ可能）。

> **注意**: 上記の 200 万は raw 容量。safety_factor=2.0 を適用した場合の実用計画容量は約 100 万イベントとして設計すること。

## 注意事項

1. **ボリュームサイズ**: Persistent Store のボリュームサイズは、タスク停止中に蓄積されるイベント量に応じて設定する。1GB で約 200 万イベントをバッファ可能。

2. **autoflush_interval**: サーバー再接続後、この間隔でバッファされたイベントがフラッシュされる。短すぎるとパフォーマンスに影響、長すぎるとリプレイ遅延が発生。

3. **順序保証**: Persistent Store はイベントの順序を保証する。リプレイ時も元の発生順序で送信される。

4. **非同期モード限定**: Persistent Store は `asynchronous` (non-mandatory) ポリシーでのみ使用可能。`synchronous` (mandatory) ポリシーではサーバー切断時にファイル操作がブロックされる。

5. **ディスク使用量監視**: Persistent Store ボリュームの使用率を CloudWatch カスタムメトリクスで監視し、80% 超過時にアラートを設定することを推奨。

## Phase 11 検証状態

| 項目 | 状態 | 備考 |
|------|------|------|
| Persistent Store ボリューム作成 | ✅ 完了 | fpolicy_persistent_store (1GB) |
| Persistent Store 作成 | ✅ 完了 | fpolicy_aws_store |
| ポリシー関連付け | ✅ 完了 | fpolicy_aws → fpolicy_aws_store |
| ポリシー再有効化 | ✅ 完了 | enabled=true, persistent_store=fpolicy_aws_store |
| イベントロスゼロ検証 | 📋 テスト手順準備済み | NFS/SMB マウント環境からの実行が必要 |

### 実行ログ

```
# Step 1: ボリューム作成
POST /api/storage/volumes → 202 (job: 8d368e7f-4fc0-11f1-9530-a1411a1e7d1e)
Job status: success (3秒で完了)

# Step 2: Persistent Store 作成
POST /api/protocols/fpolicy/{svm}/persistent-stores → 201 Created
  name: fpolicy_aws_store
  volume: fpolicy_persistent_store

# Step 3: ポリシー無効化 → 関連付け → 再有効化
PATCH /api/protocols/fpolicy/{svm}/policies/fpolicy_aws (enabled: false) → 200
PATCH /api/protocols/fpolicy/{svm}/policies/fpolicy_aws (persistent_store: fpolicy_aws_store) → 200
PATCH /api/protocols/fpolicy/{svm}/policies/fpolicy_aws (enabled: true, priority: 1) → 200

# 確認
GET /api/protocols/fpolicy/{svm}/policies/fpolicy_aws?fields=persistent_store,enabled
  → enabled: true, persistent_store: "fpolicy_aws_store"
```

## 参考リンク

- [ONTAP 9.14.1: FPolicy Persistent Store](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
- [ONTAP REST API: Persistent Stores](https://docs.netapp.com/us-en/ontap-restapi/ontap/protocols_fpolicy_svm.uuid_persistent-stores_endpoint_overview.html)
- [FPolicy Asynchronous Mode](https://docs.netapp.com/us-en/ontap/nas-audit/synchronous-asynchronous-notifications-concept.html)


## Replay Throughput Sizing

容量だけでなく、「再接続後に何分で追いつくか」を設計する必要がある。

### 計算式

```
replay_recovery_time = buffered_events / sustainable_processing_rate
```

### 見積もり例

| バッファ済みイベント | 処理レート | リカバリ時間 |
|-------------------|-----------|------------|
| 10,000 | 100 events/sec | 100 秒 (< 2 分) |
| 100,000 | 100 events/sec | 1,000 秒 (≈ 17 分) |
| 1,000,000 | 100 events/sec | 10,000 秒 (≈ 2.8 時間) |
| 100,000 | 500 events/sec | 200 秒 (≈ 3 分) |

### Sustainable Processing Rate の制約要因

replay 時のスループットは以下のボトルネックで決まる:

1. **FPolicy Server**: TCP 受信 + SQS 送信の処理能力
2. **SQS**: SendMessage レート（リージョン制限: 3,000 msg/sec per queue）
3. **Bridge Lambda**: SQS → EventBridge の変換レート
4. **EventBridge**: PutEvents レート（10,000 entries/sec per account）
5. **Step Functions**: StartExecution レート（デフォルト 2,000/sec）
6. **DynamoDB**: Idempotency Store の書き込みキャパシティ
7. **Downstream Lambda**: 各 UC の処理能力

### Phase 12 Replay Storm Test メトリクス

| メトリクス | 測定方法 |
|-----------|---------|
| Buffered event count | ONTAP REST API: Persistent Store status |
| Replay duration | FPolicy Server ログ: 最初のreplayイベント〜最後のreplayイベント |
| Replay events/sec | SQS SendMessage count / replay duration |
| SQS backlog age | CloudWatch: ApproximateAgeOfOldestMessage |
| Step Functions concurrency | CloudWatch: ExecutionsStarted per minute |
| DynamoDB conditional write failures | CloudWatch: ConditionalCheckFailedRequests |
| ECS CPU/Memory | Container Insights |
| Downstream throttling | Lambda Throttles metric |
