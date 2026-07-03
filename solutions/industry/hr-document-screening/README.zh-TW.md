# UC27：人力資源 — 履歷篩選 / PII 嚴格模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構](docs/architecture.zh-TW.md) | [示範指南](docs/demo-guide.zh-TW.md)

## 概述

這是一個利用 FSx for ONTAP 的 S3 Access Points，從履歷與經歷書中結構化擷取技能與經驗，並以 PII 嚴格模式排除受保護特徵後進行評分的無伺服器工作流程。

> **重要：法規注意事項**
> 本模式是一個**文件分流與摘要工作流程**，而非自動招聘決策系統。最終招聘決策必須始終由具備資格的人力資源人員做出。使用前，必須驗證其是否符合各國家與地區的勞動法、隱私法規（GDPR、APPI、CCPA 等）以及反歧視要求。輸出中不得包含依受保護特徵進行的排名，評估說明僅以與職務相關的資格與經驗為依據。

## Success Metrics

### Outcome
透過文件處理與分析的自動化，實現營運效率提升與合規強化。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 履歷資料擷取率 | ≥ 90% |
| 評分公平性 | 無受保護特徵偏見（排除年齡、性別、國籍） |
| PII 合規性 | 100%（日誌中零 PII 輸出） |
| 報告生成時間 | < 5 分鐘 / 批次 |
| 成本 / 每日執行 | < $2.00 |
| Human Review 必要率 | > 30%（所有評分結果由人力資源團隊確認） |

### Measurement Method
Step Functions 執行歷程、AI/ML 服務擷取結果、CloudWatch EMF Metrics（ProcessingDuration, SuccessCount, ErrorCount）。

### Human Review Requirements
- 低信賴度結果需要人工確認
- Critical 警示由領域專家審查
- 定期摘要報告由管理層審查

### Output Safeguard Requirements
- 輸出結構描述中不得包含 age/gender/ethnicity/nationality 欄位
- 評估說明僅以與職務相關的資格與經驗為依據
- 偵測到的受保護特徵應在儲存前予以移除
- 所有推薦結果都必須經過人工審查

## 架構

詳細的資料流程圖請參閱[架構文件](docs/architecture.zh-TW.md)。

## 前提條件

> **S3 AP NetworkOrigin 注意**：Discovery Lambda 部署在 VPC 內。如果 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（因為不會路由到 FSx 資料平面）。請使用 NetworkOrigin=VPC 的 S3 AP，或設定經由 NAT Gateway 的存取。詳情請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 帳戶與適當的 IAM 權限
- FSx for ONTAP 檔案系統（ONTAP 9.17.1P4D3 以上）
- 已啟用 S3 Access Point 的磁碟區
- VPC、私有子網路
- 已啟用 Amazon Bedrock 模型存取（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 呼叫設定

## 部署步驟

```bash
# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **注意**：`template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 若使用 `aws cloudformation deploy` 命令直接部署，請使用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳到 S3）。

## ⚠️ 效能注意事項

- FSx for ONTAP 的輸送量容量在 **NFS/SMB/S3 AP 之間共用**。以 MapConcurrency=10 進行平行處理時，可能會影響同一磁碟區上的其他工作負載。
- 進行大量檔案的批次處理時，請確認 FSx for ONTAP 的 Throughput Capacity (MBps)，並視需要調整 MapConcurrency。
- 建議：在生產環境中先以 MapConcurrency=5 開始，並在監控 FSx for ONTAP 的 CloudWatch 指標 (ThroughputUtilization) 的同時逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## 成本估算（每月概算）

> **備註**：ap-northeast-1 區域的概算。實際成本因使用量而異。

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每日 1 次） | ~$8-20 |
| 標準組態 | ~$20-50 |

---

## Governance Note

> 本模式提供技術架構指引。這不構成法律、合規或法規建議。招聘選拔中的 AI 應用必須遵守《職業安定法》與《男女雇用機會均等法》，並排除基於受保護特徵（年齡、性別、國籍等）的偏見。AI 評分僅為參考資訊，最終判斷必須由人力資源人員做出。

> **相關法規**：職業安定法、個人資訊保護法、勞動基準法

---

## S3AP Compatibility

關於 FSx for ONTAP S3 Access Points 的相容性限制、疑難排解與觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
