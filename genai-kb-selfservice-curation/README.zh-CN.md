# 自助式知识库维护

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

让业务部门成员**仅通过熟悉的 Windows 资源管理器拖放操作**即可维护 Amazon Bedrock Knowledge Base 数据源的模式。

在 FSx for ONTAP 上创建**AI 专用卷/文件夹**，通过 SMB 向各角色·部门开放；同一数据通过 **S3 Access Points（只读路径）**连接到 Amazon Bedrock Knowledge Base 数据源，检测文件变更并**自动摄取（Ingestion）**。

由此从"IT 部门按请求手动 ETL/复制/摄取"的运维，转变为**现场自行维护知识的民主化运维**。

## Before / After

> **注**: 已对客户名、个人名、团队名进行脱敏的通用化运维故事。

- **Before**: 业务部门请求 → IT 从 EC2 Windows Server 手动复制 → 上传 S3 → 手动摄取到 Bedrock KB。每次请求成为瓶颈，数据重复管理，属人化。
- **After**:"把要给 AI 用的数据放到这个 Windows 文件夹并自行维护。"用户照常拖放，经 S3 AP 自动同步到 KB，立即可检索。

## 两个演示场景

在同一基础上，可按运维成熟度体验两个阶段。详见 [演示指南](docs/demo-guide.md)。

| 场景 | 概要 | 摄取触发 |
|------|------|---------|
| **A: 手动维护体验** | 用 Windows 文件操作（添加/更新/删除）维护 AI 数据，摄取由人手动触发（控制台"同步"/CLI） | 手动 |
| **B: 自动化** | 将 A 的手动同步用 Lambda + Step Functions + EventBridge 自动化（检测→摄取→等待完成→通知） | 自动 |

> 业务用户的操作（拖放）在两种场景下相同。不同之处仅在于摄取之后由人完成还是由无服务器完成。

## 解决的问题

| 问题 | 解决方案 |
|------|--------|
| 知识更新等待 IT 手动操作 | 现场用 Windows 操作维护，自动摄取 |
| 复制到 S3 导致数据重复管理 | 通过 S3 AP 直接将 FSx ONTAP 正本作为数据源 |
| 漏摄取·漏更新 | 检测文件变更后自动 Ingestion |
| 需要 ETL/S3/Bedrock 专业技能 | 仅需 Windows 拖放 |
| 数据所有权不明确 | 按角色·部门划分文件夹结构 |

## 托管 KB vs 自定义 RAG

本 UC 采用**托管 Bedrock Knowledge Bases（Pattern C）**以最小化运维负担。若需在检索时进行文件级权限过滤，请选择自定义 RAG（[FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/)，Pattern A）。

> **部署前提**: 使用 [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) 或 Bedrock 控制台创建 Knowledge Base 与数据源，并将其 ID 传入模板参数。

## 安全

- 无数据移动（FSx ONTAP 正本保留，S3 AP 仅只读）
- 写入仅经 SMB/NFS，AI 摄取路径（S3 AP）为读取
- 按文件夹的 NTFS ACL 分离各部门写权限
- S3 AP 数据源边界为卷/前缀级别（按用户的可见范围控制不在范围内）

## Governance Note

> 本模式提供技术架构指导，不构成法律或合规建议。请咨询合格的专业人士。
