# FlexCache AnyCast / DR — デモガイド

## 前提条件

- AWS アカウント（CloudFormation デプロイ権限）
- Python 3.12
- AWS CLI v2
- SAM CLI（オプション）

## Demo 1: Static FlexCache + S3 AP Analytics

### 目的
FlexCache volume に S3 AP を attach し、Lambda 経由でデータ分析を実行するデモ。

### 手順

1. **FlexCache 作成**（ONTAP REST API 経由）
```bash
# Lambda 経由で FlexCache 作成をシミュレーション
aws lambda invoke \
  --function-name flexcache-anycast-CreateFlexCache \
  --payload '{"origin_volume": "vol1", "cache_name": "cache_demo1", "size_gb": 100}' \
  response.json
cat response.json
```

2. **S3 AP 経由でデータ確認**
```bash
# S3 AP エイリアスを使用して ListObjectsV2
aws s3api list-objects-v2 \
  --bucket "<S3_AP_ALIAS>" \
  --prefix "data/" \
  --max-keys 10
```

3. **Step Functions 実行**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{"mode": "static_cache_analytics", "s3ap_alias": "<S3_AP_ALIAS>", "prefix": "data/"}'
```

4. **結果確認**
```bash
# 実行結果を確認
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN>
```

### 期待される結果
- FlexCache volume 経由で S3 AP アクセスが成功
- Discovery → Processing → Report の全ステップが成功
- レポートが S3 出力バケットに生成

---

## Demo 2: FlexCache Health Check + Serverless Report

### 目的
複数の FlexCache ノードのヘルスチェックを実行し、レポートを生成するデモ。

### 手順

1. **ヘルスチェック実行**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input file://events/sample-cache-health-event.json
```

2. **ヘルスチェック結果確認**
```bash
# CloudWatch Logs でヘルスチェック結果を確認
aws logs filter-log-events \
  --log-group-name "/aws/lambda/flexcache-anycast-HealthCheck" \
  --start-time $(date -d '5 minutes ago' +%s000) \
  --filter-pattern "health_status"
```

3. **レポート確認**
```bash
# S3 出力バケットのレポートを確認
aws s3 ls s3://<OUTPUT_BUCKET>/health-reports/ --recursive
aws s3 cp s3://<OUTPUT_BUCKET>/health-reports/latest.json -
```

### 期待される結果
- 各キャッシュノードのヘルスステータスが取得される
- JSON レポートが生成される
- 異常検出時は SNS 通知が送信される

### シミュレーションモード
実環境の FlexCache がない場合、`SimulationMode=true` で以下をシミュレーション:
- キャッシュノードの応答時間
- Cache hit ratio
- ストレージ使用率
- ネットワーク到達性

---

## Demo 3: Simulated AnyCast Route Decision

### 目的
BGP/VIP が使えない環境で、Lambda によるルート判定ロジックをデモ。

### 手順

1. **ルーティングテーブル初期化**
```bash
# DynamoDB にルーティングテーブルを作成
aws dynamodb put-item \
  --table-name FlexCacheRoutingTable \
  --item '{
    "cache_id": {"S": "cache-a"},
    "endpoint": {"S": "fsxn-cache-a.example.com"},
    "region": {"S": "ap-northeast-1"},
    "weight": {"N": "70"},
    "health": {"S": "healthy"},
    "latency_ms": {"N": "5"}
  }'

aws dynamodb put-item \
  --table-name FlexCacheRoutingTable \
  --item '{
    "cache_id": {"S": "cache-b"},
    "endpoint": {"S": "fsxn-cache-b.example.com"},
    "region": {"S": "us-west-2"},
    "weight": {"N": "30"},
    "health": {"S": "healthy"},
    "latency_ms": {"N": "45"}
  }'
```

2. **ルート判定実行**
```bash
aws lambda invoke \
  --function-name flexcache-anycast-RouteDecision \
  --payload '{"client_region": "ap-northeast-1", "strategy": "latency_based"}' \
  response.json
cat response.json
# 期待: cache-a が選択される（低レイテンシ）
```

3. **重み付きルーティング**
```bash
aws lambda invoke \
  --function-name flexcache-anycast-RouteDecision \
  --payload '{"client_region": "ap-northeast-1", "strategy": "weighted"}' \
  response.json
cat response.json
# 期待: 70% の確率で cache-a、30% で cache-b
```

