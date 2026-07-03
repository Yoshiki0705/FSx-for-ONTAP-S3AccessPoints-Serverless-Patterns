# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

一種以無侵入方式收集並分析由 **SIOS LifeKeeper** 建構的高可用性 (HA) 叢集日誌與容錯移轉事件的無伺服器模式，資料透過 **Amazon FSx for NetApp ONTAP** 的 S3 Access Points 採集。

藉由 Amazon Bedrock (Nova Pro) 提供的**根本原因分析 (Root Cause Analysis)** 與**叢集健康評分**，實現容錯移轉的快速原因定位與徵兆偵測。

---

## 設想情境

在企業環境中，SAP、Oracle 及核心業務應用由 SIOS LifeKeeper 進行 HA 保護，並使用 FSx for ONTAP Multi-AZ 作為共用儲存。

**課題**：
- 容錯移轉發生時的根本原因定位耗時較長
- LifeKeeper 日誌分析多為手動作業，依賴個人經驗
- 在 HA 叢集節點上新增監控代理程式會增加故障點
- 儲存層 (FSx for ONTAP) 與應用層 (LifeKeeper) 的故障區分困難

**解決方案**：
使用 FSx for ONTAP S3 Access Points，將 LifeKeeper 寫入的日誌以**無侵入方式**由無伺服器分析管線處理。透過 AI 自動分析降低維運負擔。

---

## SIOS LifeKeeper + FSx for ONTAP 組合

### 架構中的定位

| 層 | 職責 | HA 提供範圍 |
|---------|------|------------|
| 儲存 | FSx for ONTAP Multi-AZ | 資料可用性、AZ 備援、自動容錯移轉 |
| 應用 | SIOS LifeKeeper | VIP 控制、服務監控、自動復原 |
| 分析（本模式） | S3 AP + 無伺服器 + Bedrock | 無侵入式日誌分析、AI 根本原因分析 |

### 何謂 SIOS LifeKeeper

由 SIOS Technology 公司提供的、面向 Linux/Windows 的 HA 叢集軟體。在 AWS 上實現關鍵任務應用的高可用性。

**主要特性**：
- 應用感知型 Recovery Kit（直接監控 SAP S/4HANA、Oracle、NFS、IP 等）
- 跨 AZ 容錯移轉（單一區域內 2 個 AZ）
- VIP 管理（Elastic IP / Secondary IP）
- 透過通訊路徑備援防止腦裂
- 作為 AWS Partner Solution 正式提供

**實績**：Astro Malaysia 公司在 SAP + Oracle on AWS 環境中採用 SIOS LifeKeeper，實現了 99.99% 的可用性。

### FSx for ONTAP 共用磁碟支援 (V10 及以後)

自 LifeKeeper V10.0.1 起，可將 FSx for ONTAP 作為共用磁碟直接保護。過去僅支援 DataKeeper（區塊複寫），新增共用磁碟組態後可實現更簡單的 HA 架構。

| 通訊協定 | 所需的 Recovery Kit | 備註 |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | 在 AWS 上使用 FSx for ONTAP 時必需 |
| NFS | NAS Recovery Kit | 標準的 NFS 共用磁碟組態 |

> SIOS bcblog 的驗證文章 (2026-05-08) 確認，在 RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) 的組態下切換 (switchover) 可正常運作。

### FSx for ONTAP 帶來的價值

- **Multi-AZ 共用儲存**：可從 LifeKeeper 的兩個節點透過 NFS/iSCSI 存取
- **自動儲存容錯移轉**：自動處理儲存層的 AZ 故障
- **Snapshot**：保全容錯移轉前後的資料狀態
- **S3 Access Points**：用於日誌分析的無侵入式資料存取路徑
- **多通訊協定**：從單一磁碟區同時提供 SMB + NFS + iSCSI + S3 API，避免資料重複保存
- **雲端原生**：可從 AWS Management Console 直接開始使用（無需額外授權）

