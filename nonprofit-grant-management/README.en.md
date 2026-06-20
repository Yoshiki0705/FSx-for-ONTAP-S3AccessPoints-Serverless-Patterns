# UC24: Nonprofit — Grant Application Classification / Outcome Matching

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to automatically classify grant applications, extract applicant information and budgets, and match outcome metrics from activity reports against original grant objectives.

## Success Metrics

### Outcome
Automate document processing and analysis to improve operational efficiency and compliance.

### Metrics
| Metric | Target (Example) |
|--------|-----------------|
| Grant application classification accuracy | ≥ 85% |
| Outcome achievement measurement accuracy | ≥ 80% |
| Application data extraction rate | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $1.50 |
| Human review required rate | > 25% (low-confidence classifications) |

### Measurement Method
Step Functions execution history, AI/ML service extraction results, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Low-confidence results require manual verification
- Critical alerts reviewed by domain experts
- Periodic summary reports reviewed by management

## Architecture

See [Architecture Document](docs/architecture.en.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3 or later)
- S3 Access Point enabled on volume
- VPC with private subnets
- Amazon Bedrock model access enabled (Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1) configuration

> **S3 AP NetworkOrigin Note**: The Discovery Lambda is deployed inside a VPC. If the S3 Access Point's NetworkOrigin is `Internet`, it cannot be accessed via S3 Gateway VPC Endpoint (requests are not routed to the FSx data plane). Use a VPC-origin S3 AP or configure NAT Gateway access. See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

## Deployment

```bash
aws cloudformation deploy \
  --template-file nonprofit-grant-management/template.yaml \
  --stack-name fsxn-nonprofit-grants \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```


## ⚠️ Performance Considerations

- FSx for ONTAP throughput capacity is **shared across NFS/SMB/S3 AP**. Running MapConcurrency=10 in parallel may impact other workloads on the same volume.
- For large batch processing, check FSx for ONTAP Throughput Capacity (MBps) and adjust MapConcurrency accordingly.
- Recommended: Start with MapConcurrency=5 in production, monitor FSx for ONTAP CloudWatch metrics (ThroughputUtilization), and increase gradually.

## Cleanup

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## Cost Estimate (Monthly)

> **Note**: Estimates for ap-northeast-1. Actual costs vary by usage.

| Configuration | Monthly Estimate |
|--------------|-----------------|
| Minimum (daily 1x) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. Handling of personal and organizational information in grant applications must comply with each funding agency's regulations and applicable privacy laws.

> **Related Regulations**: NPO 法, 公益法人認定法 (Public Interest Corporation Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) for FSx for ONTAP S3 Access Points constraints, troubleshooting, and trigger patterns.
