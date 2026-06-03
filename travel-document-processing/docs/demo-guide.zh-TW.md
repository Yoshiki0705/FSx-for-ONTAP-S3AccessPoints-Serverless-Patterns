# 旅行與飯店業 — 預約文件處理示範指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 概述

本示範展示飯店預約文件和設施檢查影像的自動分析管線。通過 Textract/Comprehend 擷取預約資料，Rekognition/Bedrock 分析設施狀態並生成維護建議。

**預計時間**: 3~5 分鐘

---

## 部署和驗證步驟

### Step 1: 前置條件

```bash
aws --version && sam --version && python3 --version
aws sts get-caller-identity
```

### Step 2: 部署

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/travel-document-processing
sam build && sam deploy \
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

### Step 3: 執行工作流程

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

## 清理

```bash
aws cloudformation delete-stack --stack-name fsxn-travel-demo --region ap-northeast-1
```
