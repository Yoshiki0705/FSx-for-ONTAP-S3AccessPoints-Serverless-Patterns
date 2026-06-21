# FlexCache AnyCast / DR — 運用ランブック

## FlexCache 作成

### ONTAP REST API 経由

```bash
# FlexCache 作成
curl -X POST "https://<MGMT_IP>/api/storage/flexcache/flexcaches" \
  -H "Content-Type: application/json" \
  -u "admin:password" \
  -d '{
    "name": "cache_vol_001",
    "svm": {"name": "svm1"},
    "origins": [{"volume": {"name": "origin_vol"}, "svm": {"name": "svm1"}}],
    "size": 107374182400,
    "path": "/cache_vol_001",
    "aggregates": [{"name": "aggr1"}]
  }'
```

### Lambda 経由（推奨）

```python
from shared.ontap_client import OntapClient, OntapClientConfig

config = OntapClientConfig(
    management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
    secret_name=os.environ["ONTAP_SECRET_NAME"],
)
client = OntapClient(config)
result = client.create_flexcache(
    name="cache_vol_001",
    svm_name="svm1",
    origin_volume="origin_vol",
    origin_svm="svm1",
    size_gb=100,
    junction_path="/cache_vol_001",
)
```

## FlexCache 削除

```python
# UUID で削除
client.delete_flexcache(uuid="<FLEXCACHE_UUID>")

# 名前で検索して削除
caches = client.list_flexcaches(name="cache_vol_001")
if caches:
    client.delete_flexcache(uuid=caches[0]["uuid"])
```

**注意**: 削除前にクライアントのアンマウントを確認すること。

## Cache Warm-up / Prepopulate

### Prepopulate 実行

```python
client.prepopulate_flexcache(
    uuid="<FLEXCACHE_UUID>",
    dir_paths=["/data/hot/", "/tools/v2024/"],
)
```

### Prepopulate 進捗確認

```python
job = client.get("/cluster/jobs/<JOB_UUID>")
print(f"State: {job['state']}, Progress: {job.get('description', 'N/A')}")
```

## Health Check

### 定期ヘルスチェック項目

| チェック項目 | 方法 | 閾値 |
|-------------|------|------|
| FlexCache volume state | ONTAP REST API GET /storage/volumes | state == "online" |
| Cache hit ratio | ONTAP REST API GET /storage/flexcache/flexcaches | > 70% |
| Origin 到達性 | ONTAP REST API GET /cluster/peers | state == "available" |
| S3 AP 到達性 | boto3 list_objects_v2 (MaxKeys=1) | 200 OK |
| ストレージ使用率 | ONTAP REST API GET /storage/volumes | < 85% |

### CloudWatch Logs Insights クエリ例

```sql
-- FlexCache ヘルスチェック結果の集計
fields @timestamp, @message
| filter @message like /health_status/
| parse @message '"cache_id": "*"' as cache_id
| parse @message '"status": "*"' as status
| stats count(*) by cache_id, status
| sort @timestamp desc
| limit 50
```

```sql
-- S3 AP アクセスエラーの検出
fields @timestamp, @message
| filter @message like /AccessDenied/ or @message like /timeout/
| parse @message '"s3ap_alias": "*"' as s3ap
| stats count(*) as error_count by s3ap, bin(5m)
| sort error_count desc
```

```sql
-- FlexCache 作成/削除の履歴
fields @timestamp, @message
| filter @message like /flexcache/ and (@message like /create/ or @message like /delete/)
| parse @message '"action": "*"' as action
| parse @message '"cache_name": "*"' as cache_name
| parse @message '"duration_ms": *' as duration
| sort @timestamp desc
| limit 100
```

## Stale Cache 対応

### 症状
- クライアントが古いデータを読み取る
- Origin で更新されたファイルが FlexCache に反映されない

### 対応手順

1. **キャッシュ無効化**
```python
# FlexCache の特定パスを無効化
client.post(f"/storage/flexcache/flexcaches/{uuid}/invalidate", body={
    "path": "/data/updated_dir/"
})
```

2. **TTL 確認・調整**
```bash
# ONTAP CLI 経由
ssh admin@<MGMT_IP> "volume flexcache config show -vserver svm1"
```

3. **Prepopulate で再キャッシュ**
```python
client.prepopulate_flexcache(uuid=uuid, dir_paths=["/data/updated_dir/"])
```

## Origin 到達不可時

### 検出

