#!/usr/bin/env bash
# =============================================================================
# UC29 / UC30 verification-environment teardown (idempotent, re-runnable)
# =============================================================================
# Removes ONLY the resources created for UC29 (Self-Service KB) and UC30
# (Quick Agentic Workspace) verification. The shared FSx for ONTAP file system
# is preserved by default (it backs all 28+ patterns).
#
# Design principles (lessons learned from prior deletions):
#   - Resolve IDs by NAME at runtime; never hardcode (IDs go stale on rebuild).
#   - Order matters: empty buckets / drop Glue tables BEFORE stack delete;
#     delete KB data sources BEFORE the KB; terminate EC2 BEFORE its SG;
#     delete volumes BEFORE the SVM.
#   - Every step is guarded (|| true / existence check) so the script is safe
#     to re-run after a partial failure.
#   - No account IDs / IPs hardcoded (public repo). Derived at runtime.
#
# Usage:
#   bash scripts/teardown-uc29-uc30.sh            # full teardown
#   DELETE_FSX_FILESYSTEM=true bash ...           # also delete the FS (DANGER)
#   SKIP_AD=true bash ...                         # keep the Managed AD
# =============================================================================
set -uo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
DELETE_FSX_FILESYSTEM="${DELETE_FSX_FILESYSTEM:-false}"
SKIP_AD="${SKIP_AD:-false}"

