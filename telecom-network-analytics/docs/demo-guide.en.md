# Telecom Network Analytics — CDR/Network Log Anomaly Detection Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

This demo demonstrates the automated CDR (Call Detail Records) and network equipment log analysis pipeline. Athena-based traffic statistics and Bedrock-based anomaly detection enable early detection of network failures and automated compliance reporting.

**Core Message**: AI automatically analyzes CDR/network logs, detects anomalies in real-time, and generates daily reports.

**Estimated Duration**: 3–5 minutes

---

## Step-by-Step Deployment & Validation

### Step 1: Prerequisites Check

```bash
aws --version          # v2.x required
sam --version          # 1.x or later
python3 --version      # 3.9 or later
aws sts get-caller-identity
```

### Step 2: Clone Repository

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Step 3: Prepare Sample Data

Place sample data on FSx for ONTAP volume:

```
/cdr/
  2026/06/02/morning.csv       # CDR file (CSV format)
  2026/06/02/afternoon.csv
  2026/06/02/evening.parquet   # CDR file (Parquet format)
/syslog/
  2026/06/02/router01.log      # Syslog RFC 5424 format
  2026/06/02/switch01.log
```

### Step 4: Deploy

```bash
sam build

sam deploy \
  --stack-name fsxn-telecom-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    CdrSuffixFilter=".csv,.asn1,.parquet" \
    AnomalyThresholdStdDev=3 \
    CapacityThresholdPercent=80 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: Verify Deployment

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1
```

### Step 6: Execute Workflow Manually

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 \
  --query "executionArn" \
  --output text)
```

### Step 7: Monitor Execution

```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN \
  --query "status" \
  --region ap-northeast-1
```

### Step 8: Verify Outputs

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/ --region ap-northeast-1
```

---

## Validation Checklist

| Check Item | Verification Method | Expected Result |
|-----------|-------------------|-----------------|
| CDR file detection | Step Functions execution log | Discovery step returns CDR file count |
| Athena traffic stats | S3 output bucket | `cdr-stats.json` generated |
| Syslog parsing | Step Functions execution log | Log Analyzer step completed |
| Anomaly detection | `anomalies.json` review | Flagged anomaly records present (depends on test data) |
| Daily report | S3 bucket | `network-health.json` exists in `reports/daily/{today}/` |
| SNS alert | Email check | Notification email received (only if critical anomalies exist) |

---

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|-----------|
| Discovery Lambda timeout | S3 AP access failure from VPC | Check NetworkOrigin setting. Internet Origin AP requires VPC-external execution or NAT Gateway |
| CDR parse error | Unexpected file format | Check `CdrSuffixFilter` parameter. Detailed errors in `errors/cdr/` |
| Athena query failure | Workgroup misconfiguration | Check Athena workgroup and query result bucket |
| Bedrock invocation failure | Model access not enabled | Enable model access in Bedrock console |
| `AccessDenied` on S3 AP | Incorrect IAM policy ARN format | Use `arn:aws:s3:{region}:{account}:accesspoint/{name}` format |

---

---

## Screenshots

![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)


## Cleanup

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1

aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1
```
