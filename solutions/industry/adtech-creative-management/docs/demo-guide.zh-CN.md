# 创意资产管理 — 资产编目与品牌合规检查演示指南

🌐 **Language / 语言**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 摘要

本演示展示广告创意资产的自动编目和品牌合规检查管道。通过 Rekognition 视觉分析与 Bedrock 品牌指南合规检查，自动化广告制作的质量管理。

**核心信息**：AI 自动分析创意资产，验证品牌指南合规性，并自动生成资产目录。

**预计时间**：3~5 分钟

---

## 逐步部署与验证

### Step 1：前提条件确认

```bash
aws --version          # AWS CLI v2 必须
sam --version          # SAM CLI 1.x 以上
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2：克隆仓库

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/adtech-creative-management
```

### Step 3：SAM 构建和部署

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

### Step 4：手动执行工作流

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 5：确认输出结果

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ID=$(echo $EXECUTION_ARN | rev | cut -d':' -f1 | rev)
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${EXECUTION_ID}/asset-catalog.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## 验证清单

| 检查项 | 验证方法 | 预期结果 |
|--------|---------|---------|
| 媒体文件检测 | Step Functions 执行日志 | Discovery 步骤返回资产文件数 |
| 标签提取 | `asset-catalog.json` 确认 | 每个资产最多附有 50 个标签 |
| 审核检查 | `flagged-assets.json` 确认 | 问题内容已标记并列出 |
| 品牌合规检查 | compliance_status 字段确认 | compliant / non-compliant 正确判定 |
| SNS 警报 | 邮件确认 | 仅在存在审核违规时收到通知 |

---

---

## 截图

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc19-demo/step-functions-graph-view.png)


## 清理

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*本文档是技术演示视频的制作指南。*
