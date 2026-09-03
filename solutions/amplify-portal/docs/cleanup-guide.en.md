# Amplify Portal Cleanup Guide

🌐 **Language / 言語**: [日本語](cleanup-guide.md) | English

This guide describes how to safely delete the Amplify portal and its related resources.

## Prerequisites

- The Amazon FSx for NetApp ONTAP file system is NOT deleted (existing infrastructure)
- The CDKToolkit stack is shared with other projects, so it is NOT deleted
- S3 AP (already attached to FSx for ONTAP) is managed separately via `detach-and-delete-s3-access-point`
  - **Ordering constraint**: if you also delete a volume, **the S3 AP must be detached and deleted first**. Deleting a volume while an access point is still attached returns BadRequest. This guide does not delete the file system, so it usually does not apply — but respect the order if you clean up volumes too.

## What deletion destroys (read before running)

None of the following can be recovered.

| Target | What is lost |
|--------|--------------|
| The 6 DynamoDB tables | Job execution history, favourites, recent files, file tags, folder watches, notifications. Unless point-in-time recovery was enabled, deleting the table does not give the data back. Export first if you need any of it |
| S3 buckets (`rb --force`) | `--force` empties the bucket before deleting it, so **every object in it goes as well**. Check the contents before worrying about whether the bucket is shared |
| CloudWatch Logs | The log groups go with the stack. If you need them for audit, export to S3 before deleting |

> **State created on the ONTAP side by portal demos is NOT removed by this cleanup.** In particular, if you enabled tamperproof snapshots (snapshot locking) or set an `expiry_time` on individual snapshots, those **cannot be shortened or released**. If you created a SnapLock audit-log volume, deletion of the volume, the SVM and the **file system** is blocked for at least six months. If you exercised any of those, check the pre-flight list in [Tamperproof snapshot design](../../../docs/tamperproof-snapshot-design.md).

## Quick Reference

```bash
# === Delete the Amplify sandbox (do this first) ===
cd solutions/amplify-portal
./scripts/sandbox.sh delete --yes
# → 5-10 minutes. Cognito, AppSync, DynamoDB, Lambda and S3 all go
# `npx ampx sandbox delete` bare takes the identifier from the OS username, so it can
# delete a different sandbox than the one amplify_outputs.json names. The wrapper
# resolves the identifier from deployed state and passes it explicitly.

# === Delete the project's CloudFormation stacks together ===
./scripts/cleanup_stacks.sh --all-project
# → Deletes stacks with the fsxn- prefix, asking about each

# === Delete one stack ===
aws cloudformation delete-stack --stack-name <stack-name> --region ap-northeast-1

# === Delete the standalone Lambdas ===
aws lambda delete-function --function-name agentcore-mcp-eda-tools --region ap-northeast-1
aws lambda delete-function --function-name fsxn-duckdb-query --region ap-northeast-1

# === Confirm everything is gone ===
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_IN_PROGRESS DELETE_FAILED \
  --query 'StackSummaries[?starts_with(StackName, `fsxn-`) || starts_with(StackName, `amplify-fsxn`)].[StackName,StackStatus]' \
  --output table --region ap-northeast-1
```

## Deletion Targets and Duration

| Resource | Command | Duration |
|----------|---------|---------|
| Amplify Sandbox | `npx ampx sandbox delete --yes` | 5-10 min |
| VPC Endpoint stack | `aws cloudformation delete-stack --stack-name fsxn-syslog-vpce-admin-audit` | 1-2 min |
| EventBridge + Lambda stack | `aws cloudformation delete-stack --stack-name fsxn-automated-response` | 2-3 min |
| AgentCore MCP Lambda | `aws lambda delete-function --function-name agentcore-mcp-eda-tools` | immediate |
| DELETE_FAILED stack | `./scripts/cleanup_stacks.sh` (auto-repair) | 1-3 min |

## Step Details

### 1. Delete the Amplify Sandbox

```bash
cd solutions/amplify-portal
npx ampx sandbox delete --yes
```

