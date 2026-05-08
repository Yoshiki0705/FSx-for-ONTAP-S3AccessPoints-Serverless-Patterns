# 现有环境影响评估指南

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## 概述

本文档评估启用各 Phase 功能时对现有环境的影响，并提供安全的启用步骤和回滚方法。

> **范围**: Phase 1–5（后续 Phase 添加时更新本文档）

设计原则：
- **Phase 1 (UC1–UC5)**: 独立 CloudFormation 堆栈。仅在 VPC/子网中创建 ENI
- **Phase 2 (UC6–UC14)**: 独立堆栈 + 跨区域 API 调用
- **Phase 3 (横向功能增强)**: 现有 UC 扩展。所有功能选择性控制（默认禁用）
- **Phase 4 (生产 SageMaker·多账户·事件驱动)**: UC9 扩展 + 新模板。选择性控制
- **Phase 5 (Serverless Inference·成本优化·CI/CD·Multi-Region)**: 所有功能选择性控制（默认禁用）

---

## Phase 1: 基础 UC (UC1–UC5)

| 参数 | 默认值 | 启用时的影响 |
|------|--------|------------|
| VpcId / PrivateSubnetIds | —（必填） | 创建 Lambda ENI |
| EnableS3GatewayEndpoint | "true" | ⚠️ 与现有 S3 Gateway EP 冲突 |
| EnableVpcEndpoints | "false" | 创建 Interface VPC Endpoints |
| ScheduleExpression | "rate(1 hour)" | 定期执行 Step Functions |

## Phase 2: 扩展 UC (UC6–UC14)

| 参数 | 默认值 | 启用时的影响 |
|------|--------|------------|
| CrossRegion | "us-east-1" | 跨区域 API 调用（延迟 50–200ms） |
| MapConcurrency | 10 | 影响 Lambda 并发配额 |

## Phase 3: 横向功能增强

| 参数 | 默认值 | 启用时的影响 |
|------|--------|------------|
| EnableStreamingMode | "false" | UC11 新资源（现有轮询无影响） |
| EnableSageMakerTransform | "false" | ⚠️ UC9 工作流添加 SageMaker 路径 |
| EnableXRayTracing | "true" | ⚠️ 开始 X-Ray 追踪传输 |

## Phase 4: 生产扩展

| 参数 | 默认值 | 启用时的影响 |
|------|--------|------------|
| EnableDynamoDBTokenStore | "false" | 新 DynamoDB 表 |
| EnableRealtimeEndpoint | "false" | ⚠️ 持续运行成本（~$166/月） |
| EnableABTesting | "false" | Multi-Variant Endpoint |

## Phase 5: Serverless Inference·成本优化·CI/CD·Multi-Region

| 参数 | 默认值 | 启用时的影响 |
|------|--------|------------|
| InferenceType | "none" | "serverless" 修改路由 |
| EnableScheduledScaling | "false" | ⚠️ 更改现有 Endpoint 扩缩容 |
| EnableAutoStop | "false" | ⚠️ 自动停止空闲 Endpoint |
| EnableBillingAlarms | "false" | 新告警（现有无影响） |
| EnableMultiRegion | "false" | ⚠️ **不可逆** — DynamoDB Global Table |

---

## 安全启用顺序

| 顺序 | 功能 | Phase | 风险 |
|------|------|-------|------|
| 1 | UC1 部署（最小配置） | 1 | 低 |
| 2 | 可观测性 (X-Ray + EMF) | 3 | 低 |
| 3 | CI/CD 管道 | 5 | 无 |
| 4 | Kinesis 流处理 (UC11) | 3 | 低 |
| 5 | Serverless Inference | 5 | 低 |
| 6 | Real-time Endpoint | 4 | 中 ⚠️ |
| 7 | Scheduled Scaling / Auto-Stop | 5 | 中 ⚠️ |
| 8 | Multi-Account | 4 | 中 ⚠️ |
| 9 | Multi-Region | 5 | 高 ⚠️ **不可逆** |

---

## 成本影响摘要

| Phase | 功能 | 默认状态 | 额外成本 |
|-------|------|---------|---------|
| 1/2 | VPC Endpoints | 禁用 | ~$29/月 |
| 3 | Kinesis | 禁用 | ~$11/分片/月 |
| 3 | X-Ray | 启用 | ~$5/百万追踪 |
| 4 | Real-time Endpoint | 禁用 | ⚠️ ~$166/月 |
| 5 | Serverless Inference | 禁用 | 按量计费 |
| 5 | Multi-Region | 禁用 | Global Table 额外成本 |

---

## 相关文档

- [成本结构分析](cost-analysis.md) | [流处理 vs 轮询指南](streaming-vs-polling-guide-zh-CN.md)
- [推理成本比较](inference-cost-comparison.md) | [成本优化指南](cost-optimization-guide.md)
- [CI/CD 指南](ci-cd-guide.md) | [Multi-Region DR](multi-region/disaster-recovery.md)

---

*本文档是 FSxN S3AP Serverless Patterns 的现有环境影响评估指南。*
