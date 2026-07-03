# UC27：人力资源 — 简历筛选 / PII 严格模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

这是一个利用 FSx for ONTAP 的 S3 Access Points，从简历和履历中结构化提取技能与经验，并以 PII 严格模式排除受保护特征后进行评分的无服务器工作流。

> **重要：监管注意事项**
> 本模式是一个**文档分诊与摘要工作流**，而非自动招聘决策系统。最终招聘决策必须始终由具备资格的人力资源人员做出。使用前，必须验证其是否符合各国家和地区的劳动法、隐私法规（GDPR、APPI、CCPA 等）以及反歧视要求。输出中不得包含按受保护特征进行的排名，评估说明仅以与职务相关的资格和经验为依据。

## Success Metrics

### Outcome
通过文档处理与分析的自动化，实现运营效率提升与合规强化。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| 简历数据提取率 | ≥ 90% |
| 评分公平性 | 无受保护特征偏见（排除年龄、性别、国籍） |
| PII 合规性 | 100%（日志中零 PII 输出） |
| 报告生成时间 | < 5 分钟 / 批次 |
| 成本 / 每日执行 | < $2.00 |
| Human Review 必需率 | > 30%（所有评分结果由人力资源团队确认） |

### Measurement Method
Step Functions 执行历史、AI/ML 服务提取结果、CloudWatch EMF Metrics（ProcessingDuration, SuccessCount, ErrorCount）。

### Human Review Requirements
- 低置信度结果需要人工确认
- Critical 告警由领域专家审核
- 定期摘要报告由管理层审核

### Output Safeguard Requirements
- 输出架构中不得包含 age/gender/ethnicity/nationality 字段
- 评估说明仅以与职务相关的资格和经验为依据
- 检测到的受保护特征应在存储前予以移除
- 所有推荐结果都必须经过人工审核

## 架构

详细的数据流图请参阅[架构文档](docs/architecture.zh-CN.md)。

## 前提条件

> **S3 AP NetworkOrigin 注意**：Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（因为不会路由到 FSx 数据平面）。请使用 NetworkOrigin=VPC 的 S3 AP，或配置经由 NAT Gateway 的访问。详情请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 账户与适当的 IAM 权限
- FSx for ONTAP 文件系统（ONTAP 9.17.1P4D3 及以上）
- 已启用 S3 Access Point 的卷
- VPC、私有子网
- 已启用 Amazon Bedrock 模型访问（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 调用配置

## 部署步骤

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **注意**：`template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 若使用 `aws cloudformation deploy` 命令直接部署，请使用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3）。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。以 MapConcurrency=10 进行并行处理时，可能会影响同一卷上的其他工作负载。
- 进行大量文件的批量处理时，请确认 FSx for ONTAP 的 Throughput Capacity (MBps)，并根据需要调整 MapConcurrency。
- 建议：在生产环境中先以 MapConcurrency=5 开始，并在监控 FSx for ONTAP 的 CloudWatch 指标 (ThroughputUtilization) 的同时逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## 成本估算（每月概算）

> **备注**：ap-northeast-1 区域的概算。实际成本因使用量而异。

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次） | ~$8-20 |
| 标准配置 | ~$20-50 |

---

## Governance Note

> 本模式提供技术架构指导。这不构成法律、合规或监管建议。招聘选拔中的 AI 应用必须遵守《职业安定法》和《男女雇用机会均等法》，并排除基于受保护特征（年龄、性别、国籍等）的偏见。AI 评分仅为参考信息，最终判断必须由人力资源人员做出。

> **相关法规**：职业安定法、个人信息保护法、劳动基准法

---

## S3AP Compatibility

关于 FSx for ONTAP S3 Access Points 的兼容性约束、故障排除和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
