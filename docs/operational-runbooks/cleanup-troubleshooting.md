# CloudFormation Stack Cleanup Troubleshooting

Runbook for resolving `DELETE_FAILED` states when running
`scripts/cleanup_generic_ucs.sh` or manually deleting UC demo stacks.

**Last updated**: 2026-05-11 (based on Phase 7 Extended Work cleanup of 9 UC stacks)

---

## Quick reference: cleanup command

```bash
# Ensure AWS credentials are valid
aws sts get-caller-identity

# Run cleanup (resolves ACCOUNT_ID from STS automatically)
bash scripts/cleanup_generic_ucs.sh UC1 UC2 UC3 UC5 UC7 UC8 UC10 UC12 UC13

# Or with explicit overrides
ACCOUNT_ID=<your-account-id> REGION=us-east-1 bash scripts/cleanup_generic_ucs.sh UC1
```

---

## Failure Mode 1: Athena WorkGroup is non-empty

### Symptom

```
The following resource(s) failed to delete: [AthenaWorkgroup].
Resource handler returned message: "Invalid request provided:
WorkGroup fsxn-<uc>-demo-workgroup is not empty"
```

### Root cause

CloudFormation cannot delete an Athena WorkGroup that contains saved
queries or query execution history. The `DeletionPolicy` on the
WorkGroup resource does not force-delete contents.

### Resolution

```bash
# Force-delete the workgroup with all its contents
aws athena delete-work-group \
    --work-group "fsxn-<uc>-demo-workgroup" \
    --recursive-delete-option \
    --region ap-northeast-1

# Then retry stack deletion
aws cloudformation delete-stack \
    --stack-name "fsxn-<uc>-demo" \
    --region ap-northeast-1
```

### Affected UCs (Phase 7 experience)

UC3 (manufacturing-analytics), UC7 (genomics-pipeline), UC8 (energy-seismic),
UC1 (legal-compliance) — any UC that uses Athena for query output.

### Prevention

Phase 8 Theme A will integrate `--recursive-delete-option` into the
cleanup script automatically. Until then, manual intervention is needed.

---

## Failure Mode 2: S3 bucket has versioned objects

### Symptom

```
The following resource(s) failed to delete: [AthenaResultsBucket].
Resource handler returned message: "The bucket you tried to delete
is not empty. You must delete all versions in the bucket."
```

### Root cause

S3 buckets with versioning enabled retain object versions and delete
markers even after `aws s3 rm --recursive`. CloudFormation's bucket
deletion requires the bucket to be completely empty (no versions, no
delete markers).

### Resolution

```bash
BUCKET="fsxn-<uc>-demo-athena-results-<account-id>"
REGION="ap-northeast-1"

# Step 1: Remove current-version objects
aws s3 rm "s3://${BUCKET}" --recursive --region "$REGION"

# Step 2: Delete all object versions
VERSIONS=$(aws s3api list-object-versions \
    --bucket "$BUCKET" --region "$REGION" \
    --output json \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')

if [ "$VERSIONS" != '{"Objects": null}' ] && [ -n "$VERSIONS" ]; then
    echo "$VERSIONS" > /tmp/_versions.json
    aws s3api delete-objects \
        --bucket "$BUCKET" --region "$REGION" \
        --delete "file:///tmp/_versions.json"
fi

# Step 3: Delete all delete markers
MARKERS=$(aws s3api list-object-versions \
    --bucket "$BUCKET" --region "$REGION" \
    --output json \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')

if [ "$MARKERS" != '{"Objects": null}' ] && [ -n "$MARKERS" ]; then
    echo "$MARKERS" > /tmp/_markers.json
    aws s3api delete-objects \
        --bucket "$BUCKET" --region "$REGION" \
        --delete "file:///tmp/_markers.json"
fi

# Step 4: Verify empty
aws s3 ls "s3://${BUCKET}" --recursive --region "$REGION"
# Should return nothing

# Step 5: Retry stack deletion
aws cloudformation delete-stack \
    --stack-name "fsxn-<uc>-demo" \
    --region "$REGION"
```

