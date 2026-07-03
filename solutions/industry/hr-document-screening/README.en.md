# UC27: Human Resources — Resume Screening / PII Strict Mode

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow that leverages FSx for ONTAP S3 Access Points to extract structured skills and experience from resumes and CVs, and performs scoring in PII strict mode that excludes protected characteristics.

> **Important: Regulatory Notice**
> This pattern is a **document triage and summarization workflow**, not an automated hiring decision system. Final hiring decisions must always be made by qualified HR personnel. Before use, you must verify compliance with the labor laws, privacy regulations (GDPR, APPI, CCPA, etc.), and anti-discrimination requirements of each country and region. Outputs must not include ranking by protected characteristics, and evaluation explanations must be based solely on job-related qualifications and experience.

## Success Metrics

### Outcome
Automate document processing and analysis to achieve operational efficiency and stronger compliance.

### Metrics
| Metric | Target (Example) |
|--------|-----------------|
| Resume data extraction rate | ≥ 90% |
| Scoring fairness | No protected characteristic bias (age/gender/nationality excluded) |
| PII compliance | 100% (zero PII in logs) |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.00 |
| Human Review required rate | > 30% (all scoring results reviewed by the HR team) |

### Measurement Method
Step Functions execution history, AI/ML service extraction results, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Low-confidence results require manual verification
- Critical alerts reviewed by domain experts
- Periodic summary reports reviewed by management

### Output Safeguard Requirements
- The output schema must not include age/gender/ethnicity/nationality fields
- Evaluation explanations must be based solely on job-related qualifications and experience
- Any detected protected characteristics must be removed before storage
- All recommendation results must require human review

## Architecture

See the [Architecture Document](docs/architecture.en.md) for detailed data flow diagrams.

## Prerequisites

> **S3 AP NetworkOrigin Note**: The Discovery Lambda is deployed inside a VPC. If the S3 Access Point's NetworkOrigin is `Internet`, it cannot be accessed via an S3 Gateway VPC Endpoint (requests are not routed to the FSx data plane). Use an S3 AP with NetworkOrigin=VPC, or configure access via a NAT Gateway. See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) for details.

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3 or later)
- Volume with S3 Access Point enabled
- VPC with private subnets
- Amazon Bedrock model access enabled (Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1) invocation configuration

## Deployment

```bash
# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.
sam build

sam deploy \
  --stack-name fsxn-hr-screening \
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

> **Note**: `template.yaml` is used with the SAM CLI (`sam build` + `sam deploy`).
> To deploy directly with the `aws cloudformation deploy` command, use `template-deploy.yaml` instead (this requires pre-packaging the Lambda zip files and uploading them to S3).

## ⚠️ Performance Considerations

- FSx for ONTAP throughput capacity is **shared across NFS/SMB/S3 AP**. Running parallel processing with MapConcurrency=10 may impact other workloads on the same volume.
- For bulk processing of large numbers of files, check the FSx for ONTAP Throughput Capacity (MBps) and adjust MapConcurrency as needed.
- Recommended: In production, start with MapConcurrency=5 and increase gradually while monitoring FSx for ONTAP CloudWatch metrics (ThroughputUtilization).

## Cleanup

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## Cost Estimate (Monthly)

> **Note**: Rough estimates for the ap-northeast-1 region. Actual costs vary by usage.

| Configuration | Monthly Estimate |
|------|---------|
| Minimum (daily 1x) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. The use of AI in recruitment screening must comply with the Employment Security Act and the Equal Employment Opportunity Act, and must eliminate bias based on protected characteristics (age, gender, nationality, etc.). AI scoring is advisory information only; the final decision must be made by HR personnel.

> **Related Regulations**: Employment Security Act, Act on the Protection of Personal Information (APPI), Labor Standards Act

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) for FSx for ONTAP S3 Access Points compatibility constraints, troubleshooting, and trigger patterns.
