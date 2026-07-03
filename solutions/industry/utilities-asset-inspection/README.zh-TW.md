# UC25: 電力與公用事業 — 無人機影像巡檢 / SCADA 異常偵測

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構](docs/architecture.zh-TW.md) | [示範指南](docs/demo-guide.zh-TW.md)

## 概觀

一個運用 FSx for ONTAP S3 Access Points 的無伺服器工作流程，從輸電設施的無人機巡檢影像中偵測設備缺陷、對 SCADA 記錄進行時間序列異常偵測，並分析 FLIR 熱影像的熱點。

## Success Metrics

### Outcome
透過自動化文件處理與分析，實現營運效率提升與合規強化。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 缺陷偵測率 | ≥ 85% |
| SCADA 異常誤報率 | < 10% |
| 熱影像熱點偵測精度 | ≥ 90% |
| 報告產生時間 | < 5 分鐘 / 批次 |
| 成本 / 每日執行 | < $3.00 |
| Human Review 必要率 | > 30%（偵測到 Critical 嚴重程度時全部確認） |

### Measurement Method
Step Functions 執行歷史、AI/ML 服務擷取結果、CloudWatch EMF Metrics（ProcessingDuration, SuccessCount, ErrorCount）。

### Human Review Requirements
- 低信賴度結果需要人工確認
- Critical 警示由領域專家審查
- 定期彙總報告由管理層審查

## 架構

詳細的資料流程圖請參閱[架構文件](docs/architecture.zh-TW.md)。

## 先決條件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 內部。若 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（因為不會路由至 FSx 資料平面）。請使用 NetworkOrigin=VPC 的 S3 AP，或設定透過 NAT Gateway 的存取。詳情請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 帳戶與適當的 IAM 權限
- FSx for ONTAP 檔案系統（ONTAP 9.17.1P4D3 或更新版本）
- 已啟用 S3 Access Point 的磁碟區
- VPC、私有子網路
- 已啟用 Amazon Bedrock 模型存取（Claude / Nova）

## 部署步驟

```bash
# 前提: 需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
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
> 若要使用 `aws cloudformation deploy` 命令直接部署，請改用 `template-deploy.yaml`（需要事先封裝 Lambda zip 檔案並上傳至 S3）。

## ⚠️ 效能注意事項

- FSx for ONTAP 的傳輸量容量在 **NFS/SMB/S3 AP 之間共用**。以 MapConcurrency=10 進行平行處理時，可能會影響同一磁碟區上的其他工作負載。
- 進行大量檔案的批次處理時，請確認 FSx for ONTAP 的 Throughput Capacity (MBps)，並視需要調整 MapConcurrency。
- 建議: 在生產環境中先以 MapConcurrency=5 開始，同時監控 FSx for ONTAP 的 CloudWatch 指標 (ThroughputUtilization)，並逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## 成本估算（每月概算）

> **備註**: ap-northeast-1 區域的概算。實際成本因使用量而異。

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每日 1 次） | ~$8-20 |
| 標準組態 | ~$20-50 |

---

## Governance Note

> 本模式提供技術架構指引。不構成法律、合規或法規方面的建議。SCADA 資料屬於關鍵基礎設施資訊。存取權限管理與稽核記錄保留必須遵循適用的電力事業法規及關鍵基礎設施保護指引。

> **相關法規**: 電氣事業法（電気事業法）, 電氣設備技術標準（電気設備技術基準）

---

## S3AP Compatibility

關於 FSx for ONTAP S3 Access Points 的相容性限制、疑難排解與觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
