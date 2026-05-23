# Dynamic FlexCache Render / EDA Workflow

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md)

## Overview

A workflow that dynamically creates ONTAP FlexCache volumes via REST API when rendering/EDA/simulation jobs are submitted, and automatically deletes them after job completion. Implements NVIDIA-style per-job cache management patterns using AWS Step Functions.

## Why Create FlexCache Per Job?

| Reason | Explanation |
|--------|-------------|
| Cost optimization | Storage costs only during job execution |
| Data isolation | Cache isolated per project/job |
| Security | No data remains after job completion |
| Operational simplicity | Prevents orphan volume accumulation |
| Performance optimization | Prepopulate only data needed for the job |

## Why Delete FlexCache After Job Completion?

- **Cost**: Avoid charges for unnecessary storage capacity
- **Security**: Prevent cache residue of sensitive data
- **Capacity management**: Prevent aggregate capacity exhaustion
- **Operations**: Prevent orphan volume accumulation

## Architecture

```
Job Request → Validate → Create FlexCache → Wait Ready → Prepopulate
    → Submit Job → Monitor Loop → Cleanup FlexCache → Report → Notify
```

## ONTAP REST API Operations

- FlexCache create: `POST /api/storage/flexcache/flexcaches`
- FlexCache delete: `DELETE /api/storage/flexcache/flexcaches/{uuid}`
- Job monitoring: `GET /api/cluster/jobs/{uuid}`
- Prepopulate: `PATCH /api/storage/flexcache/flexcaches/{uuid}`

## FSx for ONTAP S3 AP Role

- Data reads during job execution (via Lambda)
- Job result analysis and report generation
- Metadata extraction and quality checks

## Documentation

| Document | Description |
|----------|-------------|
| [Demo Guide](docs/demo-guide.md) | Job lifecycle demo |
| [Cost Optimization](docs/cost-optimization.md) | Cost analysis and optimization |
| [Failure Handling](docs/failure-handling.md) | Error recovery patterns |
| [ONTAP REST API Design](docs/ontap-rest-api-design.md) | API integration details |
| [PoC Checklist](docs/poc-checklist.md) | Proof of concept planning |
| [Security Design](docs/security-design.md) | Security considerations |
| [Workflow Design](docs/workflow-design.md) | Step Functions design |

## Success Metrics

| Metric | Target |
|--------|--------|
| FlexCache creation time | < 2 min |
| FlexCache deletion time | < 1 min |
| Job completion rate | > 95% |
| Orphan volume count | 0 |
| Cost per job (FlexCache overhead) | < $0.50 |
