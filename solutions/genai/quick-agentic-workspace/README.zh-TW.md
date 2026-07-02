# 基於 FSx for ONTAP 的 Amazon Quick 代理工作區

🌐 **Language / 語言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

將 Amazon FSx for NetApp ONTAP **經 S3 Access Points** 作為 **Amazon Quick Suite**（代理式 AI 工作區）的資料基礎的模式。業務部門以 Windows 檔案操作維護的資料，可於 Quick 各功能（Index / Sight / Flows / Research）橫向運用。

與 UC29（受管 Bedrock KB 自助）不同，UC30 聚焦於**整合非結構化檢索、BI 與動作自動化的代理工作區**。

> Amazon Quick Suite 於 2025 年 10 月發布。功能·價格·區域皆為 time-sensitive，詳見 [aws.amazon.com/quick](https://aws.amazon.com/quick/)。

## Quick 功能與 S3 AP 對應

| Quick 功能 | 資料（S3 AP） | 實作 |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/`（非結構化） | S3 AP 唯讀資料來源 |
| Quick Sight (BI) | `analytics/<role>/`（csv） | Glue/Athena（Athena Query Lambda） |
| Quick Flows | `flows/<role>/`（json） | Action API（API Gateway + Lambda + Bedrock） |

## 兩個示範情境

| 情境 | 概要 |
|------|------|
| **A: 手動工作區** | 以 Windows 放置資料，在 Quick 主控台手動連接 Index、建立 Quick Sight 資料集、執行 Quick Flows |
| **B: 自動化** | 以無伺服器自動化資料準備、BI 查詢與動作（Data Prep / Athena Query / Action API） |

## 角色 × 服務結構

角色對齊 Amazon Quick 目標（sales、marketing、IT、operations、finance、legal + developers）。範例資料見 [`sample-data/quick-workspace/`](sample-data/)。與 UC29 共享角色結構。

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## 安全

- 無資料移動（FSx for ONTAP 正本保留，S3 AP 唯讀）
- Action API 使用 IAM 認證（SigV4）——不暴露未認證端點
- 最小權限、加密（SSE-FSX/SSE-S3/TLS）
- Quick 本體資料來源連接於 Quick 主控台設定

## 部署

使用 AWS SAM CLI 部署（請將佔位符替換為您的環境值）：

```bash
# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-quick-agentic-workspace \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。

> **Amazon Quick 設定**: 連接 Index、建立資料集、執行 Flows 不在本範本範圍內。部署後請在 Amazon Quick 主控台中設定（參見 [quick-console-setup](docs/quick-console-setup.md)）。

## Governance Note

> 本文為技術架構指導，不構成法律或合規建議。Quick 功能與價格可能變動，請以官方資訊為準。
