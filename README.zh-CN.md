# FSxN S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

基于 Amazon FSx for NetApp ONTAP S3 Access Points 的行业专属无服务器自动化模式集合。

## 概述

本仓库提供 **5 种行业专属模式**，通过 **S3 Access Points** 对存储在 FSx for NetApp ONTAP 上的企业数据进行无服务器处理。

每个用例都是独立的 CloudFormation 模板，共享模块（ONTAP REST API 客户端、FSx 辅助工具、S3 AP 辅助工具）位于 `shared/` 目录中。

### 主要特性

- **轮询架构**: EventBridge Scheduler + Step Functions（FSx ONTAP S3 AP 不支持 `GetBucketNotificationConfiguration`）
- **共享模块分离**: OntapClient / FsxHelper / S3ApHelper 在所有用例中复用
- **CloudFormation 原生**: 每个用例都是独立的 CloudFormation 模板
- **安全优先**: 默认启用 TLS 验证、最小权限 IAM、KMS 加密
- **成本优化**: 高成本常驻资源（VPC Endpoints 等）为可选项

## 用例

| # | 目录 | 行业 | 模式 | AI/ML 服务 | 区域兼容性 |
|---|------|------|------|-----------|-----------|
| UC1 | `legal-compliance/` | 法务合规 | 文件服务器审计与数据治理 | Athena, Bedrock | 所有区域 |
| UC2 | `financial-idp/` | 金融服务 | 合同/发票处理 (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: 跨区域 |
| UC3 | `manufacturing-analytics/` | 制造业 | IoT 传感器日志与质量检测 | Athena, Rekognition | 所有区域 |
| UC4 | `media-vfx/` | 媒体与娱乐 | VFX 渲染管线 | Rekognition, Deadline Cloud | Deadline Cloud 区域 |
| UC5 | `healthcare-dicom/` | 医疗健康 | DICOM 图像分类与脱敏 | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: 跨区域 |

> **区域限制**: Amazon Textract 和 Amazon Comprehend Medical 并非在所有区域可用（例如 ap-northeast-1）。可通过 `TEXTRACT_REGION` 和 `COMPREHEND_MEDICAL_REGION` 参数进行跨区域调用。详见[区域兼容性矩阵](docs/region-compatibility.md)。

## 快速开始

### 前提条件

- AWS CLI v2
- Python 3.12+
- 已启用 S3 Access Points 的 FSx for NetApp ONTAP
- 存储在 AWS Secrets Manager 中的 ONTAP 凭证

### 部署

> ⚠️ **对现有环境的影响**
>
> - `EnableS3GatewayEndpoint=true` 会向您的 VPC 添加 S3 Gateway Endpoint。如果已存在，请设置为 `false`。
> - `ScheduleExpression` 会触发定期的 Step Functions 执行。如果不需要立即使用，请在部署后禁用调度。
> - 如果 S3 存储桶包含对象，堆栈删除可能会失败。删除前请清空存储桶。
> - VPC Endpoint 删除需要 5-15 分钟。Lambda ENI 释放可能会延迟 Security Group 的删除。
>
> **区域**: 建议使用 `us-east-1` 或 `us-west-2` 以获得完整的 AI/ML 服务可用性。详见[区域兼容性](docs/region-compatibility.md)。

```bash
# 设置区域
export AWS_DEFAULT_REGION=us-east-1

# 打包 Lambda 函数
./scripts/deploy_uc.sh legal-compliance package

# 部署 CloudFormation 堆栈
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ParameterKey=PrivateRouteTableIds,ParameterValue=<your-route-table-ids> \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false
```

## 文档

| 文档 | 说明 |
|------|------|
| [部署指南](docs/guides/deployment-guide.md) | 分步部署说明 |
| [运维指南](docs/guides/operations-guide.md) | 监控与运维流程 |
| [故障排除指南](docs/guides/troubleshooting-guide.md) | 常见问题与解决方案 |
| [成本分析](docs/cost-analysis.md) | 成本结构与优化 |
| [区域兼容性](docs/region-compatibility.md) | 各区域服务可用性 |
| [扩展模式](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [验证结果](docs/verification-results.md) | AWS 环境测试结果 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| IaC | CloudFormation (YAML) |
| 计算 | AWS Lambda |
| 编排 | AWS Step Functions |
| 调度 | Amazon EventBridge Scheduler |
| 存储 | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| 安全 | Secrets Manager, KMS, IAM 最小权限 |
| 测试 | pytest + Hypothesis (PBT) |

## 许可证

MIT License。详见 [LICENSE](LICENSE)。
