# FlexCache AnyCast / DR 模式

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

本模式提供设计指南、模拟演示和运维设计文档，用于实现 ONTAP FlexCache AnyCast 和 DR（灾难恢复）配置与 FSx for ONTAP × S3 Access Points × AWS Serverless 服务的结合。

## 解决的问题

| 问题 | FlexCache AnyCast / DR 解决方案 |
|------|-------------------------------|
| 地理分布团队的读取性能 | 从最近的 FlexCache 提供热数据 |
| EDA/媒体/HPC 云爆发 | 本地 Origin + 云端 FlexCache 减少 WAN 传输 |
| DR 期间的读取连续性 | Origin 故障时缓存读取继续 |
| WAN 传输量减少 | 仅缓存热数据，增量传输 |
| 客户端挂载配置复杂性 | 通过 AnyCast IP 实现单一挂载点 |

## 架构概述

```
Control Plane (AnyCast/VIP 控制):
  Health Check Lambda → Route Decision Lambda → Route 53 / DNS

Data Plane (S3 AP 无服务器处理):
  EventBridge Scheduler → Step Functions → Discovery → Processing → Report

Storage Layer:
  Origin Volume → FlexCache A (Region/AZ A) → S3 AP A
                → FlexCache B (Region/AZ B) → S3 AP B
```

## 关键设计决策

- **模拟模式**: 无需实际 FlexCache 基础设施即可运行演示/测试
- **健康检查**: 基于 Lambda 的 FlexCache 卷健康监控
- **路由决策**: 基于 DNS 路由到最近的健康 FlexCache
- **S3 AP 集成**: 无服务器处理从最近的 S3 AP 读取

## 成功指标

| 指标 | 目标 |
|------|------|
| 故障检测时间 | < 30 秒 |
| DNS 传播时间 | < 60 秒 |
| 故障转移期间读取连续性 | > 99.9% |
| 缓存命中率（热数据） | > 80% |
| WAN 传输减少率 | > 60% |

---

## 部署

使用 AWS SAM CLI 部署（请将占位参数替换为您的环境值）：

```bash
# パラメータファイルを編集
cp params/staging.json params/flexcache-anycast-demo.json
# 必要なパラメータを設定

# デプロイ
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name flexcache-anycast-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    SimulationMode=true \
    CacheEndpoints="cache-a.example.com,cache-b.example.com" \
    HealthCheckIntervalMinutes=5
```

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。

## Governance Note

> 本模式提供技术架构指导。不构成法律、合规或监管建议。组织应咨询合格的专业人员。
