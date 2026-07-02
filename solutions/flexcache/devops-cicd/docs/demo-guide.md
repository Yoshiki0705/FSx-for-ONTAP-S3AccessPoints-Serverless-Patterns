# FC7 デモガイド: DevOps FlexClone + S3AP

## 前提条件

- FSx for ONTAP ファイルシステム（稼働中）
- S3 Access Point が設定済み
- AWS SAM CLI インストール済み
- ONTAP 管理認証情報が Secrets Manager に保存済み

## Step 1: デプロイ（シミュレーションモード）

```bash
cd solutions/flexcache/devops-cicd

# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build
sam deploy \
  --stack-name devops-flexclone-cicd-demo \
  --parameter-overrides \
    OntapManagementIp=10.0.1.100 \
    OntapSecretName=fsxn/ontap-credentials \
    SvmName=svm1 \
    SourceVolumeName=production_data \
    ClonePrefix=demo_clone \
    TtlHours=2 \
    SimulationMode=true \
  --capabilities CAPABILITY_IAM \
  --resolve-s3
```

## Step 2: FlexClone 作成テスト

```bash
# Step Functions を手動実行
aws stepfunctions start-execution \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name devops-flexclone-cicd-demo \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text) \
  --input '{
    "source_volume": "production_data",
    "ttl_hours": 2,
    "requester": "demo-user",
    "test_suite": "integration",
    "test_config": {
      "data_prefix": "testdata/",
      "validation_rules": ["schema", "completeness", "freshness"]
    },
    "pipeline_run_id": "demo-run-001"
  }'
```

## Step 3: 実行結果確認

```bash
# 最新の実行を取得
EXECUTION_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name devops-flexclone-cicd-demo \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text) \
  --max-results 1 \
  --query "executions[0].executionArn" --output text)

# 状態を確認
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN \
  --query '[status, output]'
```

期待される出力（シミュレーション）:
```json
{
  "status": "success",
  "clone_name": "demo_clone_1717776000",
  "test_results": {
    "suite": "integration",
    "total_tests": 30,
    "passed": 30,
    "failed": 0
  },
  "ready_for_cleanup": true,
  "simulation": true
}
```

## Step 4: TTL Sweep テスト

```bash
# Cleanup Lambda を直接呼び出し
aws lambda invoke \
  --function-name devops-flexclone-cicd-demo-CleanupFunction \
  --payload '{"mode": "ttl_sweep"}' \
  /dev/stdout
```

## Step 5: GitHub Actions 統合（オプション）

`.github/workflows/test-with-clone.yml`:
```yaml
name: Integration Test with FlexClone
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@ff717079ee2060e4bcee96c4779b553acc87447c # v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ap-northeast-1

      - name: Start FlexClone provisioning
        id: clone
        run: |
          EXECUTION_ARN=$(aws stepfunctions start-execution \
            --state-machine-arn ${{ secrets.STATE_MACHINE_ARN }} \
            --input '{"source_volume": "testdata_master", "test_suite": "integration", "pipeline_run_id": "${{ github.run_id }}"}' \
            --query 'executionArn' --output text)
          echo "execution_arn=$EXECUTION_ARN" >> $GITHUB_OUTPUT

      - name: Wait for completion
        run: |
          aws stepfunctions wait execution-complete \
            --execution-arn ${{ steps.clone.outputs.execution_arn }} || true
          STATUS=$(aws stepfunctions describe-execution \
            --execution-arn ${{ steps.clone.outputs.execution_arn }} \
            --query 'status' --output text)
          if [ "$STATUS" != "SUCCEEDED" ]; then exit 1; fi
```

## クリーンアップ

```bash
sam delete --stack-name devops-flexclone-cicd-demo
```

## トラブルシューティング

| 問題 | 原因 | 解決策 |
|------|------|--------|
| Clone Manager タイムアウト | ONTAP 管理 IP へのアクセス不可 | Lambda が VPC 内に配置されているか確認 |
| S3AP アクセス拒否 | IAM ポリシーの ARN 形式エラー | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を確認 |
| テスト結果が空 | S3AP alias が間違い | S3AP Provisioner の出力を確認 |
| TTL Sweep が0件削除 | クローンが存在しない | Clone prefix とクローン一覧を確認 |
