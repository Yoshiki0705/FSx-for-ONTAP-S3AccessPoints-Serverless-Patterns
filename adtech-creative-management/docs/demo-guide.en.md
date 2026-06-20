# Creative Asset Management — Asset Cataloging and Brand Compliance Check Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo showcases an automated creative asset cataloging and brand compliance checking pipeline. Rekognition visual analysis combined with Bedrock brand guideline compliance checking automates quality control for advertising production.

**Core Message**: AI automatically analyzes creative assets, verifies brand guideline compliance, and generates asset catalogs.

**Estimated Time**: 3–5 minutes

---

## Target Audience & Persona

| Item | Details |
|------|---------|
| **Role** | Creative Operations Manager / Brand Manager |
| **Daily Tasks** | Asset management, brand guideline compliance verification, compliance review |
| **Challenge** | Efficiently verify brand compliance for large volumes of creative assets and enable early detection of problematic content |
| **Expected Outcome** | Reduced asset catalog creation effort and early detection of compliance violations |

---

## Step-by-Step Deployment & Validation

### Step 1: Prerequisites Check

```bash
aws --version          # AWS CLI v2 required
sam --version          # SAM CLI 1.x or later
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: Clone Repository

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/adtech-creative-management
```

### Step 3: Place Sample Data

Place sample creative assets on the FSx for ONTAP volume:

```
/creative-assets/
  campaigns/
    summer-2026/
      banner-001.jpeg       # Web banner ad
      banner-002.png        # Social media image
      video-001.mp4         # Video ad (15 sec)
  brand/
    logo-usage-001.png      # Logo usage example
    product-shot-001.tiff   # Product photography
```

### Step 4: SAM Build and Deploy

```bash
sam build

sam deploy \
  --stack-name fsxn-adtech-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    BrandGuidelinesS3Key=brand-guidelines.json \
    ModerationConfidenceThreshold=80 \
    MaxTagsPerAsset=50 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: Verify Deployment

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Step 6: Execute Workflow Manually

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 7: Verify Output

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/ --region ap-northeast-1

# View asset catalog
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## Validation Checklist

| Check Item | Verification Method | Expected Result |
|------------|-------------------|-----------------|
| Media file detection | Step Functions execution log | Discovery step returns asset file count |
| Label extraction | `asset-catalog.json` | Each asset has up to 50 tags |
| Moderation inspection | `flagged-assets.json` | Problematic content is listed with flags |
| Text extraction | Asset catalog | Text overlays are extracted |
| Brand compliance check | compliance_status field | compliant / non-compliant correctly determined |
| SNS alert | Email inbox | Notification received only when moderation violations exist |

---

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Discovery Lambda timeout | S3 AP access failure from VPC | Check NetworkOrigin setting; Internet Origin AP requires non-VPC execution or NAT Gateway |
| Rekognition call error | Region unsupported or model access denied | Verify Rekognition availability in region |
| Textract call error | Cross-region configuration issue | Verify shared/cross_region_client.py us-east-1 configuration |
| Bedrock invocation failure | Model access not enabled | Enable model access in Bedrock console |
| `AccessDenied` on S3 AP | Incorrect IAM policy ARN format | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` format |

---

---

## Screenshots

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc19-demo/step-functions-graph-view.png)


## Cleanup

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*This document serves as a production guide for technical presentation demo videos.*
