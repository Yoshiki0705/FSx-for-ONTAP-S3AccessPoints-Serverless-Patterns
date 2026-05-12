# Phase 9 Verification Results

**Date**: 2026-05-13
**Environment**: Account `178625946981`, Region `ap-northeast-1`

---

## 1. AWS Deployment Verification

### UC7 (genomics-pipeline) — OutputDestination=FSXN_S3AP + Observability

- **Stack**: `fsxn-genomics-pipeline-demo`
- **Parameters**: OutputDestination=FSXN_S3AP, EnableCloudWatchAlarms=true,
  EnableVpcEndpoints=true, EnableS3GatewayEndpoint=true, LambdaMemorySize=512,
  LambdaTimeout=900
- **Execution**: SUCCEEDED (Discovery ~8 min + Parallel processing + Summary)
- **AI output verified**: Written to FSxN S3AP under `ai-outputs/` prefix
- **Observability verified**: CloudWatch Alarms + EventBridge failure rule created

### Failure Analysis (resolved)

| Attempt | Result | Root Cause | Fix |
|---------|--------|-----------|-----|
| 1 | FAILED (Discovery timeout) | LambdaTimeout=300s (old default) | Updated to 900s |
| 2 | FAILED (Connect timeout) | VPC Endpoints deleted with UC6 stack | EnableVpcEndpoints=true |
| 3 | SUCCEEDED | All parameters correct | — |

### Key Finding: VPC Endpoint Ownership

When `fsxn-eda-uc6` (the long-running UC6 stack that "owned" VPC Endpoints)
was deleted during cleanup, ALL VPC Endpoints were removed. Subsequent UC
deployments with `EnableVpcEndpoints=false` failed because VPC Lambda had
no path to AWS services.

**Resolution**: The FIRST UC deployed after the owner stack deletion must
include `EnableVpcEndpoints=true` + `EnableS3GatewayEndpoint=true`.

## 2. Cleanup Verification

### Resources cleaned up

| Resource | Count | Status |
|----------|-------|--------|
| CloudFormation stacks (UC6/11/14) | 3 | ✅ Deleted |
| DynamoDB tables (retained) | 6 | ✅ Deleted |
| S3 bucket (UC6 output, versioned) | 1 (2118 objects) | ✅ Emptied + deleted |
| Guard Hooks stack | 1 | Retained (shared infra) |

### Remaining resources (intentional)

| Resource | Reason |
|----------|--------|
| `fsxn-s3ap-guard-hooks` stack | Phase 6 shared infrastructure, intentionally kept |
| `fsxn-eda-deploy-178625946981` bucket | Deploy bucket for Lambda packages, always needed |
| `fsxn-s3ap-guard-rules-178625946981` bucket | Guard Hooks rules bucket |

## 3. Theme Verification Summary

| Theme | Verification | Result |
|-------|-------------|--------|
| A: Observability | All 17 UCs have alarms + EventBridge rules | ✅ |
| B: OutputDestination | UC7 FSXN_S3AP mode SUCCEEDED | ✅ |
| D: cfn-guard | Rules created, CI job added | ✅ |
| F: Performance | UC7 512MB/900s SUCCEEDED | ✅ |

## 4. Validators

| Validator | Result |
|-----------|--------|
| `check_s3ap_iam_patterns.py` | 17/17 clean ✅ |
| `check_handler_names.py` | 87 handlers, 0 issues ✅ |
| `check_conditional_refs.py` | 17 templates, 0 issues ✅ |
