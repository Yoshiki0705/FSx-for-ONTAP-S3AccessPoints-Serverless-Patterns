# Dynamic FlexCache 渲染 / EDA 工作流

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

在提交渲染/EDA/仿真作业时，通过 REST API 动态创建 ONTAP FlexCache 卷，并在作业完成后自动删除的工作流。使用 AWS Step Functions 实现 NVIDIA 风格的按作业缓存管理模式。

## 为什么按作业创建 FlexCache

| 原因 | 说明 |
|------|------|
| 成本优化 | 仅在作业执行期间产生存储费用 |
| 数据隔离 | 按项目/作业隔离缓存 |
| 安全性 | 作业完成后无数据残留 |
| 运维简化 | 防止孤立卷积累 |
| 性能优化 | 仅 Prepopulate 作业所需数据 |

## 架构

```
Job Request → Validate → Create FlexCache → Wait Ready → Prepopulate
    → Submit Job → Monitor Loop → Cleanup FlexCache → Report → Notify
```

## ONTAP REST API 操作

- FlexCache 创建: `POST /api/storage/flexcache/flexcaches`
- FlexCache 删除: `DELETE /api/storage/flexcache/flexcaches/{uuid}`
- 作业监控: `GET /api/cluster/jobs/{uuid}`
- Prepopulate: `PATCH /api/storage/flexcache/flexcaches/{uuid}`

## 成功指标

| 指标 | 目标 |
|------|------|
| FlexCache 创建时间 | < 2 分钟 |
| FlexCache 删除时间 | < 1 分钟 |
| 作业完成率 | > 95% |
| 孤立卷数量 | 0 |
| 每作业成本（FlexCache 开销） | < $0.50 |

---

## 部署

使用 AWS SAM CLI 部署（请将占位参数替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name dynamic-flexcache-workflow-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    OntapManagementIp=10.0.0.1 \
    OntapSecretName=fsxn/ontap-credentials \
    OriginSvmName=svm1 \
    OriginVolumeName=render_assets \
    CacheSvmName=svm1 \
    SimulationMode=true
```

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。

## Governance Note

> 本模式提供技术架构指导。不构成法律、合规或监管建议。组织应咨询合格的专业人员。