This deletes the following:
- Cognito User Pool + Identity Pool
- AppSync GraphQL API
- DynamoDB tables (JobExecution, Favorite, RecentFile, FileTag, FolderWatch, FileNotification)
- Lambda functions (ListFiles, GetPresignedUrl, AskAboutFile, DetectLabels, Textract, Comprehend, Athena, Glue, SearchFiles, ListSnapshots, QueryAuditLog, etc.)
- S3 buckets (for code generation, for deployment)
- IAM roles + policies
- CloudWatch Logs log groups

> **Note**: Deleting the DynamoDB tables can take 3-5 minutes. If it times out, check progress with `aws cloudformation describe-stacks`.
>
> **The data does not come back**: the contents of those six tables (job history, tags, watch settings and so on) are lost at this point. Export anything you want to keep first, for example with `aws dynamodb scan`.

### 2. Delete the VPC Endpoint stack

VPC Interface Endpoints are billed hourly (~$7.20/month each), so delete them early if they are not needed.

```bash
aws cloudformation delete-stack --stack-name fsxn-syslog-vpce-admin-audit --region ap-northeast-1
```

### 3. Delete the EventBridge + Lambda stacks

If the EventBridge Schedule is ENABLED, the Lambda is invoked periodically.

```bash
aws cloudformation delete-stack --stack-name fsxn-automated-response --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-ar-ttl-e2e --region ap-northeast-1
```

### 4. Delete standalone Lambda functions

Lambda functions created outside of a CloudFormation stack:

```bash
aws lambda delete-function --function-name agentcore-mcp-eda-tools --region ap-northeast-1
aws lambda delete-function --function-name fsxn-duckdb-query --region ap-northeast-1
```

### 5. Handle DELETE_FAILED stacks

Stacks left behind after a past deletion failure (the resources themselves no longer exist):

```bash
# Self-repair: find what is blocking the delete, then retry
./scripts/cleanup_stacks.sh

# Or force it with FORCE_DELETE_STACK
aws cloudformation delete-stack --stack-name <stack-name> --region ap-northeast-1 --deletion-mode FORCE_DELETE_STACK
```

> **Side effect of `FORCE_DELETE_STACK`**: CloudFormation **abandons** the resources it could not delete and removes only the stack. Abandoned resources keep billing and are no longer tracked by any stack, so you have to find and delete them by hand later. Clear the blockers with `./scripts/cleanup_stacks.sh` first and keep this as the last resort.

### 6. Check S3 buckets

If any buckets remain after the Amplify sandbox is deleted:

```bash
aws s3 ls | grep -i "fsxn\|amplify-fsxn"
# If anything is left:
# aws s3 rb s3://<bucket-name> --force
```

> **Note**: `rb --force` empties the bucket before deleting it, so **every object inside is deleted too**. `athena-results-*` and `aws-sam-cli-managed-default-*` may be shared with other projects, so check both whether it is shared **and** what is in it. `aws s3 ls s3://<bucket-name> --recursive --summarize | tail -2` shows the object count first.

## Redeployment

To build the environment again after cleanup:

```bash
cd solutions/amplify-portal
npm install
cp amplify/portal-config.example.ts amplify/portal-config.ts
# Edit portal-config.ts
make sandbox  # 10-15 minutes the first time, CDK bootstrap included
make dev      # Start the local dev server
```

## Troubleshooting

### `npx ampx sandbox delete` times out

The CDK stack deletion continues in the background. Check it with:

```bash
aws cloudformation list-stacks --stack-status-filter DELETE_IN_PROGRESS \
  --query 'StackSummaries[*].[StackName,StackStatus]' --output table --region ap-northeast-1
```

### Stuck in DELETE_FAILED

Delete the blocker resources first (non-empty S3 buckets, Athena WorkGroups, ECR repositories):

```bash
./scripts/cleanup_stacks.sh <stack-name>
```

### Lambda functions remain after the stack is deleted

Lambda functions created outside CloudFormation management must be deleted manually:

```bash
aws lambda list-functions \
  --query 'Functions[?starts_with(FunctionName, `fsxn-`) || starts_with(FunctionName, `agentcore-`)].[FunctionName]' \
  --output text --region ap-northeast-1
```
