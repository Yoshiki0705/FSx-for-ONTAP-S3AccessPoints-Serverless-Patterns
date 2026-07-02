# 基于 FSx for ONTAP 的 Amazon Quick 智能体工作区

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

将 Amazon FSx for NetApp ONTAP **经 S3 Access Points** 作为 **Amazon Quick Suite**（智能体式 AI 工作区）的数据基础的模式。业务部门通过 Windows 文件操作维护的数据，可在 Quick 各功能（Index / Sight / Flows / Research）中横向使用。

与 UC29（托管 Bedrock KB 自助）不同，UC30 聚焦于**统一非结构化检索、BI 与动作自动化的智能体工作区**。

> Amazon Quick Suite 于 2025 年 10 月发布。功能·价格·区域均为 time-sensitive，详见 [aws.amazon.com/quick](https://aws.amazon.com/quick/)。

## Quick 功能与 S3 AP 映射

| Quick 功能 | 数据（S3 AP） | 实现 |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/`（非结构化） | S3 AP 只读数据源 |
| Quick Sight (BI) | `analytics/<role>/`（csv） | Glue/Athena（Athena Query Lambda） |
| Quick Flows | `flows/<role>/`（json） | Action API（API Gateway + Lambda + Bedrock） |

## 两个演示场景

| 场景 | 概要 |
|------|------|
| **A: 手动工作区** | 用 Windows 放置数据，在 Quick 控制台手动连接 Index、构建 Quick Sight 数据集、运行 Quick Flows |
| **B: 自动化** | 用无服务器自动化数据准备、BI 查询与动作（Data Prep / Athena Query / Action API） |

## 角色 × 服务结构

角色对齐 Amazon Quick 目标（sales、marketing、IT、operations、finance、legal + developers）。示例数据见 [`sample-data/quick-workspace/`](sample-data/)。与 UC29 共享角色结构。

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## 安全

- 无数据移动（FSx for ONTAP 正本保留，S3 AP 只读）
- Action API 使用 IAM 认证（SigV4）——不暴露未认证端点
- 最小权限、加密（SSE-FSX/SSE-S3/TLS）
- Quick 本体数据源连接在 Quick 控制台配置

## 部署

使用 AWS SAM CLI 部署（请将占位符替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
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

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。

> **Amazon Quick 设置**: 连接 Index、创建数据集、运行 Flows 不在本模板范围内。部署后请在 Amazon Quick 控制台中配置（参见 [quick-console-setup](docs/quick-console-setup.md)）。

## Governance Note

> 本文为技术架构指导，不构成法律或合规建议。Quick 功能与价格可能变化，请以官方信息为准。
