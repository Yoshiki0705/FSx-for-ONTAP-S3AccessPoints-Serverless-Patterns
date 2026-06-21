# UC27: 人力資源 — 履歷篩選 / PII嚴格模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構圖](docs/architecture.zh-TW.md) | [演示指南](docs/demo-guide.zh-TW.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to extract structured skills and experience from resumes, with PII strict mode that excludes protected characteristics from scoring.

## Success Metrics

| Metric | Target |
|--------|--------|
| Resume data extraction rate | ≥ 90% |
| Scoring fairness | No protected characteristic bias (age/gender/nationality excluded) |
| PII compliance | 100% (zero PII in logs) |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.00 |
| Human review required rate | > 30% (all scoring results reviewed by HR team) |

## Architecture

See [Architecture Document](docs/architecture.zh-TW.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled
- Amazon Textract — Cross-Region (us-east-1)

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 內。如果 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（請求不會路由到 FSx 資料平面）。請使用 VPC-origin S3 AP 或設定 NAT Gateway 存取。詳見 [S3AP 相容性說明](../docs/s3ap-compatibility-notes.md)。

## Deployment

```bash
aws cloudformation deploy \
  --template-file hr-document-screening/template.yaml \
  --stack-name fsxn-hr-screening \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```


## ⚠️ 效能注意事項

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之間共享**。使用 MapConcurrency=10 進行並行處理時可能影響同一卷上的其他工作負載。
- 進行大規模批量處理時，請檢查 FSx for ONTAP 的 Throughput Capacity (MBps) 並相應調整 MapConcurrency。
- 建議：在生產環境中從 MapConcurrency=5 開始，監控 CloudWatch 指標 (ThroughputUtilization)，然後逐步增加。

## Cleanup

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. AI usage in recruitment screening must comply with employment laws and equal opportunity regulations, excluding bias based on protected characteristics (age, gender, nationality). AI scoring is advisory only; final decisions must be made by HR professionals.

> **Related Regulations**: 職業安定法 (Employment Security Act), 個人情報保護法 (APPI), 労働基準法 (Labor Standards Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