4. **障害時のルーティング**
```bash
# cache-a を unhealthy に変更
aws dynamodb update-item \
  --table-name FlexCacheRoutingTable \
  --key '{"cache_id": {"S": "cache-a"}}' \
  --update-expression "SET health = :h" \
  --expression-attribute-values '{":h": {"S": "unhealthy"}}'

# ルート判定再実行
aws lambda invoke \
  --function-name flexcache-anycast-RouteDecision \
  --payload '{"client_region": "ap-northeast-1", "strategy": "latency_based"}' \
  response.json
cat response.json
# 期待: cache-b が選択される（cache-a は unhealthy）
```

### 期待される結果
- レイテンシベースで最適なキャッシュが選択される
- 重み付きで確率的にキャッシュが選択される
- 障害ノードは自動的に除外される

---

## Demo 4: DR/Failover Simulation

### 目的
Origin 障害時のフェイルオーバーをシミュレーションするデモ。

### 手順

1. **正常状態の確認**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{"action": "check_origin_health"}'
# 期待: Origin healthy, FlexCache connected
```

2. **Origin 障害シミュレーション**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input file://events/sample-failover-event.json
```

`events/sample-failover-event.json`:
```json
{
  "action": "simulate_failover",
  "scenario": "origin_unreachable",
  "origin_endpoint": "fsxn-origin.example.com",
  "cache_endpoints": ["fsxn-cache-a.example.com", "fsxn-cache-b.example.com"],
  "failover_strategy": "dns_failover",
  "notify": true
}
```

3. **フェイルオーバー結果確認**
```bash
# Step Functions 実行結果
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN>

# SNS 通知確認（メール）
# Route 53 レコード変更確認
aws route53 list-resource-record-sets \
  --hosted-zone-id <ZONE_ID> \
  --query "ResourceRecordSets[?Name=='data.example.com.']"
```

4. **フェイルバック**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{"action": "failback", "origin_endpoint": "fsxn-origin.example.com"}'
```

### 期待される結果
- Origin 障害検出 → DNS 切替 → キャッシュ経由読み取り継続
- SNS 通知が送信される
- フェイルバック後に正常状態に復帰

---

## Demo 5: Media/VFX Render Input Cache Acceleration

### 目的
レンダリングジョブの入力データを FlexCache で高速化するデモ。

### 手順

1. **レンダリングジョブリクエスト**
```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{
    "action": "render_job",
    "job_id": "render-001",
    "project": "movie-xyz",
    "input_path": "/vol/assets/scene01/",
    "frame_range": "1-100",
    "resolution": "4K",
    "cache_strategy": "prepopulate"
  }'
```

2. **FlexCache 作成と Prepopulate**
```bash
# Step Functions が自動実行:
# 1. FlexCache 作成 (ONTAP REST API)
# 2. Prepopulate (input_path のデータをキャッシュ)
# 3. レンダリングジョブ投入（モック）
# 4. ジョブ完了待ち
# 5. S3 AP 経由でメタデータ/QC 実行
# 6. FlexCache 削除
```

3. **進捗確認**
```bash
# 実行中のステート確認
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN> \
  --query "status"
```

4. **結果確認**
```bash
# レンダリング結果レポート
aws s3 cp s3://<OUTPUT_BUCKET>/render-reports/render-001.json -
```

### 期待される結果
- FlexCache が自動作成される
- Prepopulate でレンダリング入力データがキャッシュされる
- モックレンダリングジョブが完了する
- S3 AP 経由で QC/メタデータ処理が実行される
- FlexCache が自動削除される

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Lambda タイムアウト | ONTAP REST API 到達不可 | VPC 設定確認、セキュリティグループ確認 |
| S3 AP AccessDenied | IAM ARN 形式エラー | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用 |
| FlexCache 作成失敗 | アグリゲート容量不足 | ストレージ容量確認、サイズ調整 |
| ヘルスチェック失敗 | ネットワーク到達性 | セキュリティグループ、ルートテーブル確認 |
| Step Functions 失敗 | Lambda エラー | CloudWatch Logs で詳細確認 |


## スクリーンショット

![Phase 13 — CloudFormation Stacks](../../docs/screenshots/masked/phase13-cloudformation-stacks.png)
![Phase 13 — Lambda Functions](../../docs/screenshots/masked/phase13-lambda-functions.png)
