# FSxN S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

A collection of industry-specific serverless automation patterns leveraging Amazon FSx for NetApp ONTAP S3 Access Points.

## Overview

This repository provides **5 industry-specific patterns** for serverless processing of enterprise data stored on FSx for NetApp ONTAP via **S3 Access Points**.

Each use case is self-contained as an independent CloudFormation template, with shared modules (ONTAP REST API client, FSx helper, S3 AP helper) in `shared/`.

### Key Features

- **Polling-based architecture**: EventBridge Scheduler + Step Functions (FSx ONTAP S3 AP does not support `GetBucketNotificationConfiguration`)
- **Shared module separation**: OntapClient / FsxHelper / S3ApHelper reused across all use cases
- **CloudFormation native**: Each use case is a standalone CloudFormation template
- **Security first**: TLS verification enabled by default, least-privilege IAM, KMS encryption
- **Cost optimized**: High-cost always-on resources (VPC Endpoints, etc.) are optional

## Use Cases

| # | Directory | Industry | Pattern | AI/ML Services | Region Compatibility |
|---|-----------|----------|---------|----------------|---------------------|
| UC1 | `legal-compliance/` | Legal & Compliance | File server audit & data governance | Athena, Bedrock | All regions |
| UC2 | `financial-idp/` | Financial Services | Contract/invoice processing (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: cross-region |
| UC3 | `manufacturing-analytics/` | Manufacturing | IoT sensor log & quality inspection | Athena, Rekognition | All regions |
| UC4 | `media-vfx/` | Media & Entertainment | VFX rendering pipeline | Rekognition, Deadline Cloud | Deadline Cloud regions |
| UC5 | `healthcare-dicom/` | Healthcare | DICOM image classification & anonymization | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: cross-region |

> **Region constraints**: Amazon Textract and Amazon Comprehend Medical are not available in all regions (e.g., ap-northeast-1). Cross-region calling is supported via `TEXTRACT_REGION` and `COMPREHEND_MEDICAL_REGION` parameters. See [Region Compatibility Matrix](docs/region-compatibility.md).

## Quick Start

### Prerequisites

- AWS CLI v2
- Python 3.12+
- FSx for NetApp ONTAP with S3 Access Points enabled
- ONTAP credentials in AWS Secrets Manager

### Deploy

```bash
# Set your region
export AWS_DEFAULT_REGION=us-east-1

# Package Lambda functions
./scripts/deploy_uc.sh legal-compliance package

# Deploy CloudFormation stack
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ...
```

## Documentation

| Document | Description |
|----------|-------------|
| [Deployment Guide](docs/guides/deployment-guide.md) | Step-by-step deployment instructions |
| [Operations Guide](docs/guides/operations-guide.md) | Monitoring and operations procedures |
| [Troubleshooting Guide](docs/guides/troubleshooting-guide.md) | Common issues and solutions |
| [Cost Analysis](docs/cost-analysis.md) | Cost structure and optimization |
| [Region Compatibility](docs/region-compatibility.md) | Service availability by region |
| [Extension Patterns](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [Verification Results](docs/verification-results.md) | AWS environment test results |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| IaC | CloudFormation (YAML) |
| Compute | AWS Lambda |
| Orchestration | AWS Step Functions |
| Scheduling | Amazon EventBridge Scheduler |
| Storage | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| Security | Secrets Manager, KMS, IAM least-privilege |
| Testing | pytest + Hypothesis (PBT) |

## License

MIT License. See [LICENSE](LICENSE) for details.
