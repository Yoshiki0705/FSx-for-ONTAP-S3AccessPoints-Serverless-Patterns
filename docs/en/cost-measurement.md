# Cost Measurement — Sandbox Actual Costs

> 🌐 **Language / 言語**: [日本語](../ja/cost-measurement.md) | English

> Methodology for measuring real costs from AWS Cost Explorer after running the portal sandbox.

## How to Measure

After running `npm start` for a representative period (1 week recommended):

```bash
# Get costs for the sandbox stack (last 7 days)
aws ce get-cost-and-usage \
  --time-period Start=$(date -v-7d +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --filter '{
    "Tags": {
      "Key": "aws:cloudformation:stack-name",
      "Values": ["amplify-fsxns3apamplifyportal-dev1-sandbox-0123456789"]
    }
  }' \
  --group-by Type=DIMENSION,Key=SERVICE
```

## Expected Cost Breakdown (Sandbox, Light Usage)

| Service | Monthly Estimate | Notes |
|---------|-----------------|-------|
| AWS AppSync | $0-4 | Free Tier: 250K queries/month |
| Amazon Cognito | $0 | Free Tier: 50K MAU |
| AWS Lambda | $0-2 | Free Tier: 1M requests/month |
| Amazon DynamoDB | $0 | Free Tier: 25GB + 25 WCU/RCU |
| AWS Secrets Manager | $0.40 | $0.40/secret/month |
| VPC (ENI hours) | $0 | No additional cost for Lambda ENI |
| CloudWatch Logs | $0-1 | 5GB ingestion free |
| **Total (Free Tier active)** | **~$1-5** | |
| **Total (post-Free Tier)** | **~$25-60** | Depends on usage volume |

## Post-Free Tier Estimates

After 12 months, without Free Tier:

| Usage Level | Monthly Cost | Profile |
|------------|-------------|---------|
| Light (10 users, 100 requests/day) | ~$25 | PoC/evaluation |
| Medium (50 users, 1000 requests/day) | ~$45 | Team deployment |
| Heavy (200 users, 5000 requests/day) | ~$80 | Department-wide |

Key cost drivers post-Free Tier:
- AppSync: $4.00 per million Query/Mutation operations
- Cognito: $0.0055 per monthly active user
- Lambda: $0.20 per million requests + $0.0000166667 per GB-second
- DynamoDB: $1.25 per WCU, $0.25 per RCU (on-demand)

## Per-Operation Cost Breakdown

For FinOps teams who need unit economics:

| Operation | Components | Arithmetic | Cost per invocation |
|-----------|-----------|-----------|--------------------|
| Browse 1 folder (ListObjectsV2) | Lambda (128MB, 200ms) + AppSync | 0.025 GB-s × $0.0000166667 + $0.000004 | ~$0.0000044 |
| AI process 1 PDF (Bedrock Nova Lite) | Lambda (256MB, 3s) + Bedrock (1K input + 500 output tokens) | 1 × $0.00006 + 0.5 × $0.00024 + 0.75 GB-s × $0.0000166667 | ~$0.0002 |
| AI process 1 PDF (Claude 3.5 Haiku) | Lambda (256MB, 5s) + Bedrock (1K in + 500 out) | 1 × $0.0008 + 0.5 × $0.004 + 1.25 GB-s × $0.0000166667 | ~$0.0028 |
| Lock 1 snapshot (ONTAP REST) | Lambda (256MB, 1s) + AppSync | 0.25 GB-s × $0.0000166667 + $0.000004 | ~$0.0000082 |
| Rekognition (1 image) | Lambda + Rekognition image API | $0.001/image (first 1M/month) | ~$0.001 |
| Textract, text only (1 page) | Lambda + `DetectDocumentText` | $0.0015/page (first 1M) | ~$0.0015 |
| Textract, tables and forms (1 page) | Lambda + `AnalyzeDocument` with `TABLES`,`FORMS` | $0.07/page (first 1M) | ~$0.07 |
| Athena query (10MB scanned) | Lambda + Athena | 10MB minimum × $5/TB | ~$0.00005 |

> **Rates**: us-east-1, on-demand, retrieved from the AWS Price List API on 2026-08-07.
> Lambda $0.0000166667/GB-s, AppSync $0.000004/request. ap-northeast-1 differs slightly;
> re-check before quoting a figure to anyone.
>
> **Nova Lite is the cheaper model, by an order of magnitude.** Nova Lite is
> $0.06/$0.24 per million input/output tokens against Claude 3.5 Haiku's
> $0.80/$4.00 — roughly 13× on input and 17× on output. An earlier version of this
> table had the two the wrong way round.
>
> **The two Textract rows differ by ~47×.** The portal calls `analyze_document`
> with `TABLES` and `FORMS` in analyze mode and `detect_document_text` otherwise
> (`functions/textract/index.py`), so which row applies depends on the mode the
> caller picked.
>
> These remain estimates: real cost tracks file size, token count and duration.

**Example**: 1,000 contract PDFs with Bedrock Nova Lite, at the token counts above:
- 1,000 × $0.0002 = **$0.20** for one batch
- Five such batches a month = **$1.00/month** for the AI processing alone

At these rates the AI processing is not what drives the bill. The infrastructure below is.

## FSx for ONTAP Infrastructure Cost (Separate)

The portal's cost is additive to FSx for ONTAP infrastructure:
- FSx for ONTAP (128 MBps, single-AZ): ~$194/month
- S3 Access Point: No additional cost (included with FSx for ONTAP)
- Data transfer (intra-region): $0.01/GB

> Note: FSx for ONTAP is shared infrastructure — its cost is amortized across all workloads using the same file system (NFS/SMB clients + S3 AP + this portal).
