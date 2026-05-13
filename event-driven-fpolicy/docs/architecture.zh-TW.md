🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | 繁體中文 | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

# 事件驅動 FPolicy — 架構

## 端到端架構

```mermaid
flowchart TB
    subgraph CLIENT["📁 NFS/SMB 用戶端"]
        NFS["檔案操作<br/>create / write / delete / rename"]
    end

    subgraph ONTAP["🗄️ FSx for NetApp ONTAP"]
        FPOLICY["FPolicy Engine<br/>非同步模式"]
    end

    subgraph FARGATE["🐳 ECS Fargate"]
        SERVER["FPolicy Server<br/>TCP :9898<br/>• XML 解析<br/>• 路徑正規化<br/>• JSON 轉換"]
    end

    subgraph PIPELINE["⚡ 事件管線"]
        SQS["SQS Queue<br/>Ingestion + DLQ"]
        BRIDGE["Bridge Lambda<br/>SQS → EventBridge<br/>批次處理 (10筆/次)"]
        EB["EventBridge<br/>自訂匯流排<br/>fsxn-fpolicy-events"]
    end

    subgraph TARGETS["🎯 UC 目標"]
        UC1["UC: 合規稽核"]
        UC2["UC: 安全監控"]
        UC3["UC: 資料管線"]
    end

    NFS -->|"檔案操作"| FPOLICY
    FPOLICY -->|"TCP 通知<br/>(非同步)"| SERVER
    SERVER -->|"SendMessage"| SQS
    SQS -->|"Event Source Mapping"| BRIDGE
    BRIDGE -->|"PutEvents"| EB
    EB -->|"規則 1"| UC1
    EB -->|"規則 2"| UC2
    EB -->|"規則 3"| UC3
```

## 元件詳情

### 1. FPolicy Server (ECS Fargate)

| 項目 | 詳情 |
|------|------|
| 執行環境 | ECS Fargate (ARM64, 0.25 vCPU / 512 MB) |
| 協定 | TCP :9898 (ONTAP FPolicy 二進位框架) |
| 工作模式 | 非同步 — NOTI_REQ 無需回應 |
| 主要處理 | XML 解析 → 路徑正規化 → JSON 轉換 → SQS 傳送 |

### 2. IP Updater Lambda

| 項目 | 詳情 |
|------|------|
| 觸發器 | EventBridge Rule (ECS Task State Change → RUNNING) |
| 處理 | 1. 停用 Policy → 2. 更新 Engine IP → 3. 重新啟用 Policy |
| 認證 | 從 Secrets Manager 取得 ONTAP 憑證 |

## 安全考量

- FPolicy Server 部署在 Private Subnet（無公網存取）
- AWS 服務存取透過 VPC Endpoints（不經過網際網路）
- Security Group 僅允許來自 VPC CIDR (10.0.0.0/8) 的 TCP 9898
- ONTAP 管理員憑證透過 Secrets Manager 管理
