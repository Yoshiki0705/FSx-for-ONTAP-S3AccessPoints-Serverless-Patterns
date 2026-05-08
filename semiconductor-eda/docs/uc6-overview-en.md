# UC6: Semiconductor / EDA — Design File Validation

## Overview

Serverless workflow that automates GDS/OASIS design file validation, metadata extraction, DRC statistics aggregation, and AI-generated design review reports — all powered by FSx for NetApp ONTAP S3 Access Points.

## Input → Output Summary

```
INPUT                          PROCESSING                      OUTPUT
─────                          ──────────                      ──────
GDS/OASIS files          →     Discovery (S3 AP)         →     Metadata JSON
on FSx ONTAP             →     Metadata Extraction       →     DRC Statistics (Athena)
                         →     DRC Aggregation           →     Design Review Report (Bedrock)
                         →     Report Generation         →     SNS Notification
```

## Architecture

```
FSx for NetApp ONTAP
    │
    ▼
S3 Access Point (no NFS mount needed)
    │
    ▼
EventBridge Scheduler ──▶ Step Functions
                              │
                    ┌─────────┼─────────────────────┐
                    ▼         ▼                     ▼
              Discovery   Map State            DRC Aggregation
              (VPC Lambda) (Metadata            (Athena SQL)
                           Extraction)              │
                                                    ▼
                                              Report Generation
                                              (Bedrock + SNS)
```

## Key Technical Highlights

### 1. Efficient Large File Handling
- GDS files can be **multi-GB** — we only read the first **64KB** (header) via Range request
- Binary header parsing extracts: library_name, units, cell_count, bounding_box, creation_date

### 2. GDSII Binary Parser
- Full GDSII record-level parser (HEADER, BGNLIB, LIBNAME, UNITS, BGNSTR)
- IBM floating-point (excess-64, base-16) to IEEE 754 conversion
- Supports GDS version 6.0 and 7.0

### 3. OASIS Support
- Magic byte validation (`%SEMI-OASIS\r\n`)
- START record parsing for version info

### 4. DRC Aggregation via Athena
- **Cell count distribution**: min, max, avg, P95
- **Bounding box outliers**: IQR (Interquartile Range) method
- **Naming convention violations**: hyphen detection, special character check
- **Invalid file count**: files that failed parsing

### 5. AI Design Review (Bedrock)
- Generates comprehensive design review in natural language
- Includes risk assessment (High/Medium/Low)
- Actionable recommendations per finding

## Deployment

Single CloudFormation template — deploy in minutes:

```bash
aws cloudformation deploy \
  --template-file semiconductor-eda/template.yaml \
  --stack-name fsxn-semiconductor-eda \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

## Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | Source storage (GDS/OASIS files) |
| S3 Access Points | Serverless data access |
| Step Functions | Workflow orchestration |
| Lambda (Python 3.13) | Compute |
| Glue Data Catalog | Schema for Athena |
| Amazon Athena | SQL analytics |
| Amazon Bedrock | AI report generation |
| SNS | Notifications |
| CloudWatch + X-Ray | Observability |

## What's Needed for Live Demo

1. FSx for NetApp ONTAP file system with S3 Access Point enabled
2. Sample GDS/OASIS files on the volume
3. VPC with private subnets (for Discovery Lambda)
4. Bedrock model access enabled (Nova Lite or Claude)

## Next Steps / Discussion Points

- DRC tool output format support (Calibre, Pegasus, ICV)
- Additional metadata fields for EDA workflows
- Integration with existing EDA tool chains
- Customer-facing demo planning
