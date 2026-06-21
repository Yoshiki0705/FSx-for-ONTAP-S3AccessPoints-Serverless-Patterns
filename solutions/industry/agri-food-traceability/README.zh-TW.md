# UC21: 農業與食品 — 農田航拍影像分析 / 溯源文件管理

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文件**: [架構圖](docs/architecture.zh-TW.md) | [示範指南](docs/demo-guide.zh-TW.md)

## 概述

利用 FSx for ONTAP S3 Access Points，分析農田無人機/航拍影像以監測作物健康狀況，並自動化溯源文件的結構化資料擷取和批次分類的無伺服器工作流程。

## Success Metrics

| 指標 | 目標值 |
|------|--------|
| 作物異常偵測準確率 | ≥ 70% |
| 溯源分類率 | ≥ 80% |
| 地理位置驗證率 | ≥ 90% |

## 治理說明

> 本模式提供技術架構指導，不構成法律、合規或監管建議。

## ⚠️ 效能注意事項

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之間共享**。使用 MapConcurrency=10 進行並行處理時可能影響同一卷上的其他工作負載。
- 進行大規模批量處理時，請檢查 FSx for ONTAP 的 Throughput Capacity (MBps) 並相應調整 MapConcurrency。
- 建議：在生產環境中從 MapConcurrency=5 開始，監控 CloudWatch 指標 (ThroughputUtilization)，然後逐步增加。

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 內。如果 S3 Access Point 的 NetworkOrigin 為 `Internet`，則無法透過 S3 Gateway VPC Endpoint 存取（請求不會路由到 FSx 資料平面）。請使用 VPC-origin S3 AP 或設定 NAT Gateway 存取。詳見 [S3AP 相容性說明](../docs/s3ap-compatibility-notes.md)。

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
