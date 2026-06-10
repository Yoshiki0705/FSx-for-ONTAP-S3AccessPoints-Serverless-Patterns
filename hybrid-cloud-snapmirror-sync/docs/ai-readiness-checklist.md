# AI Readiness Checklist

Before using replicated FSx for ONTAP data for AI, BI, or natural language analysis, verify:

> **Important**: This pattern does not assume that replicated data is automatically AI-ready. It provides freshness, governance, and observability signals that help determine whether the data is ready.

## Readiness Levels

| Level | Criteria | Usage |
|-------|----------|-------|
| **Ready** | Freshness, governance, quality, and usage boundaries are all satisfied | Safe for BI dashboards, AI prompts, and automated summaries |
| **Needs review** | One or more checks are incomplete, but human-reviewed use may be acceptable | Acceptable for exploration with explicit caveats |
| **Not ready** | Freshness unknown, classification missing, owner missing, or high-impact use without review | Do not expose to business users or AI services |

## Freshness

- [ ] `source_of_record_timestamp` is available
- [ ] `replicated_at` is available
- [ ] `dashboard_refreshed_at` is available
- [ ] Data age is within the defined SLO (see `slo-design.md`)

## Governance

- [ ] Data classification is assigned (public / internal / confidential / restricted)
- [ ] Data owner is defined
- [ ] Allowed consumers are defined
- [ ] Sensitive fields are identified and masked or excluded
- [ ] Audit trail is enabled for data access

## Quality

- [ ] Required fields exist
- [ ] Schema version is known and compatible
- [ ] Empty files are excluded from analysis
- [ ] Duplicate records are handled or flagged
- [ ] Human review is required for high-impact AI-generated actions

## Usage Boundaries

- [ ] Data is clearly labeled as "replicated copy, not source of record"
- [ ] RPO limitations are documented and visible to AI consumers
- [ ] Results are not suitable for immediate automated transactional decisions
- [ ] Regulated decisions require additional compliance review
- [ ] AI-generated insights include provenance (which data, what timestamp)

## AI Service Integration Readiness

| AWS Service | FSx S3 AP Support | Notes |
|-------------|-------------------|-------|
| Amazon Quick / QuickSight | ✅ Via S3 data source | Natural language Q&A, dashboards |
| Amazon Bedrock Knowledge Bases | ✅ Via S3 data source | RAG over enterprise documents |
| Amazon Athena | ✅ Direct query | SQL analysis over file data |
| AWS Glue | ✅ ETL via S3 AP | Transform, validate, partition |
| Amazon SageMaker | ✅ Via S3 AP | Training data, batch inference |
| Amazon EMR Serverless | ✅ Spark via S3 AP | Large-scale analytics |

> Reference: [Using S3 Access Points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
