# CloudFormation Stack Deployment Troubleshooting

Runbook for resolving deployment failures when running
`scripts/deploy_generic_ucs.sh` or manually deploying UC demo stacks.

**Last updated**: 2026-05-11 (Phase 8 Batch 2 deployment findings)

---

## Quick reference: deploy command

```bash
# Set environment variables (see scripts/deploy_generic_ucs.sh header for full list)
export DEPLOY_BUCKET=fsxn-eda-deploy-<ACCOUNT_ID>
export S3_AP_ALIAS=<your-s3ap-alias>-ext-s3alias
export VPC_ID=vpc-<your-vpc-id>
export SUBNETS=subnet-<id1>,subnet-<id2>
export ONTAP_MANAGEMENT_IP=<ip>
export SVM_UUID=<uuid>

# Deploy (S3 Gateway Endpoint disabled by default for shared VPC)
bash scripts/deploy_generic_ucs.sh UC2 UC9 UC15 UC16 UC17
```

---

## Failure Mode 1: S3 Gateway Endpoint already exists

### Symptom

```
Resource handler returned message: "route table rtb-xxx already has a route
with destination-prefix-list-id pl-xxx (Service: Ec2, Status Code: 400)"
(HandlerErrorCode: AlreadyExists)
```

### Root Cause

The UC template creates a S3 Gateway VPC Endpoint, but one already exists
in the same VPC route table (typically from the UC6 base stack or another
UC that was deployed first).

S3 Gateway Endpoints are VPC-wide resources — only one per route table is
allowed.

### Resolution

Set `EnableS3GatewayEndpoint=false` (or `EnableVpcEndpoints=false` for
templates that use that parameter):

```bash
# Option 1: Environment variable (applies to all UCs via deploy script)
export ENABLE_S3_GATEWAY_EP=false
bash scripts/deploy_generic_ucs.sh UC2

# Option 2: Direct CloudFormation deploy
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    EnableS3GatewayEndpoint=false \
    ...
```

### Prevention

The `deploy_generic_ucs.sh` script now defaults to
`ENABLE_S3_GATEWAY_EP=false`. If deploying to a fresh VPC without any
existing S3 Gateway Endpoint, set `ENABLE_S3_GATEWAY_EP=true`.

### Which templates have this parameter?

| Parameter | Templates |
|-----------|-----------|
| `EnableS3GatewayEndpoint` | UC2, UC3, UC5, UC10, UC12, UC13 |
| `EnableVpcEndpoints` (controls S3 GW EP) | UC7, UC8, UC9, UC15, UC16, UC17 |
| No S3 GW EP resource | UC1, UC4, UC6, UC11, UC14 |

---

## Failure Mode 2: VPC Lambda cold start timeout

### Symptom

Step Functions execution takes 2-3 minutes on the Discovery step (first
Lambda invocation), then subsequent steps complete in seconds.

### Root Cause

VPC-attached Lambda functions require ENI (Elastic Network Interface)
creation on first invocation. This takes 60-180 seconds depending on
VPC complexity and AZ availability.

### Resolution

This is expected behavior for first invocation. Subsequent invocations
reuse the ENI and complete in seconds.

For production workloads:
```yaml
# Add to Lambda function in template
ProvisionedConcurrencyConfig:
  ProvisionedConcurrentExecutions: 1
```

Or use Lambda SnapStart (Python 3.12+ with `SnapStart: ApplyOn: PublishedVersions`).

### Observed timings (Phase 8 verification)

| UC | First invocation | Subsequent |
|----|-----------------|------------|
| UC9 | 2:41 (Discovery) | <1s |
| UC15 | ~3s (already warm from UC6) | <1s |
| UC16 | ~3s | <1s |
| UC17 | ~4s | <1s |

---

## Failure Mode 3: PrivateRouteTableIds required

### Symptom

```
Parameters: [PrivateRouteTableIds] must have values
```

### Root Cause

Some UC templates require `PrivateRouteTableIds` for S3 Gateway Endpoint
route table association. This parameter is not in the base deploy script's
parameter list.

### Resolution

Find the route table ID for your private subnets:

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<your-subnet-id>" \
  --query 'RouteTables[0].RouteTableId' --output text
```

Then pass it:
```bash
aws cloudformation deploy \
  --parameter-overrides \
    PrivateRouteTableIds=rtb-<your-route-table-id> \
    ...
```

Note: When `EnableS3GatewayEndpoint=false`, this parameter is still
required by CloudFormation but its value is not used (the S3 Gateway
Endpoint resource is conditionally skipped).

---

## Failure Mode 4: Lambda package not found in deploy bucket

### Symptom

```
Error: The runtime parameter of python3.13 is no longer supported...
```
or
```
Error: S3 key lambda/<uc>-<function>.zip does not exist
```

### Root Cause

Lambda deployment packages haven't been uploaded to the deploy bucket.

### Resolution

Package and upload Lambda functions:

```bash
bash scripts/package_generic_uc.sh <uc-directory>
# or for all UCs:
bash scripts/package_lambdas.sh
```

Verify packages exist:
```bash
aws s3 ls s3://<deploy-bucket>/lambda/ | grep <uc-name>
```

---

## Failure Mode 5: Secrets Manager secret not found

### Symptom

Lambda execution fails with:
```
ResourceNotFoundException: Secrets Manager can't find the specified secret.
```

### Root Cause

The ONTAP credentials secret (`fsx-ontap-fsxadmin-credentials`) doesn't
exist in the target region, or the Lambda's IAM role doesn't have
`secretsmanager:GetSecretValue` permission.

### Resolution

1. Verify secret exists:
```bash
aws secretsmanager describe-secret \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --region ap-northeast-1
```

2. If missing, create it:
```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-password>"}' \
  --region ap-northeast-1
```

---

## General debugging tips

1. **Check stack events for the actual error**:
```bash
aws cloudformation describe-stack-events \
  --stack-name <stack-name> \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
  --output table
```

2. **Check Lambda logs after execution**:
```bash
aws logs tail /aws/lambda/<stack-name>-discovery --since 5m
```

3. **Retry after ROLLBACK_COMPLETE**:
```bash
# Delete the failed stack first
aws cloudformation delete-stack --stack-name <stack-name>
# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name <stack-name>
# Retry deploy
bash scripts/deploy_generic_ucs.sh <UC>
```
