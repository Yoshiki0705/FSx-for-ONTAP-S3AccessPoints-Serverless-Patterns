# Dynamic FlexCache Render/EDA Workflow — デモガイド

## 前提条件

- AWS アカウント（CloudFormation デプロイ権限）
- Python 3.12
- AWS CLI v2

## Demo 1: レンダリングジョブ（シミュレーションモード）

### デプロイ

```bash
aws cloudformation deploy \
  --template-file dynamic-flexcache-render-workflow/template.yaml \
  --stack-name dynamic-flexcache-demo \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    OntapManagementIp=10.0.0.1 \
    OntapSecretName=fsxn/ontap-credentials \
    OriginSvmName=svm1 \
    OriginVolumeName=render_assets \
    CacheSvmName=svm1 \
    SimulationMode=true
```

### ジョブ投入

```bash
aws stepfunctions start-execution \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name dynamic-flexcache-demo \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text) \
  --input file://dynamic-flexcache-render-workflow/events/sample-render-job-request.json
```

### 実行確認

```bash
# 実行状態を確認（30秒後に SUCCEEDED になる）
aws stepfunctions describe-execution \
  --execution-arn <EXECUTION_ARN> \
  --query "{status: status, startDate: startDate, stopDate: stopDate}"
```

### 期待される結果

1. CreateFlexCache: `status: created` (シミュレーション)
2. SubmitJob: `status: submitted`
3. MonitorJob: 数回ポーリング後に `SUCCEEDED`
4. CleanupFlexCache: `status: deleted`
5. Report: S3 にレポート出力

---

## Demo 2: EDA ジョブ（シミュレーションモード）

```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input file://dynamic-flexcache-render-workflow/events/sample-eda-job-request.json
```

EDA ジョブは `simulate_duration_seconds: 60` のため、約 60 秒後に完了。

---

## Demo 3: ジョブ失敗シミュレーション

```bash
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{
    "job_id": "fail-test-001",
    "job_type": "render",
    "project": "test",
    "origin_volume": "assets",
    "origin_svm": "svm1",
    "cache_svm": "svm1",
    "size_gb": 100,
    "prepopulate_dirs": [],
    "parameters": {
      "simulate_failure": true,
      "simulate_duration_seconds": 15
    }
  }'
```

### 期待される結果

1. CreateFlexCache: 成功
2. SubmitJob: 成功
3. MonitorJob: `FAILED` を返す
4. CleanupFlexCache: **失敗時も FlexCache を削除**（`CleanupOnFailure=true`）
5. Report: 失敗レポート + SNS 通知

---

## Demo 4: Orphan FlexCache 検出

```bash
# 手動で orphan 状態を作成（cleanup をスキップ）
# → 定期実行の orphan 検出 Lambda で検出される

# CloudWatch Logs で orphan 検出ログを確認
aws logs filter-log-events \
  --log-group-name "/aws/lambda/dynamic-flexcache-CleanupFlexCache" \
  --filter-pattern "orphan" \
  --start-time $(date -v-1H +%s000)
```

---

## Demo 5: 実環境接続（SimulationMode=false）

> **注意**: 実環境の ONTAP REST API に接続するため、事前に以下を確認:
> - ONTAP 管理 IP への到達性
> - Secrets Manager にONTAP認証情報が保存済み
> - FlexCache 作成に十分なアグリゲート容量

```bash
aws cloudformation deploy \
  --template-file dynamic-flexcache-render-workflow/template.yaml \
  --stack-name dynamic-flexcache-real \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    OntapManagementIp=<REAL_MGMT_IP> \
    OntapSecretName=fsxn/ontap-credentials \
    OriginSvmName=svm1 \
    OriginVolumeName=render_assets \
    CacheSvmName=svm1 \
    CacheAggregateName=aggr1 \
    SimulationMode=false
```

## トラブルシューティング

| 症状 | 確認ポイント |
|------|------------|
| CreateFlexCache タイムアウト | Lambda タイムアウト値（300秒推奨）、ONTAP 管理 IP 到達性 |
| MonitorJob が終わらない | `expected_completion_at` が未来すぎないか確認 |
| Cleanup 失敗 | ONTAP REST API エラーログ確認、volume busy でないか確認 |
| レポートが S3 にない | OUTPUT_BUCKET 環境変数、IAM ポリシー確認 |
