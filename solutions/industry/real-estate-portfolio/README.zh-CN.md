# UC26: 房地产 — 物业图片分析 / 合同提取

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

这是一个利用 FSx for ONTAP 的 S3 Access Points 的无服务器工作流，可从物业图片中提取特征并自动生成房源描述、从租赁合同中提取条款、并通过 PII 检测实现隐私保护。

## Success Metrics

### Outcome
通过文档处理与分析的自动化，实现运营效率提升和合规强化。

### Metrics
| 指标 | 目标值（示例） |
|------|--------------|
| 物业特征提取准确率 | ≥ 85% |
| PII 检测率 | ≥ 95% |
| 合同条款提取准确率 | ≥ 90% |
| 报告生成时间 | < 5 分钟 / 批次 |
| 成本 / 每日执行 | < $2.50 |
| Human Review 必需比例 | > 20%（PII 检测图片全部确认） |

### Measurement Method
Step Functions 执行历史、AI/ML 服务提取结果、CloudWatch EMF Metrics（ProcessingDuration、SuccessCount、ErrorCount）。

### Human Review Requirements
- 低置信度结果需要人工确认
- Critical 告警由领域专家审核
- 定期汇总报告由管理层审核

## 架构

有关详细的数据流图，请参阅[架构文档](docs/architecture.zh-CN.md)。

## 前提条件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（因为请求不会路由到 FSx for ONTAP 数据平面）。请使用 NetworkOrigin=VPC 的 S3 AP，或配置通过 NAT Gateway 的访问。详情请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。

- AWS 账户及适当的 IAM 权限
- FSx for ONTAP 文件系统（ONTAP 9.17.1P4D3 及以上）
- 已启用 S3 Access Point 的卷
- VPC、私有子网
- 已启用 Amazon Bedrock 模型访问（Claude / Nova）
- Amazon Textract — Cross-Region (us-east-1) 调用配置

## 部署步骤

```bash
# 前提条件：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-real-estate \
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

> **注意**: `template.yaml` 用于配合 SAM CLI（`sam build` + `sam deploy`）使用。
> 若使用 `aws cloudformation deploy` 命令直接部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3）。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。以 MapConcurrency=10 进行并行处理时，可能会影响同一卷上的其他工作负载。
- 进行大量文件批处理时，请确认 FSx for ONTAP 的 Throughput Capacity (MBps)，并根据需要调整 MapConcurrency。
- 建议：在生产环境中先以 MapConcurrency=5 起步，一边监控 FSx for ONTAP 的 CloudWatch 指标 (ThroughputUtilization) 一边逐步增加。

## 清理

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## 成本估算（每月概算）

> **备注**: 基于 ap-northeast-1 区域的概算。实际成本因使用量而异。

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次） | ~$8-20 |
| 标准配置 | ~$20-50 |

---

## Governance Note

> 本模式提供技术架构指导。它不构成法律、合规或监管方面的建议。租赁合同中包含的租户信息必须依据适用的个人信息保护法妥善管理。物业图片中出现的个人信息的处理还应留意房地产交易相关法规。

> **相关法规**: 宅地建物取引業法 (不动产中介业法), 個人情報保護法 (个人信息保护法)

---

## S3AP Compatibility

有关 S3 Access Points for FSx for ONTAP 的兼容性约束、故障排查和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
