# Cost Measurement — Sandbox Actual Costs

> 🌐 Language: **English** | [日本語](../ja/cost-measurement.md)

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

| Operation | Components | Cost per Invocation |
|-----------|-----------|--------------------|
| Browse 1 folder (ListObjectsV2) | Lambda (128MB, 200ms) + AppSync | ~$0.0000034 |
| AI process 1 PDF (Bedrock Nova Lite) | Lambda (256MB, 3s) + Bedrock (1K input + 500 output tokens) | ~$0.005 |
| AI process 1 PDF (Claude 3.5 Haiku) | Lambda (256MB, 5s) + Bedrock (1K in + 500 out) | ~$0.002 |
| Lock 1 snapshot (ONTAP REST) | Lambda (256MB, 1s) + AppSync | ~$0.0000084 |
| Rekognition (1 image) | Lambda + Rekognition DetectLabels | ~$0.001 |
| Textract (1 page) | Lambda + Textract AnalyzeDocument | ~$0.0015 |
| Athena query (10MB scanned) | Lambda + Athena | ~$0.00005 |

> Calculation: Lambda @ $0.0000166667/GB-s + AppSync @ $0.000004/request + Bedrock/AI per-token pricing.
> These are estimates. Actual costs depend on file size, token count, and processing time.

**Example**: Processing 1,000 contract PDFs with Bedrock Nova Lite:
- 1,000 × $0.005 = **$5.00** (one-time batch)
- Same volume monthly (5 batches) = **$25.00/month** for AI processing alone

## FSx for ONTAP Infrastructure Cost (Separate)

The portal's cost is additive to FSx for ONTAP infrastructure:
- FSx for ONTAP (128 MBps, single-AZ): ~$194/month
- S3 Access Point: No additional cost (included with FSx for ONTAP)
- Data transfer (intra-region): $0.01/GB

> Note: FSx for ONTAP is shared infrastructure — its cost is amortized across all workloads using the same file system (NFS/SMB clients + S3 AP + this portal).
