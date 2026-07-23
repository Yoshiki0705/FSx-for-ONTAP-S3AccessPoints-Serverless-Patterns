# SnapMirror Cross-Region DR + S3 Access Points 模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

一種災難復原模式，透過 SnapMirror Asynchronous 將經 S3 Access Points 收集的資料複寫到跨區域目標，並在目標卷上自動掛載新的 S3 AP 實現自動故障轉移。

正常營運期間，資料透過來源卷上的 S3 AP 進行擷取。當 DR 事件發生時，Lambda 函數在約 3 分鐘內協調故障轉移：SnapMirror break → junction path → S3 AP 建立。

## 架構

```mermaid
graph TB
    subgraph "正常營運 (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>來源]
        SRC_VOL[來源卷<br/>vol_sm_dr_source]
    end
    subgraph "複寫"
        SM[SnapMirror Async<br/>排程: 5分鐘間隔]
    end
    subgraph "DR 故障轉移 (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>目標<br/>(故障轉移時建立)]
        DST_VOL[目標卷 (DP)<br/>vol_sm_dr_dest]
        SNS[SNS 通知]
        CLIENT[應用程式<br/>(切換到新 S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|增量<br/>複寫| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## 關鍵元件

| 元件 | 說明 |
|------|------|
| 來源卷 + S3 AP | 資料擷取點 (Region A)。正常營運時使用 |
| SnapMirror Async | 卷級增量複寫 (RPO = 排程間隔) |
| 目標卷 (DP) | 資料保護卷（break 前為唯讀）。透過 FSx API 建立 (SM-VAL-009) |
| Failover Lambda | 自動化: break → junction → S3 AP 建立。RTO ~3分鐘 |
| SNS Topic | 故障轉移後向應用程式通知新 S3 AP 端點 |

## RTO / RPO

| 指標 | 值 | 備註 |
|------|:---:|------|
| **RTO** | ~3分鐘 | SnapMirror break（即時）+ junction 傳播（~2分鐘）+ S3 AP 建立（~30秒） |
| **RPO** | ≤ SnapMirror 排程 | 預設 5 分鐘排程。最後一次傳輸後的資料可能遺失 |

## 前提條件

- 位於不同區域的 2 個 FSx for ONTAP 叢集
- VPC Peering 及 Cluster/SVM Peering 已建立
- 透過 `aws fsx create-volume` 建立 DP 目標卷（僅 ONTAP REST API 不可 — SM-VAL-009）
- SnapMirror 關係已初始化且處於 `snapmirrored` 狀態
- Secrets Manager 中的 fsxadmin 憑證（兩個區域）
- Lambda 可透過 VPC 存取目標 ONTAP 管理 IP（連接埠 443）

## 部署

```bash
# 1. 部署堆疊（建立來源卷、目標 DP 卷、Failover Lambda、SNS）
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. 建立來源 S3 AP + SnapMirror 關係
#    （參見堆疊輸出中的 PostDeployInstructions）

# 3. 測試故障轉移（試運行）
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## 執行故障轉移

```bash
# 觸發 DR 故障轉移
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# 檢查結果
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## 驗證

```bash
# 故障轉移後，從目標 S3 AP 讀取
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## 技術限制

| 限制 | 詳情 |
|------|------|
| 僅 SnapMirror Asynchronous | S3 NAS bucket 卷不支援 Synchronous 模式 |
| 不支援 SVM-DR | 包含 S3 NAS bucket 的 SVM 會阻止 SVM-DR。僅支援卷級 SnapMirror |
| 透過 FSx API 建立 DP 卷 | SM-VAL-009: 僅透過 ONTAP REST API 建立的卷對 FSx API 不可見，阻止 S3 AP |
| S3 AP 不隨複寫傳輸 | SM-002: S3 AP 是 AWS 層資源。目標需建立新 AP |
| 用戶端應用程式更新 | 新 AP 具有不同的 ARN/alias。應用程式必須切換端點 |
| SnapMirror 排程 | FSx for ONTAP 最小間隔: 5分鐘 |

## 清理（順序關鍵 — SM-VAL-011）

```bash
# ⚠️ 嚴格按照順序執行以防止孤立資源

# 1. 刪除 SnapMirror 關係（從目標叢集）
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    然後從來源: snapmirror release (ONTAP CLI)

# 2. 刪除 SVM Peers（兩個叢集）— 輪詢兩側直到 num_records: 0

# 3. 刪除 Cluster Peers（兩個叢集）

# 4. 刪除 VPC Peering（僅在步驟 2 確認後）

# 5. 分離/刪除 S3 Access Points（來源和目標，如已建立）
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. 刪除 CloudFormation 堆疊
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## 參考資料

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
