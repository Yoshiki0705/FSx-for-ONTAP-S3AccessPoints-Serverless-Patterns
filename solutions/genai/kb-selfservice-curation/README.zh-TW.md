# 自助式知識庫維運

🌐 **Language / 語言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

讓業務部門成員**僅透過熟悉的 Windows 檔案總管拖放操作**即可維護 Amazon Bedrock Knowledge Base 資料來源的模式。

在 FSx for ONTAP 上建立**AI 專用磁碟區/資料夾**，透過 SMB 向各角色·部門開放；同一資料透過 **S3 Access Points（唯讀路徑）**連接到 Amazon Bedrock Knowledge Base 資料來源，偵測檔案變更並**自動擷取（Ingestion）**。

藉此從「IT 部門依請求手動 ETL/複製/擷取」的維運，轉變為**現場自行維護知識的民主化維運**。

## Before / After

> **註**: 已對客戶名、個人名、團隊名進行遮罩的通用化維運故事。

- **Before**: 業務部門請求 → IT 從 EC2 Windows Server 手動複製 → 上傳 S3 → 手動擷取至 Bedrock KB。每次請求形成瓶頸，資料重複管理，屬人化。
- **After**:「把要給 AI 用的資料放到這個 Windows 資料夾並自行維護。」使用者照常拖放，經 S3 AP 自動同步到 KB，立即可檢索。

## 兩個示範情境

在同一基礎上，可依維運成熟度體驗兩個階段。詳見 [示範指南](docs/demo-guide.md)。

| 情境 | 概要 | 擷取觸發 |
|------|------|---------|
| **A: 手動維運體驗** | 以 Windows 檔案操作（新增/更新/刪除）維護 AI 資料，擷取由人手動觸發（主控台「同步」/CLI） | 手動 |
| **B: 自動化** | 將 A 的手動同步以 Lambda + Step Functions + EventBridge 自動化（偵測→擷取→等待完成→通知） | 自動 |

> 業務使用者的操作（拖放）在兩種情境下相同。不同之處僅在於擷取之後由人完成或由無伺服器完成。

## 解決的問題

| 問題 | 解決方案 |
|------|--------|
| 知識更新等待 IT 手動操作 | 現場以 Windows 操作維護，自動擷取 |
| 複製到 S3 造成資料重複管理 | 透過 S3 AP 直接將 FSx for ONTAP 正本作為資料來源 |
| 漏擷取·漏更新 | 偵測檔案變更後自動 Ingestion |
| 需要 ETL/S3/Bedrock 專業技能 | 僅需 Windows 拖放 |
| 資料所有權不明確 | 依角色·部門劃分資料夾結構 |

## 受管 KB vs 自訂 RAG

本 UC 採用**受管 Bedrock Knowledge Bases（Pattern C）**以最小化維運負擔。若需在檢索時進行檔案層級權限過濾，請選擇自訂 RAG（[FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/)，Pattern A）。

> **部署前提**: 使用 [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) 或 Bedrock 主控台建立 Knowledge Base 與資料來源，並將其 ID 傳入範本參數。

## 安全

- 無資料移動（FSx for ONTAP 正本保留，S3 AP 僅唯讀）
- 寫入僅經 SMB/NFS，AI 擷取路徑（S3 AP）為讀取
- 依資料夾的 NTFS ACL 分離各部門寫入權限
- S3 AP 資料來源邊界為磁碟區/前綴層級（依使用者的可見範圍控制不在範圍內）

## 部署

使用 AWS SAM CLI 部署（請將佔位符替換為您的環境值）：

> **部署前提**: 本範本假設已存在 Amazon Bedrock Knowledge Base 及資料來源（連接到 S3 AP）。由於 OpenSearch Serverless 向量索引建立並非 CloudFormation 原生支援，請先建立 Knowledge Base，並將其 `KnowledgeBaseId` / `DataSourceId` 作為參數傳入（使用儲存庫根目錄的 `scripts/create_bedrock_kb.py` 或 Bedrock 主控台）。

```bash
# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-kb-selfservice-curation \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    KnowledgeBaseId=<your-kb-id> \
    DataSourceId=<your-datasource-id> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。

## Governance Note

> 本模式提供技術架構指導，不構成法律或合規建議。請諮詢合格的專業人士。
