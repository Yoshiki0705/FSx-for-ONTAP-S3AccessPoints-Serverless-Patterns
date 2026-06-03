# Travel & Hospitality — Reservation Document Processing Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated pipeline for processing hotel reservation documents and facility inspection images. Textract/Comprehend extract reservation data while Rekognition/Bedrock analyze facility conditions and generate maintenance recommendations.

**Core message**: AI automatically parses reservation documents to extract structured data, and generates condition scores and maintenance recommendations from facility inspection images.

**Duration**: 3–5 minutes

---

## Step-by-Step Deployment & Validation

### Step 1: Prerequisites

```bash
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: Clone and navigate

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/travel-document-processing
```

### Step 3: Deploy

```bash
sam build
sam deploy \
  --stack-name fsxn-travel-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 4: Execute workflow

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### Step 5: Verify results

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

aws s3 ls s3://${OUTPUT_BUCKET}/reports/$(date +%Y-%m-%d)/ --region ap-northeast-1
```

---

## Cleanup

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-travel-demo --region ap-northeast-1
```
