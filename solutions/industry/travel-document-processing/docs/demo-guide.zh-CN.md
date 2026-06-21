# 旅行与酒店业 — 预订文档处理演示指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 概述

本演示展示酒店预订文档和设施检查图像的自动分析管道。通过 Textract/Comprehend 提取预订数据，Rekognition/Bedrock 分析设施状态并生成维护建议。

**预计时间**: 3~5 分钟

---

## 部署和验证步骤

### Step 1: 前置条件

```bash
aws --version && sam --version && python3 --version
aws sts get-caller-identity
```

### Step 2: 部署

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/travel-document-processing
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

### Step 3: 执行工作流

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

---

## 截图

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc20-demo/step-functions-graph-view.png)


## 清理

```bash
aws cloudformation delete-stack --stack-name fsxn-travel-demo --region ap-northeast-1
```
