# 現有環境影響評估指南

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## 概述

本文件評估啟用各 Phase 功能時對現有環境的影響，並提供安全的啟用步驟和回復方法。

> **範圍**: Phase 1–5（後續 Phase 新增時更新本文件）

設計原則：
- **Phase 1 (UC1–UC5)**: 獨立 CloudFormation 堆疊。僅在 VPC/子網中建立 ENI
- **Phase 2 (UC6–UC14)**: 獨立堆疊 + 跨區域 API 呼叫
- **Phase 3 (橫向功能增強)**: 現有 UC 擴展。所有功能選擇性控制（預設停用）
- **Phase 4 (生產 SageMaker·多帳戶·事件驅動)**: UC9 擴展 + 新範本。選擇性控制
- **Phase 5 (Serverless Inference·成本最佳化·CI/CD·Multi-Region)**: 所有功能選擇性控制（預設停用）

---

## Phase 1–2: 基礎與擴展 UC

| 參數 | 預設值 | 啟用時的影響 |
|------|--------|------------|
| EnableS3GatewayEndpoint | "true" | ⚠️ 與現有 S3 Gateway EP 衝突 |
| EnableVpcEndpoints | "false" | 建立 Interface VPC Endpoints |
| CrossRegion | "us-east-1" | 跨區域 API 呼叫（延遲 50–200ms） |
| MapConcurrency | 10 | 影響 Lambda 並行配額 |

## Phase 3: 橫向功能增強

| 參數 | 預設值 | 啟用時的影響 |
|------|--------|------------|
| EnableStreamingMode | "false" | UC11 新資源（現有輪詢無影響） |
| EnableSageMakerTransform | "false" | ⚠️ UC9 工作流程新增 SageMaker 路徑 |
| EnableXRayTracing | "true" | ⚠️ 開始 X-Ray 追蹤傳輸 |

## Phase 4: 生產擴展

| 參數 | 預設值 | 啟用時的影響 |
|------|--------|------------|
| EnableRealtimeEndpoint | "false" | ⚠️ 持續運行成本（~$166/月） |
| EnableDynamoDBTokenStore | "false" | 新 DynamoDB 資料表 |

## Phase 5: Serverless Inference·成本最佳化·CI/CD·Multi-Region

| 參數 | 預設值 | 啟用時的影響 |
|------|--------|------------|
| InferenceType | "none" | "serverless" 修改路由 |
| EnableScheduledScaling | "false" | ⚠️ 變更現有 Endpoint 擴縮容 |
| EnableAutoStop | "false" | ⚠️ 自動停止閒置 Endpoint |
| EnableMultiRegion | "false" | ⚠️ **不可逆** — DynamoDB Global Table |

---

## 安全啟用順序

| 順序 | 功能 | Phase | 風險 |
|------|------|-------|------|
| 1 | UC1 部署 | 1 | 低 |
| 2 | 可觀測性 | 3 | 低 |
| 3 | CI/CD | 5 | 無 |
| 4–6 | Streaming / SageMaker / Serverless | 3–5 | 低 |
| 7–8 | Real-time / Scaling | 4–5 | 中 ⚠️ |
| 9 | Multi-Region | 5 | 高 ⚠️ **不可逆** |

---

*本文件是 FSxN S3AP Serverless Patterns 的現有環境影響評估指南。*
