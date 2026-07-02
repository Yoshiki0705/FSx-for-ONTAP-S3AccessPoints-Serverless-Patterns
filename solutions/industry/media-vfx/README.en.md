# UC4: Media — VFX Rendering Pipeline

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture Diagram](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow that leverages S3 Access Points in FSx for ONTAP to automate the submission of VFX rendering jobs, quality checks, and the write-back of approved outputs.

### When this pattern is a good fit

- You use FSx for ONTAP as rendering storage for VFX / animation production
- You want to automate quality checks after rendering completes and reduce the burden of manual review
- You want to automatically write assets that pass quality checks back to the file server (S3 AP PutObject)
- You want to build a pipeline that integrates Deadline Cloud with existing NAS storage

### When this pattern is not a good fit

- You need immediate kick-off of rendering jobs (file-save triggers)
- You use a rendering farm other than Deadline Cloud (e.g., on-premises Thinkbox Deadline)
- Rendering output exceeds 5 GB (the S3 AP PutObject limit)
- Quality checks require a proprietary image-quality evaluation model (Rekognition label detection is insufficient)

### Key features

- Automatic detection of target rendering assets via S3 AP
- Automatic submission of rendering jobs to AWS Deadline Cloud
- Quality assessment with Amazon Rekognition (resolution, artifacts, color consistency)
- On pass, PutObject to FSx for ONTAP via S3 AP; on fail, SNS notification

## Success Metrics

### Outcome
Reduce asset search time through automatic classification and metadata tagging of VFX assets.

### Metrics
| Metric | Target (example) |
|-----------|------------|
| Processed assets per run | > 200 files |
| Metadata tagging success rate | > 95% |
| Reduction in asset search time | > 60% |
| Processing time per file | < 60 sec |
| Cost per run | < $10 |
| Human Review rate | < 10% |

### Measurement Method
Step Functions execution history, Rekognition label count, S3 output metadata.

## Architecture

```mermaid
graph LR
    subgraph "Step Functions workflow"
        D[Discovery Lambda<br/>Asset discovery]
        JS[Job Submit Lambda<br/>Deadline Cloud job submission]
        QC[Quality Check Lambda<br/>Rekognition quality assessment]
    end

    D -->|Manifest| JS
    JS -->|Job Result| QC

    D -.->|ListObjectsV2| S3AP[S3 Access Point]
    JS -.->|GetObject| S3AP
    JS -.->|CreateJob| DC[AWS Deadline Cloud]
    QC -.->|DetectLabels| Rekognition[Amazon Rekognition]
    QC -.->|PutObject (on pass)| S3AP
    QC -.->|Publish (on fail)| SNS[SNS Topic]
```

### Workflow Steps

1. **Discovery**: Detect target rendering assets from the S3 AP and generate a Manifest
2. **Job Submit**: Retrieve assets via the S3 AP and submit rendering jobs to AWS Deadline Cloud
3. **Quality Check**: Evaluate the quality of rendering results with Rekognition. On pass, PutObject to the S3 AP; on fail, flag for re-rendering with an SNS notification

## Prerequisites

- An AWS account and appropriate IAM permissions
- An FSx for ONTAP file system (ONTAP 9.17.1P4D3 or later)
- A volume with S3 Access Points enabled
- ONTAP REST API credentials registered in Secrets Manager
- A VPC and private subnets
- An AWS Deadline Cloud Farm / Queue already configured
- A region where Amazon Rekognition is available

## Deployment Steps

### 1. Prepare parameters

Before deploying, confirm the following values:

- FSx for ONTAP S3 Access Point Alias
- ONTAP management IP address
- Secrets Manager secret name
- AWS Deadline Cloud Farm ID / Queue ID
- VPC ID, private subnet IDs

### 2. SAM deployment

```bash
# Prerequisite: AWS SAM CLI is required. sam build packages the code and shared layer automatically.
sam build

sam deploy \
  --stack-name fsxn-media-vfx \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    S3AccessPointOutputAlias=<your-output-volume-ext-s3alias> \
    OntapSecretName=<your-ontap-secret-name> \
    OntapManagementIp=<your-ontap-management-ip> \
    ScheduleExpression="rate(1 hour)" \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    DeadlineFarmId=<your-deadline-farm-id> \
    DeadlineQueueId=<your-deadline-queue-id> \
    QualityThreshold=80.0 \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Note**: `template.yaml` is used with the SAM CLI (`sam build` + `sam deploy`).
> To deploy directly with the `aws cloudformation deploy` command, use `template-deploy.yaml` instead (this requires pre-packaging the Lambda zip files and uploading them to S3).

> **Note**: Replace the `<...>` placeholders with your actual environment values.

### 3. Confirm the SNS subscription

After deployment, an SNS subscription confirmation email is sent to the address you specified.

> **Note**: If you omit `S3AccessPointName`, the IAM policy becomes Alias-based only, which may cause an `AccessDenied` error. Specifying it is recommended for production environments. For details, see the [Troubleshooting Guide](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー).

## Configuration Parameters

| Parameter | Description | Default | Required |
|-----------|------|----------|------|
| `S3AccessPointAlias` | FSx for ONTAP S3 AP Alias (for input) | — | ✅ |
| `S3AccessPointName` | S3 AP name (for ARN-based IAM permission grants; Alias-based only when omitted) | `""` | ⚠️ Recommended |
| `S3AccessPointOutputAlias` | FSx for ONTAP S3 AP Alias (for output) | — | ✅ |
| `OntapSecretName` | Secrets Manager secret name for ONTAP credentials | — | ✅ |
| `OntapManagementIp` | ONTAP cluster management IP address | — | ✅ |
| `ScheduleExpression` | EventBridge Scheduler schedule expression | `rate(1 hour)` | |
| `VpcId` | VPC ID | — | ✅ |
| `PrivateSubnetIds` | List of private subnet IDs | — | ✅ |
| `NotificationEmail` | SNS notification email address | — | ✅ |
| `DeadlineFarmId` | AWS Deadline Cloud Farm ID | — | ✅ |
| `DeadlineQueueId` | AWS Deadline Cloud Queue ID | — | ✅ |
| `QualityThreshold` | Rekognition quality assessment threshold (0.0–100.0) | `80.0` | |
| `EnableVpcEndpoints` | Enable Interface VPC Endpoints | `false` | |
| `EnableCloudWatchAlarms` | Enable CloudWatch Alarms | `false` | |

## Cost Structure

### Request-based (pay-as-you-go)

| Service | Billing unit | Estimate (100 assets/month) |
|---------|---------|----------------------|
| Lambda | Number of requests + execution time | ~$0.01 |
| Step Functions | Number of state transitions | Within free tier |
| S3 API | Number of requests | ~$0.01 |
| Rekognition | Number of images | ~$0.10 |
| Deadline Cloud | Rendering time | Estimated separately※ |

※ The cost of AWS Deadline Cloud depends on the scale and duration of the rendering jobs.

### Always-on (optional)

| Service | Parameter | Monthly |
|---------|-----------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints=true` | ~$28.80 |
| CloudWatch Alarms | `EnableCloudWatchAlarms=true` | ~$0.20 |

> In a demo/PoC environment, you can start from **~$0.12/month** with variable costs only (excluding Deadline Cloud).

## Cleanup

```bash
# Delete the CloudFormation stack
aws cloudformation delete-stack \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-media-vfx \
  --region ap-northeast-1
```

> **Note**: Stack deletion may fail if objects remain in the S3 bucket. Empty the bucket beforehand.

## Supported Regions

UC4 uses the following services:

| Service | Region constraint |
|---------|-------------|
| Amazon Rekognition | Available in almost all regions |
| AWS Deadline Cloud | Limited region availability ([Deadline Cloud supported regions](https://docs.aws.amazon.com/general/latest/gr/deadline-cloud.html)) |
| AWS X-Ray | Available in almost all regions |
| CloudWatch EMF | Available in almost all regions |

> For details, see the [Region Compatibility Matrix](../docs/region-compatibility.md).

## References

### AWS Official Documentation

- [FSx for ONTAP S3 Access Points overview](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Streaming with CloudFront (official tutorial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html)
- [Serverless processing with Lambda (official tutorial)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Deadline Cloud API Reference](https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html)
- [Rekognition DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html)

### AWS Blog Posts

- [S3 AP announcement blog](https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/)
- [Three serverless architecture patterns](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### GitHub Samples

- [aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing](https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing) — Large-scale Rekognition processing
- [aws-samples/dotnet-serverless-imagerecognition](https://github.com/aws-samples/dotnet-serverless-imagerecognition) — Step Functions + Rekognition
- [aws-samples/serverless-patterns](https://github.com/aws-samples/serverless-patterns) — Serverless patterns collection

### In-Project Guides

- [FlexClone Serverless Patterns (Japanese)](../docs/guides/flexclone-serverless-patterns.md) — Sequential frame processing pipeline with FlexClone + Step Functions + S3AP, multiprotocol mount, industry use cases
- [FlexClone Serverless Patterns (English)](../docs/guides/flexclone-serverless-patterns-en.md) — FlexClone + Step Functions + S3AP sequential frame processing pipeline

## Validated Environment

| Item | Value |
|------|-----|
| AWS Region | ap-northeast-1 (Tokyo) |
| FSx for ONTAP version | ONTAP 9.17.1P4D3 |
| FSx configuration | SINGLE_AZ_1 |
| Python | 3.12 |
| Deployment method | CloudFormation (standard) |

## Lambda VPC Placement Architecture

Based on lessons learned during validation, the Lambda functions are split between inside and outside the VPC.

**Lambda inside the VPC** (only functions that need ONTAP REST API access):
- Discovery Lambda — S3 AP + ONTAP API

**Lambda outside the VPC** (using only AWS managed service APIs):
- All other Lambda functions

> **Reason**: Accessing AWS managed service APIs (Athena, Bedrock, Textract, etc.) from a Lambda inside the VPC requires an Interface VPC Endpoint ($7.20/month each). Lambda functions outside the VPC can access AWS APIs directly over the internet and run at no additional cost.

> **Note**: For UCs that use the ONTAP REST API (UC1 Legal & Compliance), `EnableVpcEndpoints=true` is mandatory, because ONTAP credentials are retrieved through the Secrets Manager VPC Endpoint.

## FlexCache Rendering Acceleration Extension

### Overview

In VFX rendering workflows, render input assets (textures, geometry, plates) are read-centric, making them an ideal target for FlexCache. By dynamically creating a FlexCache at job start and automatically deleting it after rendering completes, you can achieve both cost optimization and performance improvement.

### Rendering Data Classification

| Data type | Access pattern | FlexCache applicable | S3 AP usage |
|-----------|---------------|:---:|:---:|
| Textures | Read-only | ✅ | ⚠️ Binary |
| Geometry/Plates | Read-only | ✅ | ⚠️ Binary |
| Scene Files | Read-only | ✅ | ❌ |
| Render Output (EXR/PNG) | Write | ❌ | ✅ QC/metadata |
| Logs | Write → read | ❌ | ✅ Analysis |
| Cache (sim/fluid) | Read/write | ❌ | ❌ |

### Dynamic FlexCache Render Workflow

For details on a workflow that creates and deletes a FlexCache per job, see:

- **[Dynamic FlexCache Render/EDA Workflow](../dynamic-flexcache-render-workflow/README.md)** — Automation with Step Functions
- [FlexCache AnyCast / DR](../flexcache-anycast-dr/README.md) — Multi-region render farm
- [Industry / Workload Mapping](../docs/industry-workload-mapping.md) — Pattern E: Media/VFX Render Farm

### Expected Benefits

| KPI | Without FlexCache | With FlexCache | Improvement |
|-----|--------------|---------------|--------|
| Wait to start rendering | 10-20 min | 2-5 min | 75% |
| Time per frame | 15 min | 10 min | 33% |
| WAN transfer per job | 500GB | 50GB | 90% |
| Cost per frame | $0.50 | $0.35 | 30% |

---

## AWS Documentation Links

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon CloudFront | [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) |
| Amazon Bedrock | [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework Alignment

| Pillar | Alignment |
|----|------|
| Operational Excellence | X-Ray tracing, EMF metrics, job status monitoring |
| Security | Least-privilege IAM, CloudFront OAC, KMS encryption |
| Reliability | Step Functions Retry/Catch, quality check gate |
| Performance Efficiency | CloudFront CDN delivery, Lambda parallel processing |
| Cost Optimization | Serverless, CloudFront cache utilization |
| Sustainability | On-demand execution, reduced origin load via CDN |

---

## Local Testing

### Prerequisites check

```bash
# Confirm prerequisites
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (for sam local)
aws sts get-caller-identity  # AWS credentials
```

### sam local invoke

```bash
# Build
# Prerequisite: AWS SAM CLI is required. sam build packages the code and shared layer automatically.
sam build

# Run the Discovery Lambda locally
sam local invoke DiscoveryFunction --event events/discovery-event.json

# With environment variable overrides
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit tests

```bash
python3 -m pytest tests/ -v
```

For details, see the [Local Testing Quick Start](../docs/local-testing-quick-start.md).

---

## Output Sample

Example output of a VFX rendering quality check:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 48,
    "prefix": "renders/shot-042/"
  },
  "quality_check": [
    {
      "key": "renders/shot-042/frame-0001.exr",
      "resolution": "4096x2160",
      "color_space": "ACEScg",
      "quality_score": 0.94,
      "issues": [],
      "cloudfront_url": "https://d1234.cloudfront.net/delivery/shot-042/frame-0001.exr"
    }
  ],
  "delivery": {
    "total_frames": 48,
    "passed_qc": 46,
    "failed_qc": 2,
    "cloudfront_distribution": "d1234.cloudfront.net"
  }
}
```

> **Note**: The above is a sample output; actual values vary by environment and input data. Benchmark figures are a sizing reference, not a service limit.

---

## Governance Note

> This pattern provides technical architecture guidance. It is not legal, compliance, or regulatory advice. Organizations should consult qualified professionals.

---

## S3AP Compatibility

For S3 Access Points for FSx for ONTAP compatibility constraints, troubleshooting, and trigger patterns, see [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
