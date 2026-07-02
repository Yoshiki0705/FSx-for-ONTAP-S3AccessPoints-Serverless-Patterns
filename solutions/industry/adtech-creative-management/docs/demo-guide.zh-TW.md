# 創意資產管理 — 資產編目與品牌合規檢查示範指南

🌐 **Language / 語言**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## 摘要

本示範展示廣告創意資產的自動編目和品牌合規檢查管線。透過 Rekognition 視覺分析與 Bedrock 品牌指南合規檢查，自動化廣告製作的品質管理。

**核心訊息**：AI 自動分析創意資產，驗證品牌指南合規性，並自動產生資產目錄。

**預計時間**：3~5 分鐘

---

## 逐步部署與驗證

### Step 1：先決條件確認

```bash
aws --version          # AWS CLI v2 必須
sam --version          # SAM CLI 1.x 以上
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2：複製儲存庫

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/adtech-creative-management
```

### Step 3：SAM 建置和部署

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
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

### Step 4：手動執行工作流程

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-adtech-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 5：確認輸出結果

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

## 驗證清單

| 檢查項目 | 驗證方法 | 預期結果 |
|----------|---------|---------|
| 媒體檔案偵測 | Step Functions 執行日誌 | Discovery 步驟回傳資產檔案數 |
| 標籤擷取 | `asset-catalog.json` 確認 | 每個資產最多附有 50 個標籤 |
| 審核檢查 | `flagged-assets.json` 確認 | 問題內容已標記並列出 |
| 品牌合規檢查 | compliance_status 欄位確認 | compliant / non-compliant 正確判定 |
| SNS 警示 | 電子郵件確認 | 僅在存在審核違規時收到通知 |

---

---

## 截圖

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc19-demo/step-functions-graph-view.png)


## 清理

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-adtech-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-adtech-demo --region ap-northeast-1
```

---

*本文件是技術簡報用示範影片的製作指南。*
