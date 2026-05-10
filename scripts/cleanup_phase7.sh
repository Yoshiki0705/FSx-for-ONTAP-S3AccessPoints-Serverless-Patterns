#!/bin/bash
# Phase 7 (UC15/UC16/UC17) cleanup script
# Removes demo stacks and associated S3 buckets / DynamoDB tables (which have DeletionPolicy: Retain)
set +e

for bucket in fsxn-uc15-demo-output-178625946981 fsxn-uc16-demo-output-178625946981 fsxn-uc17-demo-output-178625946981; do
  echo "=== Emptying $bucket ==="
  aws s3api delete-objects --bucket "$bucket" --region ap-northeast-1 \
    --delete "$(aws s3api list-object-versions --bucket "$bucket" --region ap-northeast-1 --output=json --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" 2>&1 | tail -3
  aws s3api delete-objects --bucket "$bucket" --region ap-northeast-1 \
    --delete "$(aws s3api list-object-versions --bucket "$bucket" --region ap-northeast-1 --output=json --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)" 2>&1 | tail -3
  aws s3 rb s3://$bucket --region ap-northeast-1 2>&1 | tail -3
done

for tbl in fsxn-uc15-demo-change-history fsxn-uc16-demo-retention fsxn-uc16-demo-foia-requests fsxn-uc17-demo-landuse-history; do
  echo "=== Deleting DynamoDB $tbl ==="
  aws dynamodb delete-table --table-name "$tbl" --region ap-northeast-1 2>&1 | tail -2
done

echo "=== Deleting CloudFormation stacks ==="
for stack in fsxn-uc15-demo fsxn-uc16-demo fsxn-uc17-demo; do
  aws cloudformation delete-stack --stack-name "$stack" --region ap-northeast-1
  echo "Initiated delete: $stack"
done
