# UC28: 化工与材料 — SDS 危险分类提取 / GHS 验证

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

一个利用 FSx for ONTAP S3 Access Points 的无服务器工作流，可从 SDS（安全数据表）中提取危险分类和处理注意事项，验证 GHS 必填章节的完整性，并从实验记录本图像中提取实验数据。

## Success Metrics

### Outcome
通过自动化文档处理与分析，实现运营效率提升和合规性强化。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| GHS 章节验证完整性 | 100%（验证 8 个必填章节） |
| 过期 SDS 检测率 | 100% |
| 危险分类提取精度 | ≥ 90% |
| 报告生成时间 | < 5 分钟 / 批次 |
| 成本 / 每日执行 | < $2.50 |
| Human Review 必需比例 | > 25%（全部 Critical 优先级告警均需确认） |

### Measurement Method
Step Functions 执行历史、AI/ML 服务提取结果、CloudWatch EMF Metrics（ProcessingDuration、SuccessCount、ErrorCount）。

### Human Review Requirements
- 低置信度结果需要人工确认
- Critical 告警由领域专家审查
- 定期汇总报告由管理层审查

## 架构

有关详细的数据流图，请参阅[架构文档](docs/architecture.zh-CN.md)。

## 前提条件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（请求不会路由到 FSx 数据平面）。请使用 NetworkOrigin=VPC 的 S3 AP，或配置通过 NAT Gateway 的访问。详情请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 账户及适当的 IAM 权限
- FSx for ONTAP 文件系统（ONTAP 9.17.1P4D3 及以上）
- 已启用 S3 Access Point 的卷
- VPC、私有子网
- 已启用 Amazon Bedrock 模型访问（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 调用配置

## 部署步骤

```bash
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-chemical-sds \
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
> 若要使用 `aws cloudformation deploy` 命令直接部署，请使用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3）。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。使用 MapConcurrency=10 进行并行处理时，可能会影响同一卷上的其他工作负载。
- 进行大量文件的批量处理时，请确认 FSx for ONTAP 的 Throughput Capacity (MBps)，并根据需要调整 MapConcurrency。
- 建议: 在生产环境中先以 MapConcurrency=5 开始，并在监控 FSx for ONTAP 的 CloudWatch 指标 (ThroughputUtilization) 的同时逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds --region ap-northeast-1
```

## 成本估算（每月概算）

> **注记**: ap-northeast-1 区域的概算。实际成本因使用量而异。

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次） | ~$8-20 |
| 标准配置 | ~$20-50 |

---

## Governance Note

> 本模式提供技术架构指导。它不构成法律、合规或监管方面的建议。SDS 中所含化学物质信息的处理必须遵守适用的化学物质管理及劳动安全卫生法律法规。GHS 分类的最终判定必须由具备资质的化学安全专业人员做出。

> **相关法规**: 化学物质管理促进法（PRTR 法）、劳动安全卫生法、消防法

---

## S3AP Compatibility

有关 FSx for ONTAP S3 Access Points 的兼容性约束、故障排查和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
