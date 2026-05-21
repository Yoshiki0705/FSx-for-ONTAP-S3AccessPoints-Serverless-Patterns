# Quick Start Guide

Deploy your first FSx for ONTAP S3 Access Points serverless pattern in ~30 minutes.

## Prerequisites

- AWS Account with appropriate permissions (IAM, Lambda, Step Functions, S3, FSx)
- AWS CLI v2 configured (`aws configure`)
- AWS SAM CLI installed (`sam --version`)
- Python 3.12+
- An existing FSx for ONTAP file system with at least one volume
- An S3 Access Point attached to the volume (see Step 1 below)

> **Don't have an FSx for ONTAP file system yet?**  
> Use our quickstart CloudFormation template: `shared/cfn/fsxn-s3ap-quickstart.yaml`

---

## Step 1: Create an S3 Access Point (if not already created)

S3 Access Points for FSx for ONTAP provide read-only S3 API access to files on your ONTAP volumes.

### Via AWS Console or CLI

Follow the official guide:  
📖 [Creating S3 Access Points for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fsxn-creating-access-points.html)

### Key requirements:

- **File system identity**: You must specify either:
  - UNIX: UID/GID (e.g., `uid=1001, gid=1001`)
  - Windows: Domain user (e.g., `CORP\svc-s3ap`)
- **IAM permissions**: The Lambda execution role needs `s3:GetObject` and `s3:ListBucket` on the Access Point ARN
- **Network**: Lambda must NOT be in a VPC, or must have NAT Gateway access (S3 AP for FSx does not work via VPC Gateway Endpoint)

### Example CLI creation:

```bash
aws s3control create-access-point \
  --account-id 123456789012 \
  --name my-fsxn-s3ap \
  --bucket "arn:aws:fsx:ap-northeast-1:123456789012:file-system/fs-0123456789abcdef0"
```

> **Note**: After creation, note the **S3 Access Point Alias** (e.g., `my-fsxn-s3ap-abc123.s3.ap-northeast-1.amazonaws.com`). You'll need this for deployment.

---

## Step 2: Place test files on the volume

Mount the FSx for ONTAP volume via NFS and create some test files:

```bash
# Mount the volume (replace <svm-dns> with your SVM's DNS name)
sudo mount -t nfs -o nfsvers=4.1 <svm-dns>:/vol1 /mnt/fsxn

# Create test directory structure
mkdir -p /mnt/fsxn/contracts /mnt/fsxn/reports /mnt/fsxn/invoices

# Create test files
echo "This is a sample contract document for testing." > /mnt/fsxn/contracts/sample-contract-2024.txt
echo "Q4 Financial Report - Revenue increased 15% YoY." > /mnt/fsxn/reports/q4-report.txt
echo "Invoice #12345 - Amount: $50,000 - Due: 2024-03-01" > /mnt/fsxn/invoices/inv-12345.txt

# Verify files are accessible
ls -la /mnt/fsxn/
```

---

## Step 3: Store ONTAP credentials in Secrets Manager

Create a secret for ONTAP REST API access (used by some patterns for metadata enrichment):

```bash
aws secretsmanager create-secret \
  --name fsxn-s3ap-demo/ontap-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD","endpoint":"management.fs-0123456789abcdef0.fsx.ap-northeast-1.amazonaws.com"}'
```

Note the Secret ARN for deployment.

---

## Step 4: Deploy a UC template

We'll deploy the **Legal Compliance** pattern (UC1) as a first example:

```bash
# Navigate to the use case directory
cd legal-compliance

# Build with SAM
sam build

# Deploy with guided prompts
sam deploy --guided --stack-name fsxn-s3ap-uc1-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    OntapSecretArn=<your-secret-arn> \
    ScheduleExpression="rate(1 hour)" \
    OutputBucketName=fsxn-s3ap-demo-output-$(aws sts get-caller-identity --query Account --output text)
```

### Parameters explained:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `S3AccessPointAlias` | Your S3 AP alias or ARN | `my-fsxn-s3ap-abc123` |
| `OntapSecretArn` | Secrets Manager ARN for ONTAP creds | `arn:aws:secretsmanager:...` |
| `ScheduleExpression` | How often to run | `rate(1 hour)`, `cron(0 9 * * ? *)` |
| `OutputBucketName` | S3 bucket for results | `my-output-bucket` |

---

## Step 5: Verify execution

### Check Step Functions

```bash
# List recent executions
aws stepfunctions list-executions \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name fsxn-s3ap-uc1-demo \
    --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn`].OutputValue' \
    --output text) \
  --max-results 5
```

### Check CloudWatch Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/fsxn-s3ap-uc1-demo-DiscoveryFunction --since 1h
```

### Check S3 output

```bash
# List output files
aws s3 ls s3://fsxn-s3ap-demo-output-$(aws sts get-caller-identity --query Account --output text)/
```

### Manual trigger (if you don't want to wait for the schedule)

```bash
# Start a manual execution
aws stepfunctions start-execution \
  --state-machine-arn $(aws cloudformation describe-stacks \
    --stack-name fsxn-s3ap-uc1-demo \
    --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn`].OutputValue' \
    --output text) \
  --input '{}'
```

---

## Step 6: Clean up

```bash
# Delete the stack
sam delete --stack-name fsxn-s3ap-uc1-demo

# Optionally delete the output bucket (must be empty first)
aws s3 rm s3://fsxn-s3ap-demo-output-$(aws sts get-caller-identity --query Account --output text) --recursive
aws s3 rb s3://fsxn-s3ap-demo-output-$(aws sts get-caller-identity --query Account --output text)

# Optionally delete the secret
aws secretsmanager delete-secret --secret-id fsxn-s3ap-demo/ontap-credentials --force-delete-without-recovery
```

---

## Next Steps

| What to do next | Where to look |
|-----------------|---------------|
| Try EVENT_DRIVEN mode with FPolicy | `event-driven-fpolicy/` |
| Deploy SAP/ERP adjacent workflow | `sap-erp-adjacent/` |
| Review Deployment Profiles | `docs/deployment-profiles.md` |
| Plan for production | `docs/production-readiness.md` |
| See all use case patterns | `README.md` |
| Enterprise workload examples | `docs/enterprise-workload-examples.md` |

---

## Troubleshooting

### "Access Denied" on ListObjectsV2

- Verify the Lambda execution role has `s3:ListBucket` permission on the S3 Access Point ARN
- Check the S3 Access Point resource policy allows the Lambda role
- Ensure the file system identity has read access to the target directory

### Lambda timeout

- S3 Access Points for FSx do NOT work via S3 VPC Gateway Endpoints
- Lambda must be outside VPC, or use NAT Gateway for outbound access
- Increase Lambda timeout to 60s+ for large directory listings

### "No files found"

- Verify files exist on the volume at the expected path
- Check the `FilePrefix` parameter matches your directory structure
- Ensure the S3 AP file system identity has permission to read the files