### Affected UCs

Any UC with `AthenaResultsBucket` or `OutputBucket` that has versioning
enabled. In Phase 7: UC3 (manufacturing-analytics).

### Prevention

Phase 8 Theme A will integrate versioned-bucket emptying into the
cleanup script. A helper script `scripts/_empty_versioned_bucket.sh`
(gitignored) exists for manual use in the interim.

---

## Failure Mode 3: Security Group has a dependent object

### Symptom

```
The following resource(s) failed to delete: [LambdaSecurityGroup].
resource sg-<lambda-sg-id> has a dependent object
```

### Root cause

The UC's Lambda Security Group is referenced in another Security
Group's inbound rules (typically the VPC Endpoint SG). CloudFormation
cannot delete a SG that is still referenced by another SG's rules.

This commonly happens when a manual workaround was applied to add
the Lambda SG to the VPC Endpoint SG's inbound rules (Phase 7 tasks
O-2 pattern).

### Resolution

```bash
# Step 1: Identify which SG references the Lambda SG
aws ec2 describe-security-groups \
    --region ap-northeast-1 \
    --query "SecurityGroups[?IpPermissions[?UserIdGroupPairs[?GroupId=='sg-<lambda-sg-id>']]].GroupId" \
    --output text
# Returns: sg-<vpc-endpoint-sg-id>

# Step 2: Revoke the inbound rule
aws ec2 revoke-security-group-ingress \
    --group-id "sg-<vpc-endpoint-sg-id>" \
    --region ap-northeast-1 \
    --ip-permissions 'IpProtocol=tcp,FromPort=443,ToPort=443,UserIdGroupPairs=[{GroupId=sg-<lambda-sg-id>}]'

# Step 3: Retry stack deletion
aws cloudformation delete-stack \
    --stack-name "fsxn-<uc>-demo" \
    --region ap-northeast-1
```

### Important: Do NOT revoke rules for other UCs

If multiple UCs share the same VPC Endpoint SG, only revoke the rule
for the UC being deleted. Other UCs' Lambda SGs must remain in the
inbound rules.

Example: UC6's Lambda SG (`sg-<uc6-lambda-sg>`) should NOT be revoked
if UC6 is still deployed.

### Affected UCs (Phase 7 experience)

UC1 (legal-compliance), UC2 (financial-idp) — both had their Lambda
SGs manually added to the VPC Endpoint SG during Phase 7 Extended Work.

### Prevention

Phase 8 Theme B will automate VPC Endpoint SG rule management via a
CloudFormation Custom Resource. The Custom Resource automatically
adds the rule on stack create and removes it on stack delete.

---

## Failure Mode 4: VPC Lambda ENI release delay

### Symptom

Stack stays in `DELETE_IN_PROGRESS` for 15-30 minutes, then eventually
succeeds (or fails on a different resource).

### Root cause

Lambda functions attached to a VPC create Elastic Network Interfaces
(ENIs). When the Lambda function is deleted, the ENI is not immediately
released — AWS takes 15-30 minutes to garbage-collect unused ENIs.

During this window, the Security Group attached to the ENI cannot be
deleted, which blocks the stack deletion.

### Resolution

**Wait**. This is expected AWS behavior. The stack will eventually
complete deletion once the ENIs are released.

If you need to speed up:

```bash
# List ENIs attached to the Lambda SG
aws ec2 describe-network-interfaces \
    --filters "Name=group-id,Values=sg-<lambda-sg-id>" \
    --region ap-northeast-1 \
    --query 'NetworkInterfaces[].[NetworkInterfaceId,Status,Description]' \
    --output table

# If Status is "available" (not "in-use"), you can manually delete:
aws ec2 delete-network-interface \
    --network-interface-id eni-<id> \
    --region ap-northeast-1
```

**Caution**: Only delete ENIs with Status=`available`. Never delete
`in-use` ENIs — they may belong to active Lambda invocations.

### Affected UCs

