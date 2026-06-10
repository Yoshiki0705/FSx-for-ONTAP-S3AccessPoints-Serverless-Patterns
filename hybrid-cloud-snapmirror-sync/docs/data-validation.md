# Data Validation Before Consumption

This pattern treats replicated files on FSx for ONTAP as **raw replicated data**.
Before exposing the data to Amazon Quick / QuickSight or AI services, operators should validate data quality.

> **Scope note**: "Validated" in this pattern means that the dataset passed minimum freshness, schema, and usage-boundary checks for the demo or PoC. It does not imply full enterprise data quality certification. This validation layer is not intended to replace an enterprise data quality platform or transactional data lake.

> Reference: AWS provides an [official Glue ETL tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) showing how to read raw data from FSx via S3 Access Points, transform/validate it, and write curated output back to the same FSx volume.

## Data States

| State | Location | Description |
|-------|----------|-------------|
| Source of record | On-premises ONTAP | Authoritative business data |
| Raw replicated copy | FSx for ONTAP (post-SnapMirror) | Exact replica, not validated for consumption |
| Validated dataset | FSx for ONTAP (post-validation) | Passed freshness and quality checks |
| Consumption layer | Amazon Quick / QuickSight | Business-facing visualization and analysis |

## Minimum Validation Checks

Before data is consumed by Quick / QuickSight / Bedrock / AI services:

- [ ] `source_of_record_timestamp` exists and is parseable
- [ ] `replicated_at` timestamp exists
- [ ] Required columns or fields exist in the expected schema
- [ ] File count is within expected range (not zero, not anomalously high)
- [ ] Object size is not zero
- [ ] Schema version is recognized
- [ ] Data classification is assigned
- [ ] `dashboard_refreshed_at` is newer than `replicated_at`
- [ ] No duplicate records beyond tolerance
- [ ] Sensitive fields are identified and handled

## Validation Implementation Options

| Approach | When to use | AWS Service |
|----------|-------------|-------------|
| Lightweight (demo/PoC) | Small file count, simple schema | AWS Lambda triggered after SnapMirror complete |
| Medium (production PoC) | Schema validation, filtering | AWS Glue ETL job reading via S3 AP |
| Full (production) | Complex transformations, partitioning | AWS Glue + Glue Data Quality |

## Validated vs Raw in Feature Boundaries

| Area | This pattern provides | This pattern does not provide |
|------|----------------------|------------------------------|
| Data validation | Basic freshness and schema validation before consumption | Full transactional data lake management |
| Data quality | Demo-level validation checks | Enterprise-grade data quality framework |
| Curated output | Optional validated dataset on FSx | Mandatory data lake migration |
