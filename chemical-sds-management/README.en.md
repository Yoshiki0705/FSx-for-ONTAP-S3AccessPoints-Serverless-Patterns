# UC28: Chemicals & Materials — SDS Hazard Extraction / GHS Validation

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to extract hazard classifications and handling precautions from Safety Data Sheets (SDS), validate GHS mandatory section completeness, and extract experimental data from laboratory notebook images.

## Success Metrics

### Outcome
Automate document processing and analysis to improve operational efficiency and compliance.

### Metrics
| Metric | Target (Example) |
|--------|-----------------|
| GHS section validation completeness | 100% (8 mandatory sections verified) |
| Expired SDS detection rate | 100% |
| Hazard classification extraction accuracy | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.50 |
| Human review required rate | > 25% (all critical priority alerts reviewed) |

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
  --template-file chemical-sds-management/template.yaml \
  --stack-name fsxn-chemical-sds \
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
- For large batch processing, check FSx ONTAP Throughput Capacity (MBps) and adjust MapConcurrency accordingly.
- Recommended: Start with MapConcurrency=5 in production, monitor FSx ONTAP CloudWatch metrics (ThroughputUtilization), and increase gradually.

## Cleanup

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds --region ap-northeast-1
```

## Cost Estimate (Monthly)

> **Note**: Estimates for ap-northeast-1. Actual costs vary by usage.

| Configuration | Monthly Estimate |
|--------------|-----------------|
| Minimum (daily 1x) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. Handling of chemical substance information in SDS must comply with applicable chemical management and occupational safety laws. Final GHS classification determinations must be made by qualified chemical safety professionals.

> **Related Regulations**: 化学物質管理促進法 (PRTR Act), 労働安全衛生法 (Industrial Safety and Health Act), 消防法 (Fire Service Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) for FSx for ONTAP S3 Access Points constraints, troubleshooting, and trigger patterns.