```python
# ヘルスチェック Lambda で検出
try:
    peers = client.get("/cluster/peers")
    for peer in peers.get("records", []):
        if peer["status"]["state"] != "available":
            # アラート発報
            send_alert(f"Cluster peer {peer['name']} is {peer['status']['state']}")
except OntapClientError as e:
    send_alert(f"Origin unreachable: {e}")
```

### 対応

1. **Disconnected mode 確認** (ONTAP 9.12.1+)
   - FlexCache は既にキャッシュ済みデータの読み取りを継続
   - 新規データの読み取りは失敗する

2. **DNS/Route 53 フェイルオーバー**
   - Route 53 ヘルスチェックが自動的にフェイルオーバー
   - 代替 Origin（SnapMirror destination）への切替

3. **通知**
   - SNS 経由で運用チームに通知
   - CloudWatch アラーム発報

## S3 AP アクセス不可時

### 原因切り分け

```python
import boto3

s3 = boto3.client("s3")
try:
    response = s3.list_objects_v2(
        Bucket="<S3_AP_ALIAS>",
        MaxKeys=1,
    )
    print("S3 AP accessible")
except s3.exceptions.ClientError as e:
    error_code = e.response["Error"]["Code"]
    if error_code == "AccessDenied":
        print("IAM policy or S3 AP resource policy issue")
    elif error_code == "NoSuchBucket":
        print("S3 AP alias incorrect or AP deleted")
    else:
        print(f"Unexpected error: {error_code}")
except Exception as e:
    print(f"Network/timeout issue: {e}")
```

### 対応

| 原因 | 対応 |
|------|------|
| IAM ポリシーエラー | ARN 形式確認、ポリシー修正 |
| S3 AP 削除 | FSx コンソールで再作成 |
| ネットワーク到達不可 | VPC 設定、セキュリティグループ確認 |
| FlexCache offline | FlexCache volume の状態確認 |

## Lambda タイムアウト

### 原因

- ONTAP REST API の応答遅延
- S3 AP のネットワーク到達性問題
- 大量データの処理

### 対応

1. Lambda タイムアウト値の確認（推奨: 60-300秒）
2. ONTAP REST API のタイムアウト設定確認
3. 処理データ量の分割（Map State の並列度調整）

## Step Functions 失敗

### リトライ設定確認

```yaml
# template.yaml の Retry 設定
States:
  HealthCheck:
    Type: Task
    Retry:
      - ErrorEquals: ["States.TaskFailed", "States.Timeout"]
        IntervalSeconds: 10
        MaxAttempts: 3
        BackoffRate: 2.0
```

### 手動再実行

```bash
# 失敗した実行の入力を取得して再実行
INPUT=$(aws stepfunctions describe-execution \
  --execution-arn <FAILED_EXECUTION_ARN> \
  --query "input" --output text)

aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input "$INPUT"
```

## Cleanup 失敗

### Orphan FlexCache 検出

```python
# 定期実行 Lambda で orphan 検出
def detect_orphan_flexcaches(client, prefix="dynamic_cache_"):
    caches = client.list_flexcaches()
    orphans = []
    for cache in caches:
        if cache["name"].startswith(prefix):
            # DynamoDB でジョブ状態を確認
            job = get_job_by_cache_name(cache["name"])
            if job is None or job["status"] in ["COMPLETED", "FAILED"]:
                # ジョブ完了/失敗なのにキャッシュが残っている
                orphans.append(cache)
    return orphans
```

### Orphan 削除

```python
for orphan in orphans:
    try:
        client.delete_flexcache(uuid=orphan["uuid"])
        logger.info(f"Deleted orphan FlexCache: {orphan['name']}")
    except OntapClientError as e:
        logger.error(f"Failed to delete orphan {orphan['name']}: {e}")
```

## コスト監視

### CloudWatch メトリクス

| メトリクス | 名前空間 | 閾値 |
|-----------|---------|------|
| FlexCache 数 | Custom/FlexCache | < 最大許容数 |
| FlexCache 合計サイズ | Custom/FlexCache | < 予算上限 |
| Orphan FlexCache 数 | Custom/FlexCache | == 0 |
| Lambda 実行回数 | AWS/Lambda | < 予算上限 |
| Step Functions 実行回数 | AWS/States | < 予算上限 |

### コストアラーム設定

```yaml
FlexCacheCostAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: FlexCache-Cost-Warning
    MetricName: FlexCacheTotalSizeGB
    Namespace: Custom/FlexCache
    Statistic: Maximum
    Period: 3600
    EvaluationPeriods: 1
    Threshold: 1000  # 1TB
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - !Ref NotificationTopic
```
