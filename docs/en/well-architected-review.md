# Well-Architected Framework — Self-Review

> 🌐 **Language / 言語**: [日本語](../ja/well-architected-review.md) | English

> Portal architecture assessment against the six pillars of AWS Well-Architected.

> **How to read the scores**: this is a **self-assessment**, not a reviewed one. No
> AWS Well-Architected Framework Review has been conducted with a third party. Each
> star rating is the author's summary of the practice table under the same heading,
> which is where the checkable content is: implemented, partial, or absent.
> Read the tables and disregard the stars if they disagree.
>
> **Assessed**: 2026-08-07, against the sandbox configuration.
> Rated for a PoC or evaluation deployment; a production deployment that has worked
> through the production checklist would score differently on Security and Reliability.

## Summary Scores

| Pillar | Score | Key Trade-off |
|--------|:---:|---------------|
| Operational Excellence | ⭐⭐⭐⭐ | DemoMode enables rapid iteration; production needs monitoring |
| Security | ⭐⭐⭐⭐ | AppSync auth + Cognito groups; production needs WAF + SCP |
| Reliability | ⭐⭐⭐ | FSx for ONTAP can be multi-AZ; the portal's Lambda sits in one subnet |
| Performance Efficiency | ⭐⭐⭐⭐ | ARM64 Lambda + S3 AP direct access; VPC Cold Start is trade-off |
| Cost Optimization | ⭐⭐⭐⭐ | Portal components are serverless and pay-per-use; the storage layer is not |
| Sustainability | ⭐⭐⭐⭐ | ARM64 (Graviton), no idle resources, data-local processing |

## Pillar Details

### Operational Excellence

| Practice | Status | Notes |
|----------|:---:|-------|
| IaC (CDK/Amplify Gen2) | ✅ | Reproducible deploys via `npm start` |
| Observability (logs) | ✅ | CloudWatch Logs, structured logging |
| Observability (metrics) | ⚠️ | No custom CloudWatch metrics yet |
| Observability (traces) | ⚠️ | X-Ray not enabled (add via backend.ts) |
| Runbook | ✅ | GETTING-STARTED.md + troubleshooting |
| Feature flags | ⚠️ | DemoMode only; no per-feature toggles |

### Security

| Practice | Status | Notes |
|----------|:---:|-------|
| Authentication | ✅ | Cognito User Pool + optional External IdP |
| Authorization | ✅ | AppSync schema-level (group-based) |
| Encryption at rest | ✅ | FSx for ONTAP KMS + S3 SSE |
| Encryption in transit | ✅ | HTTPS (AppSync/S3 AP) + optional SMB 3.0 |
| Secrets management | ✅ | Secrets Manager for ONTAP credentials |
| IAM least privilege | ⚠️ | `resources: ["*"]` in sandbox; production guide provided |
| WAF | ❌ | Not configured (production checklist item) |
| VPC security groups | ⚠️ | The FSx for ONTAP SG is shared in sandbox; the production guide recommends separation |

### Reliability

| Practice | Status | Notes |
|----------|:---:|-------|
| Multi-AZ | ⚠️ | The portal's VPC Lambda is attached to one subnet, so it fails with that AZ. FSx for ONTAP itself can be deployed multi-AZ, and is in this configuration; the two are independent choices |
| Retry/backoff | ✅ | Step Functions with Retry/Catch |
| Health checks | ⚠️ | No explicit health endpoint |
| Disaster recovery | ✅ | SnapMirror + FlexClone for data; stack re-deploy for infra |
| Graceful degradation | ✅ | DemoMode pattern; ONTAP disconnected = file browsing still works |

### Performance Efficiency

| Practice | Status | Notes |
|----------|:---:|-------|
| Right-sized compute | ✅ | Lambda ARM64, 256MB (right for ONTAP REST calls) |
| Caching | ⚠️ | No AppSync caching; ONTAP FlexCache for read acceleration |
| Async processing | ✅ | Step Functions for AI workloads |
| Direct integration | ✅ | AppSync → Step Functions (no middleware Lambda) |

### Cost Optimization

| Practice | Status | Notes |
|----------|:---:|-------|
| Serverless | ✅ | Zero cost when idle for the portal's own components (Lambda/AppSync/DynamoDB) |
| Free Tier utilization | ⚠️ | Lambda and DynamoDB free tiers are perpetual; AppSync's is 12 months. FSx for ONTAP has no free tier and runs continuously (~$194/month at 128 MBps) |
| Right-sized AI models | ✅ | Nova Lite for cost; Claude for accuracy (configurable) |
| No over-provisioning | ✅ | No EC2, no NAT Gateway required |

### Sustainability

| Practice | Status | Notes |
|----------|:---:|-------|
| Graviton (ARM64) | ✅ | All Lambda functions on ARM64 |
| Data locality | ✅ | Process data in same region as storage (no cross-region) |
| Efficient protocols | ✅ | S3 AP avoids data copy (zero-copy access to NAS) |
| Minimize idle resources | ✅ | Serverless = no idle compute |

## Improvement Roadmap

1. **Short-term**: Add X-Ray tracing, custom CloudWatch metrics, WAF
2. **Medium-term**: Multi-AZ Lambda subnets, AppSync caching, health endpoint
3. **Long-term**: Multi-region DR with SnapMirror, feature flags via AppConfig
