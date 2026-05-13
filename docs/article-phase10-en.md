---
title: "FPolicy Event-Driven, Multi-Account StackSets, and Cost Optimization — FSx for ONTAP S3 Access Points, Phase 10"
published: false
description: Phase 10 implements ONTAP FPolicy event-driven pipelines, CloudFormation StackSets multi-account deployment, per-UC alarm profiles, and business-hours cost scheduling.
tags: aws, serverless, devops, fsxontap
canonical_url: null
cover_image: null
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 10** of the FSx for ONTAP S3 Access Points serverless pattern library. Building on [Phase 9](https://dev.to/yoshikifujiwara/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-587h), Phase 10 delivers:

- **FPolicy event-driven integration**: ONTAP FPolicy → SQS → EventBridge → Step Functions pipeline as an alternative to the missing S3AP native notifications (FR-2)
- **Multi-account StackSets**: All 17 UC templates achieve StackSets compatibility + new validator
- **Per-UC alarm profiles**: BATCH / REALTIME / HIGH_VOLUME profiles with automatic threshold configuration
- **Cost optimization**: Business-hours schedule switching + dynamic MaxConcurrency control

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## 1. FPolicy Event-Driven Architecture

### Background: Why FPolicy?

As confirmed in Phase 9, FSxN S3AP's `GetBucketNotificationConfiguration` remains "Not supported" (FR-2 unresolved). All 17 UCs operate on a polling model (EventBridge Scheduler → Discovery Lambda → ListObjectsV2).

ONTAP FPolicy is a framework that detects and notifies NFS/SMB file operations. In external server mode, it can integrate with AWS services to provide an alternative event-driven path.

This implementation is based on the proof-of-concept by NetApp colleague Shengyu Fang ([ontap-fpolicy-aws-integration](https://github.com/YhunerFSY/ontap-fpolicy-aws-integration)), adapted for this project's 17-UC pattern library.

### Architecture

```
FSx ONTAP SVM (file operations: create/write/delete/rename)
  │
  │ TCP (port 9898, async mode)
  ▼
FPolicy External Server (ECS Fargate)
  │
  ├─ [Near-real-time] → SQS Ingestion Queue → Bridge Lambda → EventBridge Custom Bus
  │                                                                    │
  │                                                          Per-UC EventBridge Rules
  │                                                                    │
  │                                                          Step Functions (per-UC)
  │
  └─ [Batch] → JSON Lines logs (FSxN S3AP) → Log Query Lambda → SQS → ...
```

### TriggerMode Parameter

All 17 UC templates now include a `TriggerMode` parameter:

| Value | Behavior |
|---|---|
| `POLLING` (default) | Existing EventBridge Scheduler + Discovery Lambda |
| `EVENT_DRIVEN` | FPolicy event-driven only |
| `HYBRID` | Both enabled + Idempotency Store for deduplication |

Default `POLLING` ensures zero impact on existing deployments.

### NFSv3 Write-Complete Issue

FPolicy events may arrive before file writes complete (especially with NFSv3). Mitigation: configurable delay (`WRITE_COMPLETE_DELAY_SEC`, default 5s) plus Step Functions retry logic.

---

## 2. Multi-Account StackSets Deployment

### StackSets Compatibility Validator

New validator `check_stacksets_compatibility.py` checks all 17 UC templates for:

1. Hardcoded Account IDs (12-digit numbers)
2. Resource name uniqueness (must include `${AWS::AccountId}` or `${AWS::StackName}`)
3. Export name collision potential
4. VPC/Subnet/SecurityGroup parameterization

Result: **All 17 UC templates pass with 0 errors, 0 warnings**.

### StackSets Execution Role

`shared/cfn/stacksets-execution.yaml` defines a least-privilege execution role with Organization ID conditional trust policy.

---

## 3. Per-UC Alarm Profiles

### Three Profiles

| Profile | Failure Threshold | Error Threshold | Target Workloads |
|---|---|---|---|
| BATCH | 10% | 3/hour | Periodic batch processing |
| REALTIME | 5% | 1/hour | Real-time processing with strict SLAs |
| HIGH_VOLUME | 15% | 5/hour | Large-scale file processing |

Each UC is assigned a default profile based on workload characteristics. `CUSTOM` profile allows individual threshold specification.

---

## 4. Cost Optimization

### Dynamic MaxConcurrency

`shared/max_concurrency_controller.py` calculates optimal parallelism based on detected file count and ONTAP API rate limits:

```python
optimal = min(detected_file_count, ontap_rate_limit // api_calls_per_file, upper_bound)
result = max(optimal, 1)
```

### Business-Hours Scheduling

With `EnableCostScheduling=true`, polling frequency automatically switches between business hours (rate(1 hour)) and off-hours (rate(6 hours)). Monthly cost savings estimate is emitted as a CloudWatch metric.

---

## 5. Verification Results

| Item | Result |
|---|---|
| Phase 10 new tests | 55 PASSED |
| Property-based tests (Hypothesis) | 7 properties × 100-200 iterations |
| 6 validators | All clean |
| Sensitive leaks | 0 |
| StackSets compatibility | 17/17 templates, 0 errors |

---

## 6. Next Phase Outlook

- **Phase 11 candidates**: FPolicy E2E AWS verification (ECS Fargate deployment + FSxN connectivity test)
- Migration to S3AP native notifications when FR-2 is resolved
- Cross-Account Observability live environment verification
- Athena result writing to FSxN S3AP (pending FR-1 resolution)
