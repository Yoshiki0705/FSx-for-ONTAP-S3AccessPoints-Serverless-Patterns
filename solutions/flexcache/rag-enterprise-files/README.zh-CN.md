# GenAI RAG — 企业文件

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

通过 S3 Access Points 将企业文件服务器（FSx for ONTAP）上的机密文档安全地提供给 Amazon Bedrock / RAG 管道，**无需复制到 S3**。在保持文件权限（ACL/NTFS）的同时实现 Permission-aware RAG。

## 解决的问题

| 问题 | 解决方案 |
|------|----------|
| 将敏感文件复制到 S3 导致数据扩散 | 通过 S3 AP 直接读取，无需复制 |
| 文件权限丢失 | 通过 ONTAP REST API 检索 ACL，在 RAG 响应时过滤 |
| 数据新鲜度问题 | FlexCache + S3 AP 提供最新数据 |
| 大型文件服务器的全卷处理 | EventBridge Scheduler + 增量检测提高效率 |
| AI 处理与数据之间的距离 | FlexCache 将数据放置在 AI 处理 VPC 附近 |

## Permission-aware RAG 概念

1. **索引时**: 通过 ONTAP REST API 检索每个文档的 ACL/权限信息，作为元数据存储在向量存储中
2. **查询时**: 根据用户的 AD SID / 组成员身份，将搜索范围过滤为仅用户可访问的文档
3. **响应时**: 仅将过滤后的文档传递给 Bedrock 生成答案

## FlexCache 的作用

- 将数据放置在 AI 处理环境（Lambda VPC）附近
- 加速嵌入处理期间的批量读取
- 减少到 Origin 的 WAN 传输
- 通过 S3 AP 提供无服务器处理

## 安全设计

- **无数据移动**: 文件保留在 FSx for ONTAP 上，通过 S3 AP 只读访问
- **权限保留**: 通过 ONTAP REST API 检索 ACL，在 RAG 响应时过滤
- **加密**: SSE-FSX（存储）、TLS（传输）、KMS（输出）
- **最小权限**: Lambda 仅允许必要的 S3 AP 操作
- **审计**: CloudTrail + ONTAP 审计日志

## 成功指标

| 指标 | 目标 |
|------|------|
| 每次执行处理的文件数 | > 200 文件 |
| ACL 提取成功率 | > 95% |
| 嵌入生成时间 | < 5 分钟 / 100 文件 |
| Permission-aware 过滤准确率 | > 99% |
| Human Review 比率 | < 10%（低置信度块） |

---

## 部署

使用 AWS SAM CLI 部署（请将占位符替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-rag-enterprise-files \
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

> **关于文件级 ACL 提取**: 默认情况下 ACL 提取以模拟模式运行（无需 ONTAP）。若要提取真实 ACL，请设置 `OntapManagementIp` / `OntapSecretName`。请注意本模板不包含 `VpcConfig`，因此要访问私有 ONTAP 管理 LIF 需要额外的网络配置。

## Governance Note

> 本模式提供技术架构指导。不构成法律、合规或监管建议。组织应咨询合格的专业人员。
