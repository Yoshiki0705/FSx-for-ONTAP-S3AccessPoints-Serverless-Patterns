# UC27: 人力资源 — 简历筛选 / PII严格模式

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to extract structured skills and experience from resumes, with PII strict mode that excludes protected characteristics from scoring.

## Success Metrics

| Metric | Target |
|--------|--------|
| Resume data extraction rate | ≥ 90% |
| Scoring fairness | No protected characteristic bias (age/gender/nationality excluded) |
| PII compliance | 100% (zero PII in logs) |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.00 |
| Human review required rate | > 30% (all scoring results reviewed by HR team) |

## Architecture

See [Architecture Document](docs/architecture.zh-CN.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled
- Amazon Textract — Cross-Region (us-east-1)

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（请求不会路由到 FSx 数据平面）。请使用 VPC-origin S3 AP 或配置 NAT Gateway 访问。详见 [S3AP 兼容性说明](../docs/s3ap-compatibility-notes.md)。

## Deployment

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
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。使用 MapConcurrency=10 进行并行处理时可能影响同一卷上的其他工作负载。
- 进行大规模批量处理时，请检查 FSx for ONTAP 的 Throughput Capacity (MBps) 并相应调整 MapConcurrency。
- 建议：在生产环境中从 MapConcurrency=5 开始，监控 CloudWatch 指标 (ThroughputUtilization)，然后逐步增加。

## Cleanup

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. AI usage in recruitment screening must comply with employment laws and equal opportunity regulations, excluding bias based on protected characteristics (age, gender, nationality). AI scoring is advisory only; final decisions must be made by HR professionals.

> **Related Regulations**: 職業安定法 (Employment Security Act), 個人情報保護法 (APPI), 労働基準法 (Labor Standards Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
