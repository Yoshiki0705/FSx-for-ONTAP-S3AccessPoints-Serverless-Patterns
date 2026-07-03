# UC24：非營利組織 — 補助金申請分類 / 成果媒合

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構](docs/architecture.zh-TW.md) | [示範指南](docs/demo-guide.zh-TW.md)

## 概述

運用 FSx for ONTAP 的 S3 Access Points 的無伺服器工作流程，可自動對補助金申請書進行分類，擷取申請者資訊與預算，並從活動報告中擷取成果指標以與原始補助金目標進行媒合。

## Success Metrics

### Outcome
透過自動化文件處理與分析，實現營運效率提升與法規遵循強化。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 補助金申請分類準確率 | ≥ 85% |
| 成果達成度測量準確率 | ≥ 80% |
| 申請書資料擷取率 | ≥ 90% |
| 報告產生時間 | < 5 分鐘 / 批次 |
| 成本 / 每日執行 | < $1.50 |
| Human Review 必需率 | > 25%（低信賴度分類結果） |

### Measurement Method
Step Functions 執行歷程、AI/ML 服務擷取結果、CloudWatch EMF Metrics（ProcessingDuration、SuccessCount、ErrorCount）。

### Human Review Requirements
- 低信賴度結果需要人工確認
- Critical 警示由領域專家審查
- 定期彙總報告由管理層審查

## 架構

詳細的資料流程圖請參閱[架構文件](docs/architecture.zh-TW.md)。

## 前提條件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署於 VPC 內。若 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（因為請求不會路由至 FSx 資料平面）。請使用 NetworkOrigin=VPC 的 S3 AP，或設定透過 NAT Gateway 的存取。詳情請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 帳戶及適當的 IAM 權限
- FSx for ONTAP 檔案系統（ONTAP 9.17.1P4D3 或更新版本）
- 已啟用 S3 Access Point 的磁碟區
- VPC、私有子網路
- 已啟用 Amazon Bedrock 模型存取（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 呼叫設定

## 部署步驟

```bash
# 前提：需要 AWS SAM CLI。sam build 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
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

> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 若要使用 `aws cloudformation deploy` 命令直接部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3）。

## ⚠️ 效能注意事項

- FSx for ONTAP 的輸送量容量在 **NFS/SMB/S3 AP 之間共用**。以 MapConcurrency=10 進行並行處理時，可能會影響同一磁碟區上的其他工作負載。
- 進行大量檔案的批次處理時，請確認 FSx for ONTAP 的 Throughput Capacity (MBps)，並視需要調整 MapConcurrency。
- 建議：在生產環境中先以 MapConcurrency=5 開始，同時監控 FSx for ONTAP 的 CloudWatch 指標 (ThroughputUtilization)，並逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## 成本估算（每月概算）

> **備註**: ap-northeast-1 區域的概算。實際成本因使用量而異。

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每日 1 次） | ~$8-20 |
| 標準組態 | ~$20-50 |

---

## Governance Note

> 本模式提供技術架構指引。它不構成法律、法規遵循或監理建議。補助金申請中所含個人資訊與組織資訊的處理，必須遵守各資助機構的規定及適用的個人資訊保護法。

> **相關法規**: 日本 NPO 法（特定非營利活動促進法）、公益法人認定法

---

## S3AP Compatibility

關於 FSx for ONTAP S3 AP 的相容性限制、疑難排解與觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
