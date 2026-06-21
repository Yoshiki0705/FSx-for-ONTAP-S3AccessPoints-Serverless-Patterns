# Demo Mode Guide — Experience Patterns Without FSx for ONTAP

🌐 **Language / 言語**: [日本語](demo-mode-guide.md) | [English](demo-mode-guide.en.md)

## Overview

The patterns in this repository assume FSx for ONTAP S3 Access Points, but
**Demo Mode** allows you to experience the entire workflow without an FSx for ONTAP environment.

In Demo Mode:
- A standard S3 bucket is used instead of S3 AP
- Test data is automatically placed in the S3 bucket
- The full Discovery → Processing → Report flow operates
- ONTAP REST API calls are skipped (ACL collection, etc.)

## How It Works

The S3ApHelper class internally just passes a value to boto3's `Bucket` parameter.
boto3 processes both S3 Access Point Aliases and standard S3 bucket names through the same S3 API.

```python
# Via S3 AP (production)
helper = S3ApHelper("vol-name-xxxxx-ext-s3alias")

# Via standard S3 bucket (Demo Mode)
helper = S3ApHelper("my-demo-bucket-12345")
```

## Quick Start (5 minutes)

### Step 1: Create a Demo S3 Bucket

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
DEMO_BUCKET="fsxn-s3ap-demo-${ACCOUNT_ID}"

aws s3 mb s3://${DEMO_BUCKET} --region ap-northeast-1
```

### Step 2: Place Test Data

```bash
# For UC1 (legal-compliance)
aws s3 cp test-data/solutions/industry/legal-compliance/ s3://${DEMO_BUCKET}/legal-docs/ --recursive

# For UC6 (semiconductor-eda)
aws s3 cp test-data/solutions/industry/semiconductor-eda/ s3://${DEMO_BUCKET}/eda-designs/ --recursive

# For SAP
aws s3 cp test-data/solutions/sap/erp-adjacent/ s3://${DEMO_BUCKET}/idoc-export/ --recursive
```

### Step 3: Deploy in Demo Mode

```bash
cd solutions/industry/legal-compliance/

sam build && sam deploy --guided \
  --parameter-overrides \
    S3AccessPointAlias=${DEMO_BUCKET} \
    DemoMode=true \
    NotificationEmail=your-email@example.com \
    BedrockModelId=amazon.nova-lite-v1:0
```

When `DemoMode=true` is specified:
- The `S3AccessPointAlias` AllowedPattern validation is relaxed
- ONTAP REST API related parameters (OntapSecretName, OntapManagementIp, etc.) are not required
- VPC related parameters (VpcId, PrivateSubnetIds, etc.) are not required
- The ACL collection Lambda returns mock data

### Step 4: Execute the Workflow

```bash
# Manually execute Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --input '{}'
```

### Step 5: Check Results

```bash
# Check results in the output bucket
aws s3 ls s3://${DEMO_BUCKET}/reports/ --recursive
```

## Demo Mode Supported Patterns

| Pattern | DemoMode Support | Notes |
|---------|:---:|------|
| UC1 legal-compliance | ✅ | ACL collection uses mock data |
| SAP solutions/sap/erp-adjacent | ✅ | ONTAP not required (uses S3 AP only) |
| FC3 solutions/flexcache/rag-enterprise-files | ✅ | ACL collection uses mock data |
| Other UCs | 🔄 | Support being added progressively |

## Limitations

The following features are restricted in Demo Mode:

| Feature | Production Mode | Demo Mode |
|---------|----------------|-----------|
| File reading via S3 AP | ✅ FSx for ONTAP volume | ✅ Standard S3 bucket |
| ONTAP REST API (ACL collection) | ✅ Real data | ⚠️ Mock data |
| VPC execution | ✅ | ❌ Executes outside VPC |
| NTFS ACL parsing | ✅ | ❌ Sample ACL |
| FPolicy event-driven | ✅ | ❌ Polling only |

## Production Migration

After verifying operation in Demo Mode, follow these steps to migrate to production:

1. Create an FSx for ONTAP file system
2. Configure S3 Access Point
3. Change to `DemoMode=false` and set production parameters
4. Redeploy with `sam deploy`

### DemoMode → Production Differences

| Area | DemoMode (Evaluation) | Production (FSx for ONTAP) |
|------|----------------------|------------------------|
| Input source | Standard S3 bucket | FSx for ONTAP S3 Access Point |
| Authorization model | S3 IAM only | IAM + S3 AP policy + ONTAP file ID |
| Network | Public AWS service path | Internet-origin or VPC-origin design decision (**immutable after creation — AP recreation required**) |
| Data | Sample / synthetic data | Customer-managed NAS data |
| Governance | Demo labels only | Data classification + lineage + retention policies |
| Cost | ~$0.10/execution | + FSx for ONTAP infrastructure (~$194/month base) |
| AI evaluation | Operation verification with test data | Accuracy evaluation with domain validation set |

> **Governance Caveat**: Demo Mode is for technical validation. In production environments, always use FSx for ONTAP S3 Access Points and define appropriate IAM policies, network design, data classification, and human review thresholds. Compliance with regulatory requirements in each country/region must be verified under the customer's responsibility.
