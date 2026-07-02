# UC20: 旅行與飯店業 — 預約文件處理 / 設施檢查影像分析

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構圖](docs/architecture.zh-TW.md) | [示範指南](docs/demo-guide.zh-TW.md)

## 概述

利用 FSx for ONTAP S3 Access Points，自動從飯店/旅館的預約文件（PDF、掃描影像）中擷取結構化資料，並對設施檢查影像進行狀態分析和維護建議自動生成的無伺服器工作流程。

### 主要功能

- 透過 S3 AP 自動偵測預約文件和設施檢查影像
- Textract + Comprehend 結構化資料擷取（住客姓名、日期、房型、金額）
- 多語言支援（語言偵測 → Textract 提示 + Comprehend 模型自動選擇）
- Rekognition 設施狀態分析（損壞偵測、清潔度評分 0–100）
- Bedrock 維護建議生成

## Success Metrics

| 指標 | 目標值 |
|------|--------|
| 預約資料擷取準確率 | ≥ 90% |
| 設施狀態偵測率 | ≥ 85% |
| 多語言支援覆蓋率 | ≥ 5 種語言 |
| 報告生成時間 | < 5 分鐘/批次 |
| 人工審核率 | > 15% |

## 治理說明

> 本模式提供技術架構指導，不構成法律、合規或監管建議。

## 部署

使用 AWS SAM CLI 部署（請將佔位參數替換為您的環境值）：

```bash
# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-travel-processing \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。

## ⚠️ 效能注意事項

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之間共享**。使用 MapConcurrency=10 進行並行處理時可能影響同一卷上的其他工作負載。
- 進行大規模批量處理時，請檢查 FSx for ONTAP 的 Throughput Capacity (MBps) 並相應調整 MapConcurrency。
- 建議：在生產環境中從 MapConcurrency=5 開始，監控 CloudWatch 指標 (ThroughputUtilization)，然後逐步增加。

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 內。如果 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（請求不會路由到 FSx 資料平面）。請使用 VPC-origin S3 AP 或設定 NAT Gateway 存取。詳見 [S3AP 相容性說明](../docs/s3ap-compatibility-notes.md)。

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