# --- resource names (stable; IDs resolved at runtime) ----------------------
STACK_UC29="fsxn-s3ap-uc29-selfservice-kb"
STACK_UC30="fsxn-s3ap-uc30-quick-workspace"
KB_NAME="uc29-selfservice-kb"
AOSS_COLLECTION="uc29-kb-vectors"
AOSS_ENC_POLICY="uc29-kb-encryption"
AOSS_NET_POLICY="uc29-kb-network"
AOSS_ACCESS_POLICY="uc29-kb-access"
KB_ROLE="fsxn-s3ap-bedrock-kb-role"
AD_NAME="uc29demo.local"
EC2_NAME="uc29-windows-demo"
SG_NAME="uc29-windows-demo"
SVM_NAME="uc29demosvm"
VOL_NAMES=("ai_knowledge" "quick_workspace")
EVENT_BUS="fsxn-fpolicy-events"
DEMO_BUCKET="uc29-demo-sample-${ACCOUNT_ID}"
GLUE_DB="quick_workspace_db"
GLUE_TABLES=("sales_pipeline" "it_incidents")
ATHENA_WG="quick-workspace-wg"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✓ %s\033[0m\n' "$*"; }
skip() { printf '    \033[1;33m- %s\033[0m\n' "$*"; }

aws_r() { aws --region "$REGION" "$@"; }

# =============================================================================
log "Phase 1 — CFN prerequisites (Glue tables + non-empty buckets)"
# =============================================================================
for t in "${GLUE_TABLES[@]}"; do
  if aws_r glue get-table --database-name "$GLUE_DB" --name "$t" >/dev/null 2>&1; then
    aws_r glue delete-table --database-name "$GLUE_DB" --name "$t" >/dev/null 2>&1 && ok "Glue table dropped: $t"
  else
    skip "Glue table absent: $t"
  fi
done

# Empty any S3 bucket owned by the two stacks (Athena results, etc.)
for stack in "$STACK_UC30" "$STACK_UC29"; do
  for b in $(aws_r cloudformation describe-stack-resources --stack-name "$stack" \
              --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
              --output text 2>/dev/null); do
    [ -n "$b" ] && [ "$b" != "None" ] || continue
    aws_r s3 rm "s3://${b}" --recursive >/dev/null 2>&1 || true
    # purge versions/delete-markers so the bucket can be removed by CFN
    aws_r s3api list-object-versions --bucket "$b" \
      --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null \
      | grep -q '"Key"' && \
      aws_r s3api delete-objects --bucket "$b" --delete "$(aws_r s3api list-object-versions \
        --bucket "$b" --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" >/dev/null 2>&1 || true
    ok "Emptied stack bucket: $b"
  done
done

# LESSON: an Athena WorkGroup with saved/named queries fails CFN delete with
# "WorkGroup ... is not empty". Force-delete it recursively up front; CFN then
# finds it already gone and the stack delete succeeds.
if aws_r athena get-work-group --work-group "$ATHENA_WG" >/dev/null 2>&1; then
  aws_r athena delete-work-group --work-group "$ATHENA_WG" --recursive-delete-option >/dev/null 2>&1 \
    && ok "Athena workgroup purged: $ATHENA_WG" || skip "Athena workgroup purge retry: $ATHENA_WG"
else
  skip "Athena workgroup absent: $ATHENA_WG"
fi

# =============================================================================
log "Phase 2 — Delete CloudFormation stacks"
# =============================================================================
for stack in "$STACK_UC30" "$STACK_UC29"; do
  if aws_r cloudformation describe-stacks --stack-name "$stack" >/dev/null 2>&1; then
    aws_r cloudformation delete-stack --stack-name "$stack" && ok "delete-stack requested: $stack"
  else
    skip "Stack absent: $stack"
  fi
done
for stack in "$STACK_UC30" "$STACK_UC29"; do
  aws_r cloudformation describe-stacks --stack-name "$stack" >/dev/null 2>&1 || continue
  log "Waiting for $stack to delete (bounded)..."
  aws_r cloudformation wait stack-delete-complete --stack-name "$stack" 2>/dev/null \
    && ok "Stack deleted: $stack" || skip "Stack still deleting / needs manual check: $stack"
done

# =============================================================================
log "Phase 3 — Bedrock Knowledge Bases (data sources first, then KB)"
# =============================================================================
delete_kb() {
  local kb_id="$1"
  [ -n "$kb_id" ] && [ "$kb_id" != "None" ] || return 0
  # LESSON: a KB with dataDeletionPolicy=DELETE purges vectors on delete. If the
  # AOSS collection or KB role is already gone, that purge fails and the KB
  # sticks in DELETE_UNSUCCESSFUL (and can't be cleared because the original
  # collection ARN no longer exists). Flip every data source to RETAIN FIRST so
  # deletion never depends on the vector store; we delete the store separately.
  for ds in $(aws_r bedrock-agent list-data-sources --knowledge-base-id "$kb_id" \
               --query "dataSourceSummaries[].dataSourceId" --output text 2>/dev/null); do
    local name cfg
    name=$(aws_r bedrock-agent get-data-source --knowledge-base-id "$kb_id" --data-source-id "$ds" --query "dataSource.name" --output text 2>/dev/null)
    cfg=$(aws_r bedrock-agent get-data-source --knowledge-base-id "$kb_id" --data-source-id "$ds" --query "dataSource.dataSourceConfiguration" --output json 2>/dev/null)
    [ -n "$cfg" ] && aws_r bedrock-agent update-data-source --knowledge-base-id "$kb_id" --data-source-id "$ds" \
      --name "$name" --data-deletion-policy RETAIN --data-source-configuration "$cfg" >/dev/null 2>&1 \
      && ok "data source $ds -> RETAIN" || skip "data source $ds RETAIN skip"
    aws_r bedrock-agent delete-data-source --knowledge-base-id "$kb_id" --data-source-id "$ds" >/dev/null 2>&1 \
      && ok "Deleted data source $ds (KB $kb_id)" || skip "data source $ds delete retry"
  done
  sleep 3
  aws_r bedrock-agent delete-knowledge-base --knowledge-base-id "$kb_id" >/dev/null 2>&1 \
    && ok "KB $kb_id delete requested" || skip "KB $kb_id delete retry needed"
  # Wait until the KB is gone BEFORE later phases remove AOSS/role.
  for _ in $(seq 1 24); do
    aws_r bedrock-agent get-knowledge-base --knowledge-base-id "$kb_id" >/dev/null 2>&1 || { ok "KB $kb_id gone"; return 0; }
    sleep 10
  done
  skip "KB $kb_id still deleting — re-run script if it sticks"
}
# active UC29 KB (resolve by name)
KB_ID=$(aws_r bedrock-agent list-knowledge-bases \
          --query "knowledgeBaseSummaries[?name=='${KB_NAME}'].knowledgeBaseId" --output text 2>/dev/null)
delete_kb "$KB_ID"
# any KB stuck in DELETE_UNSUCCESSFUL (leftovers from earlier work)
for kb in $(aws_r bedrock-agent list-knowledge-bases \
             --query "knowledgeBaseSummaries[?status=='DELETE_UNSUCCESSFUL'].knowledgeBaseId" --output text 2>/dev/null); do
  delete_kb "$kb"
done

# =============================================================================
log "Phase 4 — OpenSearch Serverless (collection, then policies)"
# =============================================================================
if aws_r opensearchserverless batch-get-collection --names "$AOSS_COLLECTION" \
     --query "collectionDetails[0].id" --output text 2>/dev/null | grep -vq None; then
  CID=$(aws_r opensearchserverless batch-get-collection --names "$AOSS_COLLECTION" \
          --query "collectionDetails[0].id" --output text)
  aws_r opensearchserverless delete-collection --id "$CID" >/dev/null 2>&1 && ok "Deleted AOSS collection $AOSS_COLLECTION ($CID)"
  sleep 10
else
  skip "AOSS collection absent: $AOSS_COLLECTION"
fi
aws_r opensearchserverless delete-access-policy   --name "$AOSS_ACCESS_POLICY" --type data       >/dev/null 2>&1 && ok "Deleted access policy $AOSS_ACCESS_POLICY"   || skip "access policy absent"
aws_r opensearchserverless delete-security-policy --name "$AOSS_NET_POLICY"    --type network     >/dev/null 2>&1 && ok "Deleted network policy $AOSS_NET_POLICY"     || skip "network policy absent"
aws_r opensearchserverless delete-security-policy --name "$AOSS_ENC_POLICY"    --type encryption  >/dev/null 2>&1 && ok "Deleted encryption policy $AOSS_ENC_POLICY" || skip "encryption policy absent"

# =============================================================================
log "Phase 5 — IAM role ${KB_ROLE}"
# =============================================================================
if aws iam get-role --role-name "$KB_ROLE" >/dev/null 2>&1; then
  for p in $(aws iam list-attached-role-policies --role-name "$KB_ROLE" --query "AttachedPolicies[].PolicyArn" --output text 2>/dev/null); do
    aws iam detach-role-policy --role-name "$KB_ROLE" --policy-arn "$p" >/dev/null 2>&1 || true
  done
  for p in $(aws iam list-role-policies --role-name "$KB_ROLE" --query "PolicyNames[]" --output text 2>/dev/null); do
    aws iam delete-role-policy --role-name "$KB_ROLE" --policy-name "$p" >/dev/null 2>&1 || true
  done
  aws iam delete-role --role-name "$KB_ROLE" >/dev/null 2>&1 && ok "Deleted IAM role $KB_ROLE" || skip "IAM role delete retry needed"
else
  skip "IAM role absent: $KB_ROLE"
fi

# =============================================================================
log "Phase 6 — Windows EC2 + Security Group"
# =============================================================================
IID=$(aws_r ec2 describe-instances \
       --filters "Name=tag:Name,Values=${EC2_NAME}" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
       --query "Reservations[].Instances[].InstanceId" --output text 2>/dev/null)
if [ -n "$IID" ] && [ "$IID" != "None" ]; then
  aws_r ec2 terminate-instances --instance-ids $IID >/dev/null 2>&1 && ok "Terminating EC2: $IID"
  aws_r ec2 wait instance-terminated --instance-ids $IID 2>/dev/null && ok "EC2 terminated" || skip "EC2 still terminating"
else
  skip "EC2 absent: $EC2_NAME"
fi
SGID=$(aws_r ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
        --query "SecurityGroups[].GroupId" --output text 2>/dev/null)
if [ -n "$SGID" ] && [ "$SGID" != "None" ]; then
  aws_r ec2 delete-security-group --group-id "$SGID" >/dev/null 2>&1 && ok "Deleted SG $SGID" || skip "SG delete retry needed (ENI still detaching)"
else
  skip "SG absent: $SG_NAME"
fi

# =============================================================================
log "Phase 7a — Detach FSx S3 Access Points (blocks volume delete otherwise)"
# =============================================================================
# LESSON: an FSx ONTAP S3 access point attached to a volume blocks DeleteVolume
# with: "Cannot delete volume while it has one or multiple S3 access points".
# These are NOT s3control access points — use the FSx DetachAndDeleteS3AccessPoint API.
for ap in $(aws_r fsx describe-s3-access-point-attachments \
             --query "S3AccessPointAttachments[?contains(Name,'uc29')||contains(Name,'uc30')].Name" \
             --output text 2>/dev/null); do
  aws_r fsx detach-and-delete-s3-access-point --name "$ap" >/dev/null 2>&1 && ok "detach+delete S3 AP: $ap" || skip "S3 AP detach retry: $ap"
done
# wait until those attachments are gone before deleting volumes
for _ in $(seq 1 20); do
  left=$(aws_r fsx describe-s3-access-point-attachments \
          --query "S3AccessPointAttachments[?contains(Name,'uc29')||contains(Name,'uc30')].Name" --output text 2>/dev/null)
  [ -z "$left" ] && break
  sleep 10
done

# =============================================================================
log "Phase 7 — FSx volumes + SVM (file system preserved)"
# =============================================================================
SVM_ID=$(aws_r fsx describe-storage-virtual-machines \
          --query "StorageVirtualMachines[?Name=='${SVM_NAME}'].StorageVirtualMachineId" --output text 2>/dev/null)
for vname in "${VOL_NAMES[@]}"; do
  VID=$(aws_r fsx describe-volumes --query "Volumes[?Name=='${vname}'].VolumeId" --output text 2>/dev/null)
  if [ -n "$VID" ] && [ "$VID" != "None" ]; then
    aws_r fsx delete-volume --volume-id "$VID" \
      --ontap-configuration '{"SkipFinalBackup":true}' >/dev/null 2>&1 \
      && ok "delete-volume requested: $vname ($VID)" || skip "volume $vname delete retry needed"
  else
    skip "Volume absent: $vname"
  fi
done
if [ -n "$SVM_ID" ] && [ "$SVM_ID" != "None" ]; then
  log "Waiting for data volumes to clear before SVM delete..."
  for i in $(seq 1 20); do
    remaining=$(aws_r fsx describe-volumes \
      --query "Volumes[?StorageVirtualMachineId=='${SVM_ID}' && Name!='${SVM_NAME}_root'].VolumeId" --output text 2>/dev/null)
    [ -z "$remaining" ] || [ "$remaining" = "None" ] && break
    sleep 15
  done
  aws_r fsx delete-storage-virtual-machine --storage-virtual-machine-id "$SVM_ID" >/dev/null 2>&1 \
    && ok "delete-svm requested: $SVM_NAME ($SVM_ID)" || skip "SVM delete retry needed (re-run after volumes gone)"
else
  skip "SVM absent: $SVM_NAME"
fi

# =============================================================================
log "Phase 8 — EventBridge bus ${EVENT_BUS} (rules first)"
# =============================================================================
if aws_r events describe-event-bus --name "$EVENT_BUS" >/dev/null 2>&1; then
  for rule in $(aws_r events list-rules --event-bus-name "$EVENT_BUS" --query "Rules[].Name" --output text 2>/dev/null); do
    tids=$(aws_r events list-targets-by-rule --rule "$rule" --event-bus-name "$EVENT_BUS" --query "Targets[].Id" --output text 2>/dev/null)
    [ -n "$tids" ] && aws_r events remove-targets --rule "$rule" --event-bus-name "$EVENT_BUS" --ids $tids >/dev/null 2>&1 || true
    aws_r events delete-rule --name "$rule" --event-bus-name "$EVENT_BUS" >/dev/null 2>&1 || true
  done
  aws_r events delete-event-bus --name "$EVENT_BUS" >/dev/null 2>&1 && ok "Deleted event bus $EVENT_BUS" || skip "event bus delete retry needed"
else
  skip "Event bus absent: $EVENT_BUS"
fi

# =============================================================================
log "Phase 9 — Demo S3 bucket ${DEMO_BUCKET}"
# =============================================================================
if aws_r s3api head-bucket --bucket "$DEMO_BUCKET" >/dev/null 2>&1; then
  aws_r s3 rm "s3://${DEMO_BUCKET}" --recursive >/dev/null 2>&1 || true
  aws_r s3api delete-bucket --bucket "$DEMO_BUCKET" >/dev/null 2>&1 && ok "Deleted bucket $DEMO_BUCKET" || skip "bucket delete retry needed"
else
  skip "Demo bucket absent: $DEMO_BUCKET"
fi

# =============================================================================
log "Phase 10 — AWS Managed Microsoft AD (async ~15-30 min)"
# =============================================================================
if [ "$SKIP_AD" = "true" ]; then
  skip "SKIP_AD=true — leaving Managed AD in place"
else
  ADID=$(aws_r ds describe-directories --query "DirectoryDescriptions[?Name=='${AD_NAME}'].DirectoryId" --output text 2>/dev/null)
  if [ -n "$ADID" ] && [ "$ADID" != "None" ]; then
    aws_r ds delete-directory --directory-id "$ADID" >/dev/null 2>&1 && ok "delete-directory requested: $AD_NAME ($ADID) — async" || skip "AD delete retry needed"
  else
    skip "Managed AD absent: $AD_NAME"
  fi
fi

# =============================================================================
log "Phase 11 — Optional: delete shared FSx file system"
# =============================================================================
if [ "$DELETE_FSX_FILESYSTEM" = "true" ]; then
  FSID=$(aws_r fsx describe-file-systems --query "FileSystems[0].FileSystemId" --output text 2>/dev/null)
  skip "DELETE_FSX_FILESYSTEM=true requested for $FSID — refusing automatic delete (shared by all patterns)."
  echo "    To delete manually: aws fsx delete-file-system --file-system-id $FSID --region $REGION"
else
  skip "Preserving shared FSx file system (default)."
fi

# =============================================================================
log "DONE — verification + manual reminders"
# =============================================================================
echo "  • Amazon Quick subscription is NOT managed here — unsubscribe manually if no longer needed"
echo "    (Quick console → Account settings → Unsubscribe). It bills monthly while active."
echo "  • Re-run this script if any step printed a 'retry needed' (async deps)."
echo '  • Rebuild the KB later with: source scripts/uc29-kb-manifest.local.env && .venv/bin/python scripts/rebuild-uc29-kb.py'
echo
echo "  Residual check:"
aws_r cloudformation describe-stacks --stack-name "$STACK_UC29" >/dev/null 2>&1 && echo "    UC29 stack: STILL PRESENT" || echo "    UC29 stack: gone"
aws_r cloudformation describe-stacks --stack-name "$STACK_UC30" >/dev/null 2>&1 && echo "    UC30 stack: STILL PRESENT" || echo "    UC30 stack: gone"
aws_r opensearchserverless batch-get-collection --names "$AOSS_COLLECTION" --query "collectionDetails[0].id" --output text 2>/dev/null | grep -vq None && echo "    AOSS: STILL PRESENT" || echo "    AOSS: gone"
aws_r ds describe-directories --query "DirectoryDescriptions[?Name=='${AD_NAME}'].DirectoryId" --output text 2>/dev/null | grep -q d- && echo "    Managed AD: deleting/async" || echo "    Managed AD: gone"
