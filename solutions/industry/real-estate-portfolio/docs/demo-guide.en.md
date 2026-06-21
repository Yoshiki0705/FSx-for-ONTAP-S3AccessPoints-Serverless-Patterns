# Real Estate — Property Image Analysis / Contract Extraction Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated pipeline where AI/ML services analyze files on FSx for ONTAP via S3 Access Points.

**Estimated Time**: 3–5 minutes

---

## Step-by-Step Deployment & Validation

### Step 1: Prerequisites Check

```bash
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: Clone Repository

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/real-estate-portfolio
```

### Step 3: Place Sample Data

Place sample data on the FSx for ONTAP volume.

### Step 4: SAM Build & Deploy

```bash
sam build
cp samconfig.toml.example samconfig.toml
sam deploy \
  --stack-name fsxn-real-estate-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: Manual Workflow Execution

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-real-estate-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### Step 6: Verify Output

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-real-estate-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/${TODAY}/ --region ap-northeast-1
```

---

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|-----------|
| Discovery Lambda timeout | S3 AP access failure | Check NetworkOrigin setting |
| `AccessDenied` | IAM policy ARN format error | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` format |
| AI/ML service error | Region configuration | Check Cross-Region settings |

---

---

## Screenshots

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc26-demo/step-functions-graph-view.png)


## Cleanup

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-real-estate-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate-demo --region ap-northeast-1
```

---

*This document is a production guide for technical presentation demo videos.*
