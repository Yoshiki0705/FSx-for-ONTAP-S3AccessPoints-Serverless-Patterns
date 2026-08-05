# OPS5: Cost Optimization

🌐 **Language / 言語**: [日本語](README.md) | English

## Overview

Decomposes FSx for ONTAP cost structure, provides unit economics ($/GB),
growth projection, top cost driver analysis, and AI recommendations.

**Cost components**: SSD capacity + Capacity Pool + Throughput + Backup

## Output

### CloudWatch custom metrics (namespace: `FSxOps`)

| Metric | Unit | Meaning |
|--------|:----:|---------|
| `MonthlyTotalCostUSD` | None | Monthly total across the cost components |
| `CostPerGBUSD` | None | Unit economics ($/GB/month) |
| `ProjectedCost` | None | Three-month outlook with the growth rate applied |

### S3 report

Carries a `data_classification` field (default `INTERNAL`, overridable via the
`DATA_CLASSIFICATION` environment variable).

## Success Metrics

| Outcome | Metric | Target | Human Review |
|---------|--------|--------|:------------:|
| Cost structure visibility | Share of components with a retrievable breakdown | 100% | — |
| Unit economics tracking | Trend of `CostPerGBUSD` | Not increasing | ✅ |
| Early budget-overrun signal | Gap between projection and actuals | Within 20% | ✅ |
| Reduction opportunities | Top cost drivers identified | At least 1 | ✅ |
| Execution stability | Workflow success rate | > 99% | — |

> **What the projection is**: the three-month figure applies a **fixed 5% monthly
> growth rate** as a baseline and compounds it (`functions/analyze/handler.py`). It
> is not derived from measured growth, so it is useful for direction but not as a
> basis for budgeting. Replace the rate with your own measured growth.

## Testing

```bash
python3 -m pytest operations/cost-optimization/tests/ -v
make test-ops5
```

## Governance Note

This pattern **reads and estimates only**. It does not modify or purchase
resources.

The figures are **not AWS billing data**. They are estimates produced by applying
unit prices to the capacity and throughput configuration read from ONTAP. Actual
charges differ with region, discount agreements, Savings Plans, data transfer and
other service usage. **Reconcile against AWS Cost Explorer and your invoice.**

Unit prices are supplied as template parameters, so they do not follow AWS price
changes automatically. Review them periodically.

> **Financial note**: the output is a technical view of cost composition, not
> financial advice or a budget commitment. Route procurement and budget decisions
> through your finance function.
