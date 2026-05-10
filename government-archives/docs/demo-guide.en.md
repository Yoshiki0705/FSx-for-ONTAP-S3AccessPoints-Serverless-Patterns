# UC16 Demo Script (30-minute slot)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Prerequisites

- AWS account, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Deploy `government-archives/template-deploy.yaml` (with `OpenSearchMode=none` for cost reduction)

## Timeline

### 0:00 - 0:05 Intro (5 min)

- Use case: digitization of government/public records management
- Load from FOIA / information disclosure request statutory deadlines (20 business days)
- Challenge: PII detection and redaction takes several hours manually

### 0:05 - 0:10 Architecture (5 min)

- Combination of Textract + Comprehend + Bedrock
- 3 modes of OpenSearch (none / serverless / managed)
- Automatic management of NARA GRS retention periods

### 0:10 - 0:15 Deployment (5 min)

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 Execution (7 min)

```bash
# サンプル PDF（機密情報含む）アップロード
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

Check results:
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt` (raw text)
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json` (classification results)
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json` (PII detection)
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt` (redacted version)
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json` (sidecar)

### 0:22 - 0:27 FOIA Deadline Tracking (5 min)

```bash
# FOIA 請求登録
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 手動実行
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

Check SNS notification email.

### 0:27 - 0:30 Wrap-up (3 min)

- Path to enabling OpenSearch (full-scale search with `serverless`)
- GovCloud migration (FedRAMP High requirements)
- Next steps: interactive FOIA response generation with Bedrock agents

## FAQ

**Q. Can it support Japan's Information Disclosure Act (30 days)?**  
A. Yes, by modifying `REMINDER_DAYS_BEFORE` and the hardcoded 20 business days (US federal holidays → Japanese holidays).

**Q. Where is the original PII stored?**  
A. It is not stored anywhere. `pii-entities/*.json` contains only SHA-256 hashes, and `redaction-metadata/*.json` contains only hash + offset. Restoration requires re-execution from the original document.

**Q. How to reduce OpenSearch Serverless costs?**  
A. Minimum 2 OCU = approximately $350/month. Recommended to stop when not in production.
A. Skip with `OpenSearchMode=none`, or reduce to ~$25/month with `OpenSearchMode=managed` + `t3.small.search × 1`.

---

## About Output Destination: Selectable with OutputDestination (Pattern B)

UC16 government-archives now supports the `OutputDestination` parameter as of the 2026-05-11 update
(see `docs/output-destination-patterns.md`).

**Target workloads**: OCR text / document classification / PII detection / redaction / pre-OpenSearch documents

**Two modes**:

### STANDARD_S3 (default, traditional behavior)
Creates a new S3 bucket (`${AWS::StackName}-output-${AWS::AccountId}`) and
writes AI artifacts there. Only the Discovery Lambda manifest is written to the S3 Access Point
(as before).

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (other required parameters)
```

### FSXN_S3AP ("no data movement" pattern)
Writes OCR text, classification results, PII detection results, redacted documents, and redaction metadata
back to the **same FSx ONTAP volume** as the original documents via the FSxN S3 Access Point.
Public records staff can directly reference AI artifacts within the existing SMB/NFS directory structure.
No standard S3 bucket is created.

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (other required parameters)
```

**Read-back in chain structure**:

UC16 has a chain structure where downstream Lambdas read back artifacts from upstream stages (OCR → Classification →
EntityExtraction → Redaction → IndexGeneration), so `get_bytes/get_text/get_json` in `shared/output_writer.py`
read back from the same destination as the write destination.
This enables read-back from the FSxN S3 Access Point when `OutputDestination=FSXN_S3AP`,
allowing the entire chain to operate with a consistent destination.

**Notes**:

- Strongly recommend specifying `S3AccessPointName` (grant IAM permissions for both Alias and ARN formats)
- Objects over 5GB are not supported by FSxN S3AP (AWS specification), multipart upload required
- ComplianceCheck Lambda uses only DynamoDB and is not affected by `OutputDestination`
- FoiaDeadlineReminder Lambda uses only DynamoDB + SNS and is not affected
- OpenSearch index is managed separately by the `OpenSearchMode` parameter (independent of `OutputDestination`)
- For AWS specification constraints, see
  [the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
  and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)
