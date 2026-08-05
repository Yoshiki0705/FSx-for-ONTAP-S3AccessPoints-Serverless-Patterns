# OPS3: Tiering Optimizer

🌐 **Language / 言語**: [日本語](README.md) | English

---

## Overview

Analyzes FSx for ONTAP volume tiering policies and recommends optimal
FabricPool configuration (policy + cooling period) with cost savings estimates.

**References**:
- [Volume data tiering (AWS Docs)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-data-tiering.html)
- [Best practices for enterprise deployments](https://docs.aws.amazon.com/prescriptive-guidance/latest/fsx-ontap-enterprise-deployment/best-practices.html)
- [How a customer reduced storage TCO by 28%](https://aws.amazon.com/blogs/storage/how-a-customer-reduced-storage-tco-by-28-with-amazon-fsx-for-netapp-ontap/)

## Recommendation Logic

| Current Policy | Condition | Recommendation |
|:--------------:|-----------|----------------|
| `none` | — | Change to `auto` (31-day cooling) |
| `snapshot-only` | Capacity Pool > 50 GB | Upgrade to `auto` |
| `auto` | cooling > 14 days & Pool > 100 GB | Reduce cooling to 14 days |
| `all` | — | No recommendation (max tiering) |

## Cost Estimate

| Tier | Price (ap-northeast-1) |
|------|:----------------------:|
| SSD | ~$0.125/GB/month |
| Capacity Pool | ~$0.021/GB/month |
| **Savings** | **~$0.104/GB/month** |

## Output

### CloudWatch custom metrics (namespace: `FSxOps`)

| Metric | Unit | Meaning |
|--------|:----:|---------|
| `TieringPotentialSavingsUSD` | None | Estimated monthly saving from a policy change |
| `TieringRecommendationCount` | Count | Number of recommendations produced |

### S3 report

Carries a `data_classification` field (default `INTERNAL`, overridable via the
`DATA_CLASSIFICATION` environment variable).

## Success Metrics

| Outcome | Metric | Target | Human Review |
|---------|--------|--------|:------------:|
| Cold data tiered | Share of capacity on the Capacity Pool tier | Trending up | ✅ |
| Cost reduction | Realised share of `TieringPotentialSavingsUSD` | 70% or more of the estimate | ✅ |
| Policy coverage | Volumes still on policy `none` | 0 | ✅ |
| Execution stability | Workflow success rate | > 99% | — |
| Latency impact | Read latency after tiering | Within business requirements | ✅ |

> **What the estimate is**: the saving is calculated from the unit prices supplied
> as template parameters and the current Capacity Pool footprint. It is not an AWS
> billing figure, and the volume actually tiered depends on access patterns and the
> cooling period, so the outcome will differ from the estimate.

## Testing

```bash
python3 -m pytest operations/tiering-optimizer/tests/ -v
```

## Governance Note

Tiering policy changes are reversible, but changing to policy=all moves all user
data to the capacity pool tier, increasing read latency to tens of milliseconds.
Test in non-production before applying to production workloads.
