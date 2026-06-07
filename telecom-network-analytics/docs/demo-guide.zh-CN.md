# 电信网络分析 — CDR/网络日志异常检测演示指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 概述

本演示展示了 CDR（通话详细记录）和网络设备日志的自动化分析管道。通过基于 Athena 的流量统计和基于 Bedrock 的异常检测，实现网络故障的早期发现和合规报告的自动化。

**核心信息**：AI 自动分析 CDR/网络日志，实时检测异常，并自动生成每日报告。

**预计时间**：3~5 分钟

---

## 逐步部署与验证

### 步骤 1：前置条件检查

```bash
aws --version          # v2.x 必需
sam --version          # 1.x 以上
python3 --version      # 3.9 以上
aws sts get-caller-identity
```

### 步骤 2：克隆仓库

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### 步骤 3：准备示例数据

在 FSx ONTAP 卷上放置示例数据。

### 步骤 4：部署

```bash
sam build

sam deploy \
  --stack-name fsxn-telecom-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    CdrSuffixFilter=".csv,.asn1,.parquet" \
    AnomalyThresholdStdDev=3 \
    CapacityThresholdPercent=80 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### 步骤 5：验证部署

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### 步骤 6：手动执行工作流

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### 步骤 7：验证输出结果

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/ --region ap-northeast-1
```

---

## 验证清单

| 检查项 | 验证方法 | 预期结果 |
|--------|---------|---------|
| CDR 文件检测 | Step Functions 执行日志 | Discovery 步骤返回 CDR 文件数量 |
| Athena 流量统计 | S3 输出桶 | `cdr-stats.json` 已生成 |
| 异常检测 | `anomalies.json` 查看 | 包含标记的异常记录 |
| 每日报告 | S3 桶 | `network-health.json` 存在 |
| SNS 告警 | 邮件接收确认 | 存在重大异常时收到通知邮件 |

---

---

## 截图

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## 清理 (Cleanup)

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