All UCs with VPC-attached Lambda functions (Discovery Lambda is always
VPC-attached for ONTAP REST API access).

---

## Failure Mode 5: DynamoDB tables with DeletionPolicy: Retain

### Symptom

Stack deletion succeeds, but DynamoDB tables remain in the account.

### Root cause

Some UC templates set `DeletionPolicy: Retain` on DynamoDB tables to
prevent accidental data loss. CloudFormation skips these resources
during stack deletion.

### Resolution

```bash
# List remaining tables
aws dynamodb list-tables --region ap-northeast-1 \
    --query 'TableNames[?contains(@, `fsxn-`)]' \
    --output text

# Delete each retained table manually
aws dynamodb delete-table \
    --table-name "fsxn-<uc>-demo-<table-name>" \
    --region ap-northeast-1
```

### Known retained tables (Phase 7 UCs)

| UC | Table name pattern |
|---|---|
| UC15 | `fsxn-uc15-demo-change-history` |
| UC16 | `fsxn-uc16-demo-retention`, `fsxn-uc16-demo-foia-requests` |
| UC17 | `fsxn-uc17-demo-landuse-history` |

### Prevention

After stack deletion, always run:
```bash
aws dynamodb list-tables --region ap-northeast-1 \
    --query 'TableNames[?contains(@, `fsxn-`)]'
```
to verify no orphaned tables remain.

---

## Failure Mode 6: ACCOUNT_ID placeholder in cleanup script

### Symptom

`aws s3 rb` reports "NoSuchBucket" for every UC, but the stacks
still have output buckets.

### Root cause

The cleanup script had a literal `<ACCOUNT_ID>` placeholder string
(leftover from a privacy redaction pass) instead of the actual account
ID. Bucket names like `fsxn-legal-compliance-demo-output-<ACCOUNT_ID>`
don't exist, so the empty + delete operations silently no-op.

### Resolution

Fixed in commit `770f713`. The script now resolves the account ID
dynamically via `aws sts get-caller-identity`. If you're on an older
version of the script:

```bash
# Override with env var
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
export ACCOUNT_ID
bash scripts/cleanup_generic_ucs.sh UC1 UC2 ...
```

---

## General troubleshooting workflow

When `DELETE_FAILED` occurs:

```bash
# 1. Identify which resources failed
aws cloudformation describe-stack-events \
    --stack-name "fsxn-<uc>-demo" \
    --region ap-northeast-1 \
    --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
    --output table

# 2. Fix the blocking resource (see failure modes above)

# 3. Retry deletion
aws cloudformation delete-stack \
    --stack-name "fsxn-<uc>-demo" \
    --region ap-northeast-1

# 4. Monitor progress
watch -n 30 'aws cloudformation describe-stacks \
    --stack-name "fsxn-<uc>-demo" \
    --region ap-northeast-1 \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "DELETED"'
```

---

## Cost awareness during cleanup

| Resource | Cost if left running | Urgency |
|---|---|---|
| Lambda functions | $0 (pay per invocation only) | Low |
| DynamoDB tables (on-demand) | $0 if no reads/writes | Low |
| VPC ENIs | $0 | Low |
| SageMaker Endpoints | $0.05-$2/hr depending on instance | **High** |
| OpenSearch Serverless | $350+/month (min 2 OCU) | **High** |
| Deadline Cloud farm | $0.01/hr idle + worker costs | Medium |

Always verify SageMaker and OpenSearch resources are deleted first.
Lambda, DynamoDB, and ENIs can wait.

---

## Related documents

- `scripts/cleanup_generic_ucs.sh` — main cleanup script (v2, commit 770f713)
- `scripts/_empty_versioned_bucket.sh` — helper for versioned S3 buckets (gitignored)
- `scripts/_check_cleanup_progress.sh` — poll stack deletion status (gitignored)
- `docs/dual-kiro-coordination.md` §9 — AWS resource lifecycle coordination rules
- `.kiro/specs/fsxn-s3ap-serverless-patterns-phase8/requirements.md` Theme A — planned cleanup script Python rewrite
