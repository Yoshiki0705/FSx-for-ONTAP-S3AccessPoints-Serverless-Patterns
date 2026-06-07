# UC29 Demo Guide: DevOps FlexClone + S3AP

## Prerequisites

- FSx for ONTAP file system (running)
- S3 Access Point configured
- AWS SAM CLI installed
- ONTAP management credentials stored in Secrets Manager

## Step 1: Deploy (Simulation Mode)

```bash
cd devops-flexclone-cicd

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

## Step 2: Test FlexClone Creation

```bash
# Manually execute the Step Functions state machine
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

## Step 3: Check Execution Results

```bash
# Get the latest execution
EXECUTION_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name devops-flexclone-cicd-demo \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text) \
  --max-results 1 \
  --query "executions[0].executionArn" --output text)

# Check status
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN \
  --query '[status, output]'
```

Expected output (simulation):
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

## Step 4: Test TTL Sweep

```bash
# Invoke Cleanup Lambda directly
aws lambda invoke \
  --function-name devops-flexclone-cicd-demo-CleanupFunction \
  --payload '{"mode": "ttl_sweep"}' \
  /dev/stdout
```

## Step 5: GitHub Actions Integration (Optional)

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

## Cleanup

```bash
sam delete --stack-name devops-flexclone-cicd-demo
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Clone Manager timeout | Cannot reach ONTAP management IP | Verify Lambda is in VPC with access to management subnet |
| S3AP access denied | IAM policy ARN format error | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` format |
| Empty test results | Wrong S3AP alias | Check S3AP Provisioner output |
| TTL Sweep deletes 0 | No clones exist | Verify clone prefix and list existing volumes |
