# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

基於 Amazon FSx for NetApp ONTAP S3 Access Points 的產業專屬無伺服器自動化模式集合。

> **本儲存庫的定位**: 這是一個「用於學習設計決策的參考實作」。部分使用案例已在 AWS 環境中完成 E2E 驗證，其他使用案例也已完成 CloudFormation 部署、共用 Discovery Lambda 及關鍵元件的功能驗證。本儲存庫以從 PoC 到正式環境的漸進式應用為目標，透過具體程式碼展示成本最佳化、安全性和錯誤處理的設計決策。

## 相關文章

本儲存庫是以下文章的實踐配套：

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

文章解釋架構設計思想和權衡取捨，本儲存庫提供具體的、可重複使用的實作模式。

## 概述

本儲存庫提供 **5 種產業專屬模式**，透過 **S3 Access Points** 對儲存在 FSx for NetApp ONTAP 上的企業資料進行無伺服器處理。

> 以下將 FSx for ONTAP S3 Access Points 簡稱為 **S3 AP**。

每個使用案例都是獨立的 CloudFormation 範本，共用模組（ONTAP REST API 用戶端、FSx 輔助工具、S3 AP 輔助工具）位於 `shared/` 目錄中。

### 主要特性

- **輪詢架構**: EventBridge Scheduler + Step Functions（FSx ONTAP S3 AP 不支援 `GetBucketNotificationConfiguration`）
- **共用模組分離**: OntapClient / FsxHelper / S3ApHelper 在所有使用案例中重複使用
- **CloudFormation / SAM Transform 架構**: 每個使用案例都是獨立的 CloudFormation 範本（使用 SAM Transform）
- **安全優先**: 預設啟用 TLS 驗證、最小權限 IAM、KMS 加密
- **成本最佳化**: 高成本常駐資源（VPC Endpoints 等）為選用項目

## 使用案例

| # | 目錄 | 產業 | 模式 | AI/ML 服務 | 區域相容性 |
|---|------|------|------|-----------|-----------|
| UC1 | `legal-compliance/` | 法務合規 | 檔案伺服器稽核與資料治理 | Athena, Bedrock | 所有區域 |
| UC2 | `financial-idp/` | 金融服務 | 合約/發票處理 (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: 跨區域 |
| UC3 | `manufacturing-analytics/` | 製造業 | IoT 感測器日誌與品質檢測 | Athena, Rekognition | 所有區域 |
| UC4 | `media-vfx/` | 媒體與娛樂 | VFX 算繪管線 | Rekognition, Deadline Cloud | Deadline Cloud 區域 |
| UC5 | `healthcare-dicom/` | 醫療保健 | DICOM 影像分類與去識別化 | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: 跨區域 |

> **區域限制**: Amazon Textract 和 Amazon Comprehend Medical 並非在所有區域可用（例如 ap-northeast-1）。可透過 `TEXTRACT_REGION` 和 `COMPREHEND_MEDICAL_REGION` 參數進行跨區域呼叫。詳見[區域相容性矩陣](docs/region-compatibility.md)。

## 快速開始

### 先決條件

- AWS CLI v2
- Python 3.12+
- 已啟用 S3 Access Points 的 FSx for NetApp ONTAP
- 儲存在 AWS Secrets Manager 中的 ONTAP 憑證

### 部署

> ⚠️ **對現有環境的影響**
>
> - `EnableS3GatewayEndpoint=true` 會向您的 VPC 新增 S3 Gateway Endpoint。如果已存在，請設定為 `false`。
> - `ScheduleExpression` 會觸發定期的 Step Functions 執行。如果不需要立即使用，請在部署後停用排程。
> - 如果 S3 儲存貯體包含物件，堆疊刪除可能會失敗。刪除前請清空儲存貯體。
> - VPC Endpoint 刪除需要 5-15 分鐘。Lambda ENI 釋放可能會延遲 Security Group 的刪除。
>
> **區域**: 建議使用 `us-east-1` 或 `us-west-2` 以獲得完整的 AI/ML 服務可用性。詳見[區域相容性](docs/region-compatibility.md)。

```bash
# 設定區域
export AWS_DEFAULT_REGION=us-east-1

# 打包 Lambda 函式
./scripts/deploy_uc.sh legal-compliance package

# 部署 CloudFormation 堆疊
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ParameterKey=PrivateRouteTableIds,ParameterValue=<your-route-table-ids> \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false
```

## 文件

| 文件 | 說明 |
|------|------|
| [部署指南](docs/guides/deployment-guide.md) | 逐步部署說明 |
| [維運指南](docs/guides/operations-guide.md) | 監控與維運流程 |
| [疑難排解指南](docs/guides/troubleshooting-guide.md) | 常見問題與解決方案 |
| [成本分析](docs/cost-analysis.md) | 成本結構與最佳化 |
| [區域相容性](docs/region-compatibility.md) | 各區域服務可用性 |
| [擴充模式](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [驗證結果](docs/verification-results.md) | AWS 環境測試結果 |

## 技術堆疊

| 層級 | 技術 |
|------|------|
| 語言 | Python 3.12 |
| IaC | CloudFormation (YAML) |
| 運算 | AWS Lambda |
| 編排 | AWS Step Functions |
| 排程 | Amazon EventBridge Scheduler |
| 儲存 | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| 安全 | Secrets Manager, KMS, IAM 最小權限 |
| 測試 | pytest + Hypothesis (PBT) |

## 授權條款

MIT License。詳見 [LICENSE](LICENSE)。
