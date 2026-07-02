# UC20: 旅行与酒店业 — 预订文档处理 / 设施检查图像分析

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

利用 FSx for ONTAP S3 Access Points，自动从酒店/旅馆的预订文档（PDF、扫描图像）中提取结构化数据，并对设施检查图像进行状态分析和维护建议自动生成的无服务器工作流。

### 主要功能

- 通过 S3 AP 自动检测预订文档和设施检查图像
- Textract + Comprehend 结构化数据提取（住客姓名、日期、房间类型、金额）
- 多语言支持（语言检测 → Textract 提示 + Comprehend 模型自动选择）
- Rekognition 设施状态分析（损伤检测、清洁度评分 0–100）
- Bedrock 维护建议生成

## Success Metrics

| 指标 | 目标值 |
|------|--------|
| 预订数据提取准确率 | ≥ 90% |
| 设施状态检测率 | ≥ 85% |
| 多语言支持覆盖率 | ≥ 5 种语言 |
| 报告生成时间 | < 5 分钟/批次 |
| 人工审核率 | > 15% |

## 治理说明

> 本模式提供技术架构指导，不构成法律、合规或监管建议。

## 部署

使用 AWS SAM CLI 部署（请将占位参数替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-travel-processing \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
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

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（请求不会路由到 FSx 数据平面）。请使用 VPC-origin S3 AP 或配置 NAT Gateway 访问。详见 [S3AP 兼容性说明](../docs/s3ap-compatibility-notes.md)。

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
