#!/bin/bash
# Deploy benchmark Lambda (VPC-external, Internet Origin S3 AP)
# This measures latency from AWS Lambda network (not local Internet)

set -euo pipefail

STACK_NAME="fsxn-benchmark-lambda"
REGION="ap-northeast-1"
S3AP_ALIAS="${S3AP_ALIAS:?set S3AP_ALIAS to the S3 Access Points alias to measure}"

echo "=== Deploying benchmark Lambda ==="

aws cloudformation deploy \
  --template-file scripts/benchmark-lambda-template.yaml \
  --stack-name ${STACK_NAME} \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    S3AccessPointAlias=${S3AP_ALIAS} \
  --region ${REGION}

echo "=== Stack deployed ==="
aws cloudformation describe-stacks \
  --stack-name ${STACK_NAME} \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region ${REGION}
