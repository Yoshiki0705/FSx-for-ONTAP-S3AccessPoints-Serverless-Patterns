# Deployment Guide — FSx for ONTAP S3 Access Points Serverless Patterns

> **Language / 言語**: [日本語](../ja/deployment-guide.md) | [English](../en/deployment-guide.md)

This guide explains how to deploy pattern stacks into an **existing** Amazon FSx for NetApp ONTAP environment. The templates in this repository are **overlay stacks** — they do not create FSx file systems, SVMs, or volumes. Your FSx for ONTAP infrastructure must already be provisioned.

---

## Where to Start

```
Do you have FSx for ONTAP already deployed?
│
├─ YES → Do you want to deploy into production?
│        ├─ YES → Path C (Production) — see "Verified Deployment Paths"
│        └─ NO  → Path A (Quick Start with sam deploy --guided)
│
└─ NO  → Path B (DemoMode) — no FSx required, deploy in ~5 minutes
```

**First-time users**: Start with Path B (DemoMode) to see the pattern working end-to-end, then graduate to Path A/C with your real FSx for ONTAP environment.

---

## Table of Contents

1. [Where to Start](#where-to-start)
2. [Prerequisites](#prerequisites)
3. [Stack Inventory and Tier Classification](#stack-inventory-and-tier-classification)
4. [Parameter Mapping — Existing Resources to Stack Parameters](#parameter-mapping)
5. [VPC Endpoint Conflict Matrix](#vpc-endpoint-conflict-matrix)
6. [Verified Deployment Paths](#verified-deployment-paths)
7. [Cost Estimates](#cost-estimates)
8. [Deployment Time Estimates](#deployment-time-estimates)
9. [Day 2 Operations](#day-2-operations)
10. [Rollback and Cleanup](#rollback-and-cleanup)
11. [ONTAP Version Requirements](#ontap-version-requirements)
12. [Troubleshooting](#troubleshooting)
13. [CI/CD Integration](#cicd-integration)

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| AWS Account | Active account with appropriate IAM permissions |
| FSx for ONTAP | File system (Multi-AZ or Single-AZ) already deployed |
| SVM | At least one Storage Virtual Machine configured |
| Volume | At least one FlexVol or FlexGroup volume with data |
| S3 Access Point | Created and attached to the target volume (`fsx:CreateAndAttachS3AccessPoint`) |
| AWS CLI | v2.15+ with configured credentials |
| SAM CLI | v1.100+ (for `sam build` / `sam deploy`) |
| Python | 3.12+ (Lambda runtime target) |
| ONTAP version | 9.14.1+ (S3 Access Point support); 9.15.1+ for FPolicy mandatory mode |
| VPC | FSx for ONTAP deployed in a VPC; private subnets available for Lambda |
| Secrets Manager | ONTAP admin credentials stored as a JSON secret |

### Minimum IAM Permissions for Deployment

The IAM principal running `cloudformation create-stack` / `sam deploy` needs:

```json
{
  "Effect": "Allow",
  "Action": [
    "cloudformation:*",
    "s3:*",
    "lambda:*",
    "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
    "iam:PassRole", "iam:DeleteRole", "iam:DetachRolePolicy",
    "states:*",
    "events:*",
    "scheduler:*",
    "sns:*",
    "logs:*",
    "ec2:CreateVpcEndpoint", "ec2:DescribeVpcEndpoints",
    "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups",
    "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupEgress",
    "secretsmanager:GetSecretValue",
    "bedrock:InvokeModel"
  ],
  "Resource": "*"
}
```

> **Security note**: For production, scope `Resource` to specific ARNs. The above is a starting point for PoC/evaluation.

### Throughput Consideration

S3 Access Point requests to FSx for ONTAP consume **the same throughput capacity** as NFS/SMB client I/O. If your file system is running near its throughput limit, Lambda functions reading via S3 AP will compete with existing NAS clients. Monitor `TotalThroughput` in CloudWatch and consider increasing throughput capacity if needed. See [S3 AP Performance Considerations](../s3ap-performance-considerations.en.md) for details.

### Obtaining Existing Resource IDs

```bash
# FSx for ONTAP file system
aws fsx describe-file-systems --query "FileSystems[?FileSystemType=='ONTAP'].[FileSystemId,DNSName]" --output table

# SVMs
aws fsx describe-storage-virtual-machines --query "StorageVirtualMachines[].[StorageVirtualMachineId,Name,FileSystemId]" --output table

# Volumes
aws fsx describe-volumes --query "Volumes[?VolumeType=='ONTAP'].[VolumeId,Name,OntapConfiguration.StorageVirtualMachineId]" --output table

# S3 Access Points (attached to FSx for ONTAP)
aws s3control list-access-points --account-id $(aws sts get-caller-identity --query Account --output text) \
  --query "AccessPointList[?contains(Name,'fsx')].[Name,Alias,NetworkOrigin]" --output table

# ONTAP Management IP (from file system DNS or describe output)
# IMPORTANT: Use the FILE SYSTEM management IP, not the SVM management IP.
# The file system management IP is required for cluster-level REST API access.
aws fsx describe-file-systems --file-system-ids fs-XXXXXXXXX \
  --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]" --output text

# SVM UUID (via ONTAP REST API — use file system management IP)
curl -sku admin:PASSWORD "https://<MANAGEMENT-IP>/api/svm/svms?fields=uuid,name" | jq '.records[]'
# Note: -k flag is needed because FSx for ONTAP uses self-signed TLS certificates
```

---

## Stack Inventory and Tier Classification

43 independent CloudFormation/SAM templates organized into 3 deployment tiers based on infrastructure requirements.

### Tier 1 — VPC-External (Lightweight)

No VPC configuration required. Lambda functions access Internet-origin S3 Access Points directly.

| # | Pattern | Path | Key Dependencies |
|---|---------|------|-----------------|
| - | Content Edge Delivery | `solutions/edge/content-delivery/` | S3 AP (Internet-origin) |
| - | Media IVS VOD Publishing | `solutions/edge/media-ivs-vod-publishing/` | S3 AP (Internet-origin), IVS |
| - | KB Self-Service Curation | `solutions/genai/kb-selfservice-curation/` | S3 AP, Bedrock KB |
| - | Quick Agentic Workspace | `solutions/genai/quick-agentic-workspace/` | S3 AP, Bedrock, Athena |

### Tier 2 — VPC-Internal (Standard Industry Patterns)

Lambda functions in VPC private subnets. Requires VPC ID, subnet IDs, and optionally VPC Endpoints.

| # | Pattern | Path | Key Dependencies |
|---|---------|------|-----------------|
| UC1 | Legal Compliance | `solutions/industry/legal-compliance/` | ONTAP API, S3 AP, Athena, Bedrock |
| UC2 | Financial IDP | `solutions/industry/financial-idp/` | ONTAP API, S3 AP, Textract, Bedrock |
| UC3 | Healthcare DICOM | `solutions/industry/healthcare-dicom/` | ONTAP API, S3 AP, Bedrock |
| UC4 | Government Archives | `solutions/industry/government-archives/` | ONTAP API, S3 AP, Bedrock |
| UC5 | Defense Satellite | `solutions/industry/defense-satellite/` | ONTAP API, S3 AP, Bedrock |
| UC6 | Semiconductor EDA | `solutions/industry/semiconductor-eda/` | ONTAP API, S3 AP, Bedrock |
| UC7 | Manufacturing Analytics | `solutions/industry/manufacturing-analytics/` | ONTAP API, S3 AP, Bedrock |
| UC8 | Media VFX | `solutions/industry/media-vfx/` | ONTAP API, S3 AP, Bedrock |
| UC9 | Retail Catalog | `solutions/industry/retail-catalog/` | ONTAP API, S3 AP, Rekognition, Bedrock |
| UC10 | Education Research | `solutions/industry/education-research/` | ONTAP API, S3 AP, Bedrock |
| UC11 | Energy Seismic | `solutions/industry/energy-seismic/` | ONTAP API, S3 AP, Bedrock |
| UC12 | Logistics OCR | `solutions/industry/logistics-ocr/` | ONTAP API, S3 AP, Textract, Bedrock |
| UC13 | Construction BIM | `solutions/industry/construction-bim/` | ONTAP API, S3 AP, Bedrock |
| UC14 | Real Estate Portfolio | `solutions/industry/real-estate-portfolio/` | ONTAP API, S3 AP, Bedrock |
| UC15 | Insurance Claims | `solutions/industry/insurance-claims/` | ONTAP API, S3 AP, Textract, Bedrock |
| UC16 | Transportation Maintenance | `solutions/industry/transportation-maintenance/` | ONTAP API, S3 AP, Bedrock |
| UC17 | Telecom Network Analytics | `solutions/industry/telecom-network-analytics/` | ONTAP API, S3 AP, Bedrock |
| UC18 | Smart City Geospatial | `solutions/industry/smart-city-geospatial/` | ONTAP API, S3 AP, Bedrock |
| UC19 | Autonomous Driving | `solutions/industry/autonomous-driving/` | ONTAP API, S3 AP, Bedrock |
| UC20 | Genomics Pipeline | `solutions/industry/genomics-pipeline/` | ONTAP API, S3 AP, Bedrock |
| UC21 | Chemical SDS Management | `solutions/industry/chemical-sds-management/` | ONTAP API, S3 AP, Bedrock |
| UC22 | Sustainability ESG | `solutions/industry/sustainability-esg-reporting/` | ONTAP API, S3 AP, Bedrock |
| UC23 | Travel Document Processing | `solutions/industry/travel-document-processing/` | ONTAP API, S3 AP, Textract, Bedrock |
| UC24 | AdTech Creative Mgmt | `solutions/industry/adtech-creative-management/` | ONTAP API, S3 AP, Rekognition, Bedrock |
| UC25 | Agri-Food Traceability | `solutions/industry/agri-food-traceability/` | ONTAP API, S3 AP, Bedrock |
| UC26 | HR Document Screening | `solutions/industry/hr-document-screening/` | ONTAP API, S3 AP, Bedrock |
| UC27 | Nonprofit Grant Mgmt | `solutions/industry/nonprofit-grant-management/` | ONTAP API, S3 AP, Bedrock |
| UC28 | Utilities Asset Inspection | `solutions/industry/utilities-asset-inspection/` | ONTAP API, S3 AP, Rekognition, Bedrock |
| SAP | SAP/ERP Adjacent | `solutions/sap/erp-adjacent/` | ONTAP API, S3 AP, Bedrock |
| HA | LifeKeeper Monitoring | `solutions/ha/lifekeeper-monitoring/` | ONTAP API, S3 AP, Bedrock |
| FC1 | FlexCache Anycast DR | `solutions/flexcache/anycast-dr/` | ONTAP API, DynamoDB |
| FC2 | Dynamic Render Workflow | `solutions/flexcache/dynamic-render-workflow/` | ONTAP API, S3 AP |
| FC3 | RAG Enterprise Files | `solutions/flexcache/rag-enterprise-files/` | ONTAP API, S3 AP, Bedrock |
| FC4 | Automotive CAE | `solutions/flexcache/automotive-cae/` | ONTAP API, S3 AP |
| FC5 | Life Sciences Research | `solutions/flexcache/life-sciences-research/` | ONTAP API, S3 AP |
| FC6 | Gaming Build Pipeline | `solutions/flexcache/gaming-build-pipeline/` | ONTAP API, S3 AP |
| FC7 | DevOps CI/CD | `solutions/flexcache/devops-cicd/` | ONTAP API, S3 AP |

### Tier 3 — Infrastructure-Heavy (Networking + Compute)

Requires VPC, subnets, Security Groups, and additional compute (ECS Fargate / EC2).

| # | Pattern | Path | Key Dependencies |
|---|---------|------|-----------------|
| - | FPolicy Event-Driven | `solutions/event-driven/fpolicy/` | VPC, SG, ECS/EC2, SQS, EventBridge, ONTAP API |
| - | Event-Driven Prototype | `solutions/event-driven/prototype/` | VPC, SQS, EventBridge |

---

## Parameter Mapping

### Common Parameters (All Tier 2 Industry Patterns)

| Your Existing Resource | Template Parameter | How to Obtain |
|-----------------------|-------------------|---------------|
| S3 Access Point alias | `S3AccessPointAlias` | `aws s3control list-access-points` → `Alias` field |
| S3 Access Point name | `S3AccessPointName` | Same command → `Name` field |
| ONTAP secret name | `OntapSecretName` | Secrets Manager console / `aws secretsmanager list-secrets` |
| ONTAP management IP | `OntapManagementIp` | `aws fsx describe-file-systems` → Management endpoint |
| SVM UUID | `SvmUuid` | ONTAP REST API: `GET /api/svm/svms` |
| Volume UUID | `VolumeUuid` | ONTAP REST API: `GET /api/storage/volumes?svm.name=<SVM>` |
| VPC ID | `VpcId` | `aws ec2 describe-vpcs` (same VPC as FSx) |
| Private subnet IDs | `PrivateSubnetIds` | `aws ec2 describe-subnets --filters "Name=vpc-id,Values=<VPC>"` |
| Route table IDs | `PrivateRouteTableIds` | `aws ec2 describe-route-tables --filters "Name=vpc-id,Values=<VPC>"` |
| Output S3 bucket | `OutputBucketName` | Create a bucket or use an existing one |
| Notification email | `NotificationEmail` | Your alert recipient email |

### FPolicy Event-Driven Pattern (Tier 3) — Additional Parameters

| Your Existing Resource | Template Parameter | How to Obtain |
|-----------------------|-------------------|---------------|
| VPC ID | `VpcId` | Same VPC as FSx for ONTAP |
| Private subnet IDs | `SubnetIds` | Private subnets in the same AZs as FSx |
| SVM Security Group ID | `FsxnSvmSecurityGroupId` | SG attached to the FSx SVM ENIs |
| Container image URI | `ContainerImage` | Your ECR repository with FPolicy server image |
| SVM management IP | `FsxnMgmtIp` | ONTAP management endpoint |
| SVM UUID | `FsxnSvmUuid` | ONTAP REST API |
| ONTAP credentials secret | `FsxnCredentialsSecret` | Secrets Manager secret name |

### DemoMode — Bypass FSx for ONTAP

Most patterns support `DemoMode=true` which accepts a regular S3 bucket name instead of an S3 AP alias, and skips ONTAP API calls. Use this for:
- Functional validation without FSx for ONTAP
- Partner demonstrations
- CI/CD pipeline testing

---

## VPC Endpoint Conflict Matrix

When deploying multiple stacks in the same VPC, VPC Endpoints can conflict. Understanding the two types is critical:

### Gateway Endpoints (S3, DynamoDB)

- Attached to **route tables**, not subnets
- **No PrivateDNS conflict** — only route-table association conflicts
- **Conflict scenario**: Two stacks both create `AWS::EC2::VPCEndpoint` for S3 Gateway targeting the same route tables → CloudFormation error
- **Resolution**: Set `EnableS3GatewayEndpoint=false` on the second stack (one per VPC is sufficient)

### Interface Endpoints (Secrets Manager, STS, Logs, Bedrock, etc.)

- Attached to **subnets** with ENIs
- **PrivateDNS conflict**: Only one Interface Endpoint per service per VPC can enable `PrivateDnsEnabled=true`
- **Conflict scenario**: Stack A creates `com.amazonaws.region.secretsmanager` with PrivateDNS; Stack B attempts the same → `InvalidParameter: already exists`
- **Resolution**: Set `EnableVpcEndpoints=false` on subsequent stacks; share the existing endpoint

### Conflict Resolution Matrix

| Service | Type | Max per VPC | Parameter to Disable |
|---------|------|-------------|---------------------|
| `com.amazonaws.REGION.s3` | Gateway | 1 (per route table set) | `EnableS3GatewayEndpoint=false` |
| `com.amazonaws.REGION.dynamodb` | Gateway | 1 (per route table set) | N/A (only in FPolicy template) |
| `com.amazonaws.REGION.secretsmanager` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.sts` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.logs` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.bedrock-runtime` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.athena` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |
| `com.amazonaws.REGION.glue` | Interface | 1 (with PrivateDNS) | `EnableVpcEndpoints=false` |

### Recommended Strategy

1. **First stack**: Deploy with `EnableVpcEndpoints=true` and `EnableS3GatewayEndpoint=true`
2. **Subsequent stacks** in the same VPC: Deploy with both set to `false`
3. **Alternative**: Pre-create all needed VPC Endpoints separately, then deploy all stacks with `EnableVpcEndpoints=false`

---

## Verified Deployment Paths

### Path A: Single Pattern Quick Start (Recommended for first deployment)

The simplest path uses SAM CLI's interactive `--guided` mode, which prompts for each parameter:

```bash
# 1. Run preflight checks
./shared/scripts/preflight-check.sh --profile quick-start

# 2. Deploy UC1 (Legal Compliance) as your first pattern
cd solutions/industry/legal-compliance
sam build
sam deploy --guided
# Follow prompts — SAM will ask for each parameter
# Tip: SAM saves your answers to samconfig.toml for future deploys
```

After the first `--guided` deploy, subsequent updates are just:
```bash
sam build && sam deploy
```

### Path B: DemoMode Evaluation (No FSx for ONTAP needed)

```bash
# 1. Create a test S3 bucket with sample data
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="fsxn-demo-${ACCOUNT_ID}"
aws s3 mb "s3://${BUCKET}"

# 2. Upload sample files (use any text/PDF/JSON files you have)
echo '{"sample": "document", "type": "idoc"}' > /tmp/sample.json
aws s3 cp /tmp/sample.json "s3://${BUCKET}/idoc-export/sample.json"

# 3. Deploy with DemoMode=true
cd solutions/sap/erp-adjacent
sam build
sam deploy --parameter-overrides \
  "DemoMode=true" \
  "S3AccessPointAlias=${BUCKET}" \
  "OutputBucketName=fsxn-demo-output-${ACCOUNT_ID}" \
  "NotificationEmail=you@example.com" \
  "OntapSecretArn="
```

### Path C: Production Deployment with Parameter File

```bash
# 1. Run preflight checks
./shared/scripts/preflight-check.sh --profile production

# 2. Deploy using parameter file
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-legal-compliance \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --tags Key=Project,Value=fsxn-s3ap-serverless-patterns Key=UseCase,Value=legal-compliance

# 3. Monitor deployment
aws cloudformation wait stack-create-complete --stack-name fsxn-s3ap-legal-compliance
aws cloudformation describe-stack-events --stack-name fsxn-s3ap-legal-compliance \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED']"
```

### Path D: Multi-Pattern Deployment (Same VPC)

```bash
# 1. Deploy first stack WITH VPC Endpoints
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-uc1 \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND

aws cloudformation wait stack-create-complete --stack-name fsxn-s3ap-uc1

# 2. Deploy second stack WITHOUT VPC Endpoints (shared from first)
aws cloudformation create-stack \
  --stack-name fsxn-s3ap-sap \
  --template-body file://solutions/sap/erp-adjacent/template.yaml \
  --parameters file://cfn-params/sap-erp-adjacent.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND
```

### Path E: FPolicy Event-Driven (Tier 3)

See [Deployment Profiles](../deployment-profiles.en.md) for PoC / Production / Compliance-sensitive profiles.

```bash
# Requires: ECR image built and pushed
# See solutions/event-driven/fpolicy/README.md for container build instructions

aws cloudformation create-stack \
  --stack-name fsxn-fpolicy \
  --template-body file://solutions/event-driven/fpolicy/template.yaml \
  --parameters file://cfn-params/fpolicy-fargate.example.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

---

## Cost Estimates

### Fixed Costs (per stack, monthly)

| Component | Cost | Notes |
|-----------|------|-------|
| Interface VPC Endpoint (each) | ~$7.20/month | $0.01/hour per AZ; typically 2 AZs |
| S3 Gateway Endpoint | Free | No hourly charge |
| NAT Gateway (if needed) | ~$32/month | Required for VPC Lambda → Internet |
| EventBridge Scheduler | ~$1/month | $1 per million invocations |
| CloudWatch Logs | ~$0.50-5/month | Depends on log volume |

### Variable Costs (per execution)

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda | ~$0.0001-0.001/invocation | Depends on memory and duration |
| Bedrock (Nova Lite) | ~$0.00022/1K input tokens | Cheapest option for testing |
| Bedrock (Nova Pro) | ~$0.0008/1K input tokens | Recommended for production |
| Step Functions | $0.025/1K transitions | Standard workflow |
| S3 AP requests | $0.0004/1K GET requests | Standard S3 pricing |

### Monthly Cost by Profile

| Profile | VPC EP | Compute | AI/ML | Total Estimate |
|---------|--------|---------|-------|----------------|
| DemoMode (no FSx) | $0 | ~$1 | ~$2 | **~$3/month** |
| Single UC (VPC EP off) | $0 | ~$5 | ~$10 | **~$15/month** |
| Single UC (VPC EP on) | ~$43 | ~$5 | ~$10 | **~$58/month** |
| Multi-UC (shared VPC EP) | ~$43 | ~$20 | ~$40 | **~$103/month** |
| FPolicy (Fargate) | ~$43 | ~$35 | ~$10 | **~$88/month** |

> These estimates exclude FSx for ONTAP infrastructure costs (which you already have).

---

## Deployment Time Estimates

| Stack Type | `sam build` | `sam deploy` / `create-stack` | Total |
|------------|-------------|-------------------------------|-------|
| Tier 1 (VPC-external) | 30-60s | 2-4 min | **~5 min** |
| Tier 2 (no VPC EP) | 30-60s | 3-5 min | **~6 min** |
| Tier 2 (with VPC EP) | 30-60s | 8-12 min | **~13 min** |
| Tier 3 (FPolicy) | 1-2 min | 10-15 min | **~17 min** |

VPC Endpoint creation is the primary bottleneck (~5-8 minutes for Interface Endpoints).

---

## Day 2 Operations

### Immediate Post-Deploy Verification

```bash
# 1. Confirm stack status
aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].StackStatus"

# 2. Confirm SNS subscription (check email for confirmation link)
aws sns list-subscriptions-by-topic --topic-arn <TOPIC-ARN>

# 3. Trigger a test execution (Step Functions)
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" --output text)
aws stepfunctions start-execution --state-machine-arn "$STATE_MACHINE_ARN"

# 4. Check Lambda connectivity to ONTAP (VPC patterns)
DISCOVERY_FN=$(aws cloudformation describe-stacks --stack-name <STACK-NAME> \
  --query "Stacks[0].Outputs[?OutputKey=='DiscoveryFunctionArn'].OutputValue" --output text)
aws lambda invoke --function-name "$DISCOVERY_FN" /tmp/output.json
cat /tmp/output.json | jq .
```

### Monitoring Metrics

| Metric | Namespace | Alarm Threshold |
|--------|-----------|----------------|
| Lambda Errors | `AWS/Lambda` | > 0 over 5 min |
| Lambda Duration | `AWS/Lambda` | > 80% of timeout |
| Step Functions ExecutionsFailed | `AWS/States` | > 0 over 15 min |
| SQS ApproximateAgeOfOldestMessage | `AWS/SQS` | > 3600s (FPolicy) |
| Custom: FilesProcessed | `FSx for ONTAP S3 AP` | = 0 for 2 consecutive periods |

### Monthly Review Checklist

- [ ] Review CloudWatch cost dashboard — unexpected spikes?
- [ ] Check Lambda concurrent executions — approaching account limits?
- [ ] Verify Bedrock model availability — deprecation notices?
- [ ] Review S3 AP access logs — unauthorized access attempts?
- [ ] Confirm ONTAP secret rotation — expired credentials?
- [ ] Check EventBridge Scheduler — missed executions?
- [ ] Review SNS delivery failures — bounced emails?
- [ ] Validate VPC Endpoint health — rejected connections?
- [ ] Review CloudTrail events — unexpected API calls to FSx or S3 AP resources?

---

## Rollback and Cleanup

### Rollback a Failed Deployment

```bash
# CloudFormation automatic rollback (default behavior)
# If stuck in ROLLBACK_FAILED:
aws cloudformation continue-update-rollback --stack-name <STACK-NAME>

# If rollback fails due to non-empty S3 bucket:
aws s3 rm s3://<BUCKET-NAME> --recursive
aws cloudformation delete-stack --stack-name <STACK-NAME>
```

### Complete Stack Removal

```bash
# 1. Empty any S3 buckets created by the stack
BUCKETS=$(aws cloudformation describe-stack-resources --stack-name <STACK-NAME> \
  --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text)
for bucket in $BUCKETS; do
  aws s3 rm "s3://$bucket" --recursive
done

# 2. Delete the stack
aws cloudformation delete-stack --stack-name <STACK-NAME>
aws cloudformation wait stack-delete-complete --stack-name <STACK-NAME>

# 3. Verify no orphaned resources
aws cloudformation list-stacks --stack-status-filter DELETE_FAILED \
  --query "StackSummaries[?contains(StackName,'fsxn')]"
```

### Cleanup Order for Multi-Stack Deployments

Remove stacks in reverse deployment order:
1. Application stacks (UC patterns, FPolicy consumers)
2. FPolicy Event-Driven stack (if deployed)
3. Stack that owns VPC Endpoints (last — others depend on them)

> The S3 Access Point itself is NOT managed by these stacks. Deleting stacks does not remove your S3 AP or affect your FSx for ONTAP data.

---

## ONTAP Version Requirements

| Feature | Minimum ONTAP Version | Patterns Affected |
|---------|----------------------|-------------------|
| S3 Access Points | 9.14.1 | All patterns |
| FPolicy Persistent Store | 9.14.1 | event-driven/fpolicy |
| FPolicy mandatory mode | 9.15.1 | event-driven/fpolicy (Production profile) |
| FlexCache with S3 AP | 9.14.1 | flexcache/* |
| S3 AP with NFS/SMB coexistence | 9.14.1 | All patterns |
| SnapMirror with S3 AP volumes | 9.14.1 | DR scenarios |

### Checking Your ONTAP Version

```bash
# Via ONTAP REST API
curl -sku admin:PASSWORD "https://<MANAGEMENT-IP>/api/cluster?fields=version" | jq '.version'

# Via AWS CLI
aws fsx describe-file-systems --file-system-ids fs-XXXXXXXXX \
  --query "FileSystems[0].OntapConfiguration.OntapVersion" --output text
```

### Known Constraints

- **S3 AP NetworkOrigin is immutable** — cannot change from Internet to VPC or vice versa after creation.
- **ONTAP S3 server conflicts with S3 AP** — if the SVM has an ONTAP native S3 server enabled (`vserver object-store-server`), S3 Access Point creation will fail. Use a different SVM or remove the S3 server first.
- **S3 AP does not support Presigned URLs** — documented as unsupported.
- **Maximum object size via PutObject is 5 GB** — use Multipart Upload for larger files.
- **S3 Gateway VPC Endpoint does NOT route Internet-origin S3 AP traffic** — use NAT Gateway or VPC-external Lambda instead.

### WINDOWS User Type S3 Access Points — AD Requirements

S3 Access Points support two user types: `UNIX` (default) and `WINDOWS`. The WINDOWS type maps file ownership and ACLs to Active Directory identities, enabling Windows-native access control on FSx for ONTAP volumes exposed via S3 AP.

**Prerequisites for WINDOWS-type S3 AP creation:**

1. **SVM must be joined to an Active Directory domain** — attempting to create a WINDOWS-type S3 AP on an SVM that is not AD-joined will fail immediately.
2. **AD environment must be reachable** — the SVM needs DNS resolution and network connectivity to the AD domain controllers (ports 53, 88, 389, 445).

**Critical: WindowsUser.Name must NOT include the domain prefix**

When creating or using a WINDOWS-type S3 Access Point, specify the username only:

```bash
# CORRECT — username only
aws fsx create-and-attach-s3-access-point \
  --file-system-id fs-XXXXXXXXX \
  --s3-access-point-configuration '{
    "Namespace": "s3ap-win",
    "FileSystemUserType": "WINDOWS",
    "WindowsUser": {"Name": "Admin"},
    "NetworkOrigin": "Internet"
  }'

# INCORRECT — domain prefix causes AccessDenied on data-plane operations
# "WindowsUser": {"Name": "DEMO\\Admin"}  ← DO NOT USE
```

The domain prefix (`DOMAIN\username`) is accepted at the CLI/API level without error, but subsequent data-plane operations (ListObjects, GetObject, PutObject) will return `AccessDenied`. This is a known behavior, not a transient error.

**Setting up the AD environment:**

Use the included infrastructure template and join script:

```bash
# 1. Deploy AD + test EC2 instances
aws cloudformation create-stack \
  --stack-name demo-ad-env \
  --template-body file://infrastructure/demo-ad-environment.yaml \
  --parameters file://params/demo-ad-environment.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Wait for AD creation (~20-30 minutes for AWS Managed AD)
aws cloudformation wait stack-create-complete --stack-name demo-ad-env

# 3. Join SVM to the AD domain
./scripts/demo-ad-join-svm.sh --stack-name demo-ad-env --svm-name svm1

# 4. Create WINDOWS-type S3 AP (now possible)
aws fsx create-and-attach-s3-access-point ...
```

See [infrastructure/demo-ad-environment.yaml](../../infrastructure/demo-ad-environment.yaml) and [scripts/demo-ad-join-svm.sh](../../scripts/demo-ad-join-svm.sh) for details.

---

## Troubleshooting

### Common Deployment Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Parameter S3AccessPointAlias failed regex` | Alias doesn't match `^[a-z0-9-]+-ext-s3alias$` | Verify alias via `aws s3control list-access-points`; ensure it ends with `-ext-s3alias` |
| `VpcEndpoint already exists` | Another stack or manual creation owns this endpoint | Set `EnableVpcEndpoints=false` and `EnableS3GatewayEndpoint=false` |
| `Unable to assume role` | Lambda execution role not yet propagated | Wait 30s and retry; IAM role propagation can take up to 10s |
| `Network timeout` connecting to ONTAP | Lambda in VPC cannot reach ONTAP management LIF | Verify SG allows egress to port 443; confirm ONTAP management IP is reachable from private subnets |
| `Access Denied` on S3 AP operations | IAM policy or S3 AP resource policy mismatch | Check both IAM identity policy and S3 AP resource policy allow the action |
| `Secret not found` | Secret name typo or wrong region | Verify with `aws secretsmanager describe-secret --secret-id <NAME>` |
| `ONTAP S3 server exists on SVM` | ONTAP native S3 conflicts with FSx for ONTAP S3 AP | Use a different SVM or remove the ONTAP S3 server (see Known Constraints) |
| `Template size exceeds 51200 bytes` | Template too large for `--template-body` | Use `sam deploy` (handles S3 upload) or upload template to S3 first |
| `Bedrock InvokeModel AccessDenied` | Model access not enabled in the region | Enable model access in Bedrock console; use cross-region inference profile ID |
| `AccessDenied` on WINDOWS S3 AP data ops | `WindowsUser.Name` contains domain prefix | Remove domain prefix — use `"Admin"` not `"DOMAIN\\Admin"` |
| S3 AP creation fails (WINDOWS type) | SVM not joined to AD domain | Join SVM to AD first: `./scripts/demo-ad-join-svm.sh` |

### Debugging Connectivity

```bash
# Test if Lambda can reach ONTAP management IP (from your local machine)
# Note: This tests YOUR network path, not Lambda's VPC path
curl -sk "https://<MANAGEMENT-IP>/api/cluster" --connect-timeout 5

# Check Lambda VPC configuration
aws lambda get-function-configuration --function-name <FUNCTION-NAME> \
  --query "VpcConfig.{SubnetIds:SubnetIds,SecurityGroupIds:SecurityGroupIds}"

# Check Security Group egress rules
aws ec2 describe-security-groups --group-ids <SG-ID> \
  --query "SecurityGroups[0].IpPermissionsEgress"
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy Pattern
on:
  push:
    branches: [main]
    paths: ['solutions/industry/legal-compliance/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/GitHubActions-Deploy
          aws-region: ap-northeast-1

      - name: Setup SAM CLI
        uses: aws-actions/setup-sam@v2

      - name: Preflight check
        run: ./shared/scripts/preflight-check.sh --profile production --vpc ${{ vars.VPC_ID }}
        env:
          ONTAP_SECRET_NAME: ${{ vars.ONTAP_SECRET_NAME }}

      - name: SAM Build & Deploy
        run: |
          cd solutions/industry/legal-compliance
          sam build
          sam deploy --no-confirm-changeset --no-fail-on-empty-changeset \
            --parameter-overrides $(cat ../../../cfn-params/uc1-legal-compliance.json | jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' | tr '\n' ' ')
```

### Using Change Sets for Production Updates

For stacks already deployed, use change sets instead of `create-stack`:

```bash
# Create a change set (preview changes before applying)
aws cloudformation create-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --template-body file://solutions/industry/legal-compliance/template.yaml \
  --parameters file://cfn-params/uc1-legal-compliance.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --change-set-name update-$(date +%Y%m%d-%H%M%S)

# Review the change set
aws cloudformation describe-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --change-set-name update-XXXXXXXX

# Execute (apply) the change set
aws cloudformation execute-change-set \
  --stack-name fsxn-s3ap-legal-compliance \
  --change-set-name update-XXXXXXXX
```

---

---

## Amplify Gen2 File Portal

The Amplify Gen2 File Portal is a separate deployment from the SAM/CloudFormation pattern stacks above. It provides a browser-based UI for file browsing, AI processing, and workflow management against the same FSx for ONTAP S3 Access Points.

### What it deploys

| Resource | Purpose |
|----------|---------|
| Cognito User Pool + Identity Pool | Authentication + S3 API credentials |
| AppSync GraphQL API | Frontend ↔ backend communication |
| Lambda x8 (inline, Python 3.12 ARM64) | File listing, presigned URLs, AI services |
| DynamoDB table | Job execution history |

### Deployment steps

```bash
cd solutions/amplify-portal
make install
cp amplify/portal-config.example.ts amplify/portal-config.ts
# Edit portal-config.ts: set region and s3ApAlias (from your S3 AP)
# Edit src/portal-settings.ts: set region, accountId, s3ApAlias (for Upload tab)
make sandbox       # ~10-15 min first time, ~7s code-only, ~3min infra changes
make dev           # Start local dev server → http://localhost:5173
```

### Finding your parameter values

```bash
# S3 AP Alias
aws fsx describe-s3-access-point-attachments \
  --query "S3AccessPointAttachments[?Lifecycle=='AVAILABLE'].S3AccessPoint.Alias" \
  --region ap-northeast-1 --output text

# Account ID (for portal-settings.ts)
aws sts get-caller-identity --query Account --output text

# Step Functions ARN (if you've deployed a UC pattern)
aws stepfunctions list-state-machines --region ap-northeast-1 \
  --query "stateMachines[*].[name,stateMachineArn]" --output table
```

### Deployment timing (verified 2026-07-20)

| Step | Duration | Notes |
|------|----------|-------|
| `npm install` | ~1 min | First time only (lockfile cached) |
| `make sandbox` (first) | 4-5 min | CDK bootstrap + full stack creation |
| `make sandbox` (incremental) | 20-40s | Only changed resources redeployed |
| `make sandbox-delete` | ~2 min | Full resource cleanup |

### Test user creation (CLI)

After sandbox deploy, create a test user without email verification:

```bash
USER_POOL_ID=$(jq -r '.auth.user_pool_id' amplify_outputs.json)
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username demo@example.com \
  --user-attributes Name=email,Value=demo@example.com Name=email_verified,Value=true \
  --temporary-password 'Demo1234!' \
  --region ap-northeast-1

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username demo@example.com \
  --password 'Demo1234!' \
  --permanent \
  --region ap-northeast-1
```

### Portal tabs (6)

| Tab | Function |
|-----|----------|
| Files | Browse files, preview images, generate share links, AI Q&A |
| Upload | Storage Browser — drag-and-drop upload, delete, copy (S3 AP direct) |
| Process | Select UC pattern → trigger Step Functions workflow |
| Results | Real-time execution status + output display |
| History | Past job list (DynamoDB, per-user scoped) |
| Analytics | Athena SQL queries against Glue Data Catalog |

### Cleanup

```bash
cd solutions/amplify-portal
make sandbox-delete   # Deletes Cognito, AppSync, Lambda, DynamoDB
make sfn-test-delete  # If you created a test state machine
```

> **Cost note**: Sandbox resources persist until explicitly deleted. No scheduled costs (all serverless/on-demand), but the Cognito User Pool and AppSync API exist as long as the stack is active. Always `make sandbox-delete` after testing.

### Detailed documentation

- [Portal Tabs Guide (with screenshots)](../../solutions/amplify-portal/docs/portal-tabs-guide.md)
- [Portal README](../../solutions/amplify-portal/README.md)
- [Amplify Hosting Production Guide](amplify-hosting-production-guide.md)

---

## Related Documents

- [Demo Mode Guide](../demo-mode-guide.en.md) — Run patterns without FSx for ONTAP
- [Cost Calculator](../cost-calculator.md) — Detailed cost estimation
- [S3 AP Compatibility Notes](../s3ap-compatibility-notes.en.md) — Known constraints and workarounds
- [Deployment Profiles (FPolicy)](../deployment-profiles.en.md) — PoC / Production / Compliance profiles
- [Pattern Selection Guide](../pattern-selection-guide.en.md) — Choose the right pattern for your use case
- [ONTAP Integration Notes](../ontap-integration-notes.en.md) — NAS coexistence and identity
- [Preflight Check Script](../../shared/scripts/preflight-check.sh) — Automated pre-deployment validation
- [Sample Parameter Files](../../cfn-params/) — Ready-to-use CloudFormation parameter examples