> 「並非將資料複製到 S3 後再使用，而是能夠透過 S3 API 直接運用 FSx for ONTAP 上的資料，這是一大優勢」 — 摘自 [SIOS bcblog 訪談文章](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### 公開參考資料

| 資料 | 發行方 | URL |
|------|--------|-----|
| 運用 SIOS LifeKeeper 與 Amazon FSx for NetApp ONTAP 的高可用性解決方案 | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| 基於 NetApp ONTAP 與 LifeKeeper 的高可用性設計 | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| 將 Amazon FSx for NetApp ONTAP 用作 LifeKeeper 的共用磁碟 | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## 功能

### Discovery Lambda
- 透過 FSx for ONTAP S3 AP 偵測 LifeKeeper 日誌檔案
- 分類為容錯移轉事件 / 健康檢查 / 組態變更 / Recovery Kit 日誌
- 自動評估重要度（CRITICAL / HIGH / MEDIUM / LOW）

### Processing Lambda
- 偵測 LifeKeeper 資源狀態轉移（ISP→OSF、ISS→ISP 等）
- 透過 Bedrock (Nova Pro) 進行根本原因分析
- 計算叢集健康評分（0-100 分）
- 區分儲存層與應用層的故障

### Report Lambda
- 產生 Markdown 健康報告
- 依重要度閾值傳送 SNS 容錯移轉警示
- 附帶 LifeKeeper 指令（`lcdstatus`、通訊路徑確認）的建議操作

---

## 部署

### 前提條件

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP 檔案系統 + S3 Access Point（DemoMode=true 時無需）
- 已啟用 Bedrock 模型存取（Amazon Nova Pro）

### 快速部署

```bash
# 以 DemoMode 部署 (無需 FSx for ONTAP)
# 前提: 需要 AWS SAM CLI。sam build 會自動封裝程式碼與共用層。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **注意**：`template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 若使用 `aws cloudformation deploy` 指令直接部署，請改用 `template-deploy.yaml`（需事先封裝 Lambda zip 檔案並上傳至 S3）。

### 生產部署

```bash
# 前提: 需要 AWS SAM CLI。sam build 會自動封裝程式碼與共用層。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### 參數

| 參數 | 預設值 | 說明 |
|-----------|-----------|------|
| S3AccessPointAlias | (必填) | FSx for ONTAP S3 AP 別名 |
| DemoMode | false | 啟用示範模式 |
| ScheduleExpression | rate(5 minutes) | 監控間隔 |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | amazon.nova-pro-v1:0 | 分析用 Bedrock 模型 |
| FailoverAlertSeverity | CRITICAL | SNS 警示最低重要度 |
| ClusterName | lifekeeper-cluster | LifeKeeper 叢集名稱 |
| OutputDestination | STANDARD_S3 | 報告輸出目標 |
| LogRetentionInDays | 90 | CloudWatch Logs 保留期限 |

---

## 測試

```bash
# 單元測試
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# DemoMode 下的端對端測試
# (事先在示範用 S3 儲存貯體中放置範例日誌)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## 健康評分

| 評分 | 等級 | 含義 | 建議操作 |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | 正常 | 查看定期報告 |
| 70-89 | WARNING | 注意 | 確認通訊路徑、儲存 I/O |
| 50-69 | DEGRADED | 劣化 | 用 LifeKeeper GUI/CLI 確認狀態，監控 FSx for ONTAP |
| 0-49 | CRITICAL | 危險 | 立即回應。用 `lcdstatus` + ONTAP 管理 CLI 確認狀態 |

---

## 目錄結構

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM 範本
├── samconfig.toml.example     # 部署設定範例
├── README.md                  # 本文件 (日語)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper 日誌偵測
│   ├── processing/
│   │   └── handler.py         # Bedrock 根本原因分析
│   └── report/
│       └── handler.py         # 報告產生、警示
├── statemachine/
│   └── workflow.asl.json      # Step Functions 定義
├── docs/
│   ├── architecture.md        # 架構詳情
│   └── demo-guide.md          # 示範指南 (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # 單元測試
```

---

## 相關模式

| 模式 | 關聯性 |
|---------|--------|
| `solutions/sap/erp-adjacent/` | 受 LifeKeeper 保護的 SAP 環境的 IDoc/批次處理 |
| `solutions/event-driven/fpolicy/` | 透過 FPolicy 事件驅動的即時日誌偵測 |
| `solutions/flexcache/anycast-dr/` | 多區域 DR 組態的參考 |

---

## Governance Note

本模式旨在為 HA 叢集的**維運監控提供輔助**，請注意以下幾點：

- AI 分析結果為維運判斷的**參考資訊**，不執行自動容錯移轉控制或復原操作
- LifeKeeper 的組態變更必須透過 LifeKeeper GUI/CLI 進行
- 容錯移轉判斷應委由 LifeKeeper 自身的健康檢查機制
- 本模式是以 **Human-in-the-loop** 為前提的設計

---

## Performance Considerations

- **監控間隔**：5 分鐘間隔下會產生最多 5 分鐘的偵測延遲。若需要即時性，可透過 `TriggerMode=HYBRID` 並用 FPolicy 事件驅動
- **日誌大小**：當日誌檔案數量龐大時，用 `MaxFilesPerExecution` 控制批次大小
- **Bedrock 成本**：在容錯移轉頻繁的環境中，需注意 Bedrock 呼叫成本。用 `FailoverAlertSeverity` 縮小分析對象
- **S3 AP 輸送量**：FSx for ONTAP S3 AP 共用整個檔案系統的頻寬。為避免大量日誌讀取影響業務 I/O，亦可考慮基於 Snapshot 的讀取

---

## License

MIT
