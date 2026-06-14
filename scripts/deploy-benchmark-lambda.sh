#!/bin/bash
# Deploy benchmark Lambda (VPC-external, Internet Origin S3 AP)
# This measures latency from AWS Lambda network (not local Internet)

set -euo pipefail

STACK_NAME="fsxn-benchmark-lambda"
REGION="ap-northeast-1"
S3AP_ALIAS="fsxn-eda-s3ap-fhyst3uaibf46uywh5xka84pnz8jaapn1a-ext-s3alias"

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
