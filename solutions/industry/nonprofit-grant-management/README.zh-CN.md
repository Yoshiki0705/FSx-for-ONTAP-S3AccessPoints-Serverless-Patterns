# UC24：非营利组织 — 补助金申请分类 / 成果匹配

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

利用 FSx for ONTAP 的 S3 Access Points 的无服务器工作流，可自动对补助金申请书进行分类，提取申请者信息和预算，并从活动报告中提取成果指标以与原始补助金目标进行匹配。

## Success Metrics

### Outcome
通过自动化文档处理与分析，实现运营效率提升与合规强化。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| 补助金申请分类准确率 | ≥ 85% |
| 成果达成度测量准确率 | ≥ 80% |
| 申请书数据提取率 | ≥ 90% |
| 报告生成时间 | < 5 分钟 / 批次 |
| 成本 / 每日执行 | < $1.50 |
| Human Review 必需率 | > 25%（低置信度分类结果） |

### Measurement Method
Step Functions 执行历史、AI/ML 服务提取结果、CloudWatch EMF Metrics（ProcessingDuration、SuccessCount、ErrorCount）。

### Human Review Requirements
- 低置信度结果需要人工确认
- Critical 告警由领域专家审查
- 定期汇总报告由管理层审查

## 架构

详细的数据流图请参阅[架构文档](docs/architecture.zh-CN.md)。

## 前提条件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。若 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（因为请求不会路由到 FSx 数据平面）。请使用 NetworkOrigin=VPC 的 S3 AP，或配置通过 NAT Gateway 的访问。详情请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 账户及适当的 IAM 权限
- FSx for ONTAP 文件系统（ONTAP 9.17.1P4D3 或更高版本）
- 已启用 S3 Access Point 的卷
- VPC、私有子网
- 已启用 Amazon Bedrock 模型访问（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 调用配置

## 部署步骤

```bash
# 前提：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
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

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 若要使用 `aws cloudformation deploy` 命令直接部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3）。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。以 MapConcurrency=10 进行并行处理时，可能会影响同一卷上的其他工作负载。
- 进行大量文件的批量处理时，请确认 FSx for ONTAP 的 Throughput Capacity (MBps)，并根据需要调整 MapConcurrency。
- 建议：在生产环境中先以 MapConcurrency=5 开始，同时监控 FSx for ONTAP 的 CloudWatch 指标 (ThroughputUtilization)，并逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## 成本估算（每月概算）

> **备注**: ap-northeast-1 区域的概算。实际成本因使用量而异。

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次） | ~$8-20 |
| 标准配置 | ~$20-50 |

---

## Governance Note

> 本模式提供技术架构指导。它不构成法律、合规或监管建议。补助金申请中所含个人信息与组织信息的处理，必须遵守各资助机构的规定及适用的个人信息保护法。

> **相关法规**: 日本 NPO 法（特定非营利活动促进法）、公益法人认定法

---

## S3AP Compatibility

有关 FSx for ONTAP S3 AP 的兼容性约束、故障排除和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
