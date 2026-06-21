# Agriculture & Food — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Summary

This demo showcases automated crop health analysis from drone imagery and traceability document classification. Rekognition/Bedrock for vegetation analysis, Textract/Comprehend for lot information extraction.

**Duration**: 3-5 minutes

---

## Deployment Steps

### Step 1: Prerequisites

```bash
aws --version && sam --version && python3 --version
aws sts get-caller-identity
```

### Step 2: Deploy

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/agri-food-traceability
sam build
sam deploy \
  --stack-name fsxn-agri-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 3: Execute Workflow

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-agri-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

---

## Screenshots

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc21-demo/step-functions-graph-view.png)


## Cleanup

```bash
aws cloudformation delete-stack --stack-name fsxn-agri-demo --region ap-northeast-1
```
