# UC26: 不動產 — 物件影像分析 / 合約擷取

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構圖](docs/architecture.zh-TW.md) | [演示指南](docs/demo-guide.zh-TW.md)

## 概述

這是一個運用 FSx for ONTAP 的 S3 Access Points 的無伺服器工作流程，可從物件影像中擷取特徵並自動產生物件說明、從租賃合約中擷取條款，並透過 PII 偵測實現隱私保護。

## Success Metrics

### Outcome
透過文件處理與分析的自動化，實現營運效率提升與合規強化。

### Metrics
| 指標 | 目標值（範例） |
|------|--------------|
| 物件特徵擷取準確率 | ≥ 85% |
| PII 偵測率 | ≥ 95% |
| 合約條款擷取準確率 | ≥ 90% |
| 報告產生時間 | < 5 分鐘 / 批次 |
| 成本 / 每日執行 | < $2.50 |
| Human Review 必需比例 | > 20%（PII 偵測影像全部確認） |

### Measurement Method
Step Functions 執行歷史、AI/ML 服務擷取結果、CloudWatch EMF Metrics（ProcessingDuration、SuccessCount、ErrorCount）。

### Human Review Requirements
- 低信賴度結果需要人工確認
- Critical 警示由領域專家審查
- 定期彙總報告由管理層審查

## 架構

有關詳細的資料流程圖，請參閱[架構文件](docs/architecture.zh-TW.md)。

## 前提條件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署於 VPC 內。若 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（因為請求不會路由至 FSx for ONTAP 資料平面）。請使用 NetworkOrigin=VPC 的 S3 AP，或設定透過 NAT Gateway 的存取。詳情請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 帳戶及適當的 IAM 權限
- FSx for ONTAP 檔案系統（ONTAP 9.17.1P4D3 以上）
- 已啟用 S3 Access Point 的磁碟區
- VPC、私有子網路
- 已啟用 Amazon Bedrock 模型存取（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 呼叫設定

## 部署步驟

```bash
# 前提條件：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-real-estate \
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

> **注意**: `template.yaml` 用於搭配 SAM CLI（`sam build` + `sam deploy`）使用。
> 若使用 `aws cloudformation deploy` 命令直接部署，請改用 `template-deploy.yaml`（需要預先打包 Lambda zip 檔案並上傳至 S3）。

## ⚠️ 效能注意事項

- FSx for ONTAP 的傳輸量容量在 **NFS/SMB/S3 AP 之間共用**。以 MapConcurrency=10 進行平行處理時，可能會影響同一磁碟區上的其他工作負載。
- 進行大量檔案批次處理時，請確認 FSx for ONTAP 的 Throughput Capacity (MBps)，並視需要調整 MapConcurrency。
- 建議：在正式環境中先以 MapConcurrency=5 起步，一邊監控 FSx for ONTAP 的 CloudWatch 指標 (ThroughputUtilization) 一邊逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## 成本估算（每月概算）

> **備註**: 以 ap-northeast-1 區域為基準的概算。實際成本因使用量而異。

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次） | ~$8-20 |
| 標準配置 | ~$20-50 |

---

## Governance Note

> 本模式提供技術架構指引。它不構成法律、合規或法規方面的建議。租賃合約中包含的租戶資訊必須依據適用的個人資訊保護法妥善管理。物件影像中出現的個人資訊的處理還應留意不動產交易相關法規。

> **相關法規**: 宅地建物取引業法 (不動產仲介業法), 個人情報保護法 (個人資訊保護法)

---

## S3AP Compatibility

有關 S3 Access Points for FSx for ONTAP 的相容性限制、疑難排解與觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
