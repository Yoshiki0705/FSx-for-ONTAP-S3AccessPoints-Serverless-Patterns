# Cost Measurement — Sandbox Actual Costs

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
      "Values": ["amplify-fsxns3apamplifyportal-yoshiki-sandbox-ae70db2b34"]
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

## FSx for ONTAP Infrastructure Cost (Separate)

The portal's cost is additive to FSx for ONTAP infrastructure:
- FSx for ONTAP (128 MBps, single-AZ): ~$194/month
- S3 Access Point: No additional cost (included with FSx for ONTAP)
- Data transfer (intra-region): $0.01/GB

> Note: FSx for ONTAP is shared infrastructure — its cost is amortized across all workloads using the same file system (NFS/SMB clients + S3 AP + this portal).
