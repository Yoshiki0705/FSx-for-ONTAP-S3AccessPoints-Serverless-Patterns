# 電信網路分析 — CDR/網路日誌異常偵測展示指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 概述

本展示演示了 CDR（通話詳細記錄）和網路設備日誌的自動化分析管道。透過基於 Athena 的流量統計和基於 Bedrock 的異常偵測，實現網路故障的早期發現和合規報告的自動化。

**核心訊息**：AI 自動分析 CDR/網路日誌，即時偵測異常，並自動生成每日報告。

**預計時間**：3~5 分鐘

---

## 逐步部署與驗證

### 步驟 1：前置條件檢查

```bash
aws --version          # v2.x 必需
sam --version          # 1.x 以上
python3 --version      # 3.9 以上
aws sts get-caller-identity
```

### 步驟 2：複製儲存庫

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/telecom-network-analytics
```

### 步驟 3：準備範例資料

在 FSx for ONTAP 磁碟區上放置範例資料。

### 步驟 4：部署

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
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

### 步驟 5：驗證部署

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### 步驟 6：手動執行工作流程

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

### 步驟 7：驗證輸出結果

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

## 驗證清單

| 檢查項目 | 驗證方法 | 預期結果 |
|---------|---------|---------|
| CDR 檔案偵測 | Step Functions 執行日誌 | Discovery 步驟回傳 CDR 檔案數量 |
| Athena 流量統計 | S3 輸出桶 | `cdr-stats.json` 已生成 |
| 異常偵測 | `anomalies.json` 檢視 | 包含標記的異常記錄 |
| 每日報告 | S3 桶 | `network-health.json` 存在 |
| SNS 告警 | 電郵接收確認 | 存在重大異常時收到通知郵件 |

---

---

## 截圖

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## 清理 (Cleanup)

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
