---
title: "FPolicy Event-Driven Pipeline, Multi-Account StackSets, and Cost Optimization — FSx for ONTAP S3 Access Points, Phase 10"
published: false
description: "Phase 10 implements ONTAP FPolicy event-driven pipeline (Fargate TCP server → SQS → EventBridge), CloudFormation StackSets multi-account deployment, UC-specific alarm profiles, and business-hours cost scheduling."
tags: aws, serverless, devops, fsxontap
canonical_url: null
cover_image: null
series: "FSx for ONTAP S3 Access Points"
---

## TL;DR

This is **Phase 10** of the FSx for ONTAP S3 Access Points serverless pattern library. Building on [Phase 9](https://dev.to/yoshikifujiwara/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-587h), Phase 10 delivers:

- **FPolicy event-driven integration**: ONTAP FPolicy → ECS Fargate TCP server → SQS → EventBridge → UC-specific targets. A working alternative to the still-unsupported S3AP native notifications (FR-2)
- **Multi-account StackSets**: All 17 UC templates validated for StackSets compatibility (0 errors) + admin/execution role templates
- **UC-specific alarm profiles**: BATCH / REALTIME / HIGH_VOLUME — three profiles with workload-appropriate thresholds
- **Cost optimization**: Dynamic MaxConcurrency controller + business-hours scheduling (rate(1h) vs rate(6h))
- **E2E verification**: NFSv3 ✅, NFSv4.0 ✅, NFSv4.1 ✅, SMB ✅, NFSv4.2 ❌ (unsupported by ONTAP FPolicy)

**In short**: Phase 9 completed the operational baseline. Phase 10 adds the event-driven path that the pattern library has needed since Phase 1 — without waiting for AWS to ship native S3AP notifications.

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

---

## 1. FPolicy Event-Driven Architecture

### Background: why FPolicy

Every UC in this pattern library runs on a polling model: EventBridge Scheduler → Discovery Lambda → ListObjectsV2. This works, but it means latency is bounded by the polling interval (typically 1 hour). AWS still does not support `GetBucketNotificationConfiguration` for S3 Access Points attached to FSx for ONTAP volumes (FR-2 remains open).

ONTAP FPolicy is a file-operation notification framework built into every ONTAP system. In external server mode, it sends TCP notifications for create/write/delete/rename events to a registered server. By connecting this to AWS services, we get near-real-time event-driven processing without waiting for FR-2.

This implementation builds on [Shengyu Fang's reference implementation](https://github.com/YhunerFSY/ontap-fpolicy-aws-integration), adapted for the 17-UC pattern library architecture.

### Architecture

```
FSx ONTAP SVM (file operations: create/write/delete/rename)
  │
  │ TCP (port 9898, async mode)
  ▼
FPolicy External Server (ECS Fargate, ARM64 Python 3.12)
  │
  ├─ [Near-real-time] → SQS Ingestion Queue
  │                        │
  │                        │ Event Source Mapping
  │                        ▼
  │                     Bridge Lambda → EventBridge Custom Bus
  │                                          │
  │                                   UC-specific Rules
  │                                          │
  │                                   Step Functions / Lambda (per-UC)
  │
  └─ [Batch] → JSON Lines log (FSxN S3AP) → Log Query Lambda
```

ONTAP initiates the TCP connection to the FPolicy server — not the other way around. This means the server simply listens on a port. Because ONTAP maintains a persistent TCP control channel with keep-alive, Lambda is not viable (15-minute timeout). ECS Fargate provides the long-running TCP listener without OS management overhead.

### Why not NLB?

Initial design placed an NLB in front of Fargate for IP stability. AWS verification revealed that ONTAP's FPolicy binary framing protocol (`"` + 4-byte big-endian length + `"` + payload) is incompatible with NLB TCP passthrough. The connection establishes but the handshake fails.

**Solution**: Fargate task direct IP connection. IP stability is handled by an EventBridge-triggered Lambda that updates the ONTAP external-engine configuration when the Fargate task IP changes:

```
ECS Task State Change (RUNNING) → EventBridge Rule → IP Updater Lambda
  → ONTAP REST API: disable policy → update engine primary_servers → enable policy
```

### TriggerMode parameter

All 17 UC templates now include a `TriggerMode` parameter:

| Value | Behavior |
|-------|----------|
| `POLLING` (default) | Existing EventBridge Scheduler + Discovery Lambda |
| `EVENT_DRIVEN` | FPolicy event-driven path only |
| `HYBRID` | Both paths active + Idempotency Store for deduplication |

Default `POLLING` ensures zero impact on existing deployments.

### NFSv3 write-complete delay

When FPolicy fires a notification, the file write may not be complete — particularly with NFSv3 which lacks close semantics. The server inserts a configurable delay (`WRITE_COMPLETE_DELAY_SEC`, default 5s) after receiving NOTI_REQ, and Step Functions include retry logic for incomplete files.

---

## 2. E2E Verification Results

### Protocol support matrix

| NFS Version | Mount Option | FPolicy NOTI_REQ | Result |
|-------------|-------------|------------------|--------|
| NFSv3 | `vers=3` | ✅ Immediate | Works |
| NFSv4.0 | `vers=4.0` | ✅ Immediate | Works |
| NFSv4.1 | `vers=4.1` | ✅ Immediate | Works |
| NFSv4.2 | `vers=4.2` | ❌ Not sent | Unsupported |
| NFSv4 (auto) | `vers=4` | ❌ Not sent | Negotiates to 4.2 |
| SMB/CIFS | — | ✅ | Works |

**Key finding**: `mount -o vers=4` on modern Linux negotiates to NFSv4.2, which ONTAP FPolicy does not support. Always use `vers=4.1` explicitly. This is documented in [NetApp's FPolicy Auditing FAQ](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing).

### Path extraction bug fix

ONTAP sends file paths in XML format within NOTI_REQ:

```xml
<PathNameType>WIN_NAME</PathNameType><PathName>\file.txt</PathName>
```

The initial regex extraction left residual XML tags in the `file_path` field. Fixed by adding an `_extract_xml_value()` helper with multi-tag fallback and residual tag stripping.

**Before fix**:
```json
{"file_path": "<PathNameType>WIN_NAME</PathNameType><PathName>\\file.txt</PathName>"}
```

**After fix**:
```json
{"file_path": "file.txt"}
```

### volume_name / svm_name resolution

ONTAP's NOTI_REQ body does not always include volume and SVM names in a parseable location. Resolution strategy:

1. Extract from NEGO_REQ session context (SVM name available at handshake)
2. Fall back to environment variables (`SVM_NAME`, `VOLUME_NAME`) set in the ECS task definition

### Complete E2E flow (verified)

```
NFSv3 file create (tee /mnt/fsxn/file.txt)
  → ONTAP FPolicy NOTI_REQ
    → Fargate FPolicy Server receives event
      → SQS SendMessage
        → Bridge Lambda → EventBridge Custom Bus
```

**Actual EventBridge event**:
```json
{
  "detail-type": "FPolicy File Operation",
  "source": "fsxn.fpolicy",
  "detail": {
    "event_id": "2175e878-1e0c-48ef-a8b3-53664d5d5b06",
    "operation_type": "create",
    "file_path": "test-eb-e2e-1778707951.txt",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-05-13T21:32:37.680626+00:00",
    "client_ip": "10.0.10.67"
  }
}
```

---

## 3. Unified UC Directory Structure

Phase 10 introduces `event-driven-fpolicy/` as a first-class UC directory with the same structure as all other UCs:

```
event-driven-fpolicy/
├── docs/                    # 8 languages (ja, en, ko, zh-CN, zh-TW, fr, de, es)
│   ├── architecture.md      # + .en.md, .ko.md, etc.
│   └── demo-guide.md
├── functions/
│   ├── ip_updater/          # Fargate IP → ONTAP REST API
│   └── sqs_to_eventbridge/  # Bridge Lambda
├── schemas/
│   └── fpolicy-event-schema.json
├── server/
│   ├── Dockerfile           # ARM64 Python 3.12
│   ├── fpolicy_server.py    # TCP listener + SQS sender
│   └── requirements.txt
├── tests/
├── README.md                # + 7 language variants
├── template.yaml            # Fargate deployment (ComputeType=fargate)
└── template-ec2.yaml        # EC2 deployment (ComputeType=ec2)
```

A single `template.yaml` with a `ComputeType` parameter (fargate/ec2) uses CloudFormation Conditions to select the appropriate resource set. The EC2 variant uses a t4g.micro with a static private IP — no NLB needed, no IP update Lambda needed — at ~$4/month vs ~$26/month for Fargate+NLB.

---

## 4. Multi-Account StackSets

### StackSets compatibility validator

New validator `scripts/check_stacksets_compatibility.py` checks all 17 UC templates for:

1. **Hardcoded Account IDs** — 12-digit numeric strings that would break in other accounts
2. **Resource name uniqueness** — names must include `!Sub` with AccountId or StackName
3. **Export name collisions** — exports that would conflict across accounts
4. **VPC/Subnet/SecurityGroup parameterization** — must not be hardcoded

**Result: 17/17 templates, 0 errors, 0 warnings.**

### StackSets role templates

| Template | Purpose |
|----------|---------|
| `shared/cfn/stacksets-admin.yaml` | Admin account role for StackSet management |
| `shared/cfn/stacksets-execution.yaml` | Target account execution role (least-privilege) |

The execution role uses an Organization ID condition in its trust policy — accounts outside the Organization cannot assume it. Permissions are scoped to Lambda, Step Functions, DynamoDB, S3, CloudWatch, EventBridge, SNS, and Secrets Manager only.

### Automatic deployment

With `AutoDeployment: Enabled` on the StackSet, new accounts joining the Organization automatically receive the UC templates. No manual intervention required.

---

## 5. Alarm Profiles and Cost Optimization

### UC-specific alarm profiles

Not all UCs have the same latency requirements. A batch genomics pipeline (UC3) tolerates higher failure rates than a real-time compliance monitor (UC12). Phase 10 introduces three profiles:

| Profile | Failure Rate Threshold | Error Threshold | Target Workloads |
|---------|----------------------|-----------------|------------------|
| BATCH | 10% | 3/hour | Periodic batch processing (UC1-5, UC9) |
| REALTIME | 5% | 1/hour | Real-time processing (UC10-14) |
| HIGH_VOLUME | 15% | 5/hour | High-volume file processing (UC6-8, UC15-17) |

Each UC template now has an `AlarmProfile` parameter (BATCH / REALTIME / HIGH_VOLUME / CUSTOM). The `CUSTOM` option exposes `CustomFailureThreshold` and `CustomErrorThreshold` for fine-grained control.

### Dynamic MaxConcurrency controller

`shared/max_concurrency_controller.py` calculates optimal Map state parallelism based on actual file volume:

```python
def calculate_max_concurrency(
    detected_file_count: int,
    ontap_rate_limit: int = 100,
    api_calls_per_file: int = 3,
    upper_bound: int = 40
) -> int:
    optimal = min(
        detected_file_count,
        ontap_rate_limit // api_calls_per_file,
        upper_bound
    )
    return max(optimal, 1)
```

This replaces the static `MaxConcurrency: 10` from Phase 8. For 500 files with default settings, it calculates `min(500, 33, 40) = 33` — a 3.3x throughput improvement without exceeding ONTAP's rate limit.

### Business-hours cost scheduling

With `EnableCostScheduling=true`, two EventBridge Schedulers dynamically adjust the polling frequency:

| Time Period | Schedule |
|-------------|----------|
| Business hours (weekday 09:00-18:00 JST) | `rate(1 hour)` |
| Off-hours (weekday 18:00-09:00 + weekends) | `rate(6 hours)` |

`BusinessHoursStart` and `BusinessHoursEnd` parameters allow customization. The Cost Scheduler emits an `EstimatedMonthlySavings` CloudWatch metric for visibility.

---

## 6. Test Results

| Category | Count | Result |
|----------|-------|--------|
| Phase 10 new tests | 62 | All PASS ✅ |
| Property-based tests (Hypothesis) | 7 properties × 100-200 iterations | All PASS ✅ |
| Existing tests (Phase 1-9) | 982 | No regressions ✅ |
| **Total** | **1044+** | **All PASS** |

### Property-based tests

| Property | What it verifies |
|----------|-----------------|
| FPolicy event round-trip | Serialize → deserialize produces equivalent object |
| MaxConcurrency bounds | Result always ≥ 1 and ≤ upper_bound |
| MaxConcurrency correctness | Result matches the min() formula |
| Zero files → 1 | Empty input never produces 0 |
| StackSets Account ID detection | Known violations are always caught |
| Cost savings non-negativity | Estimated savings ≥ 0 for all inputs |
| Same rate → ~0 savings | Equal business/off-hours rates produce near-zero savings |

### Validator results

| Validator | Result |
|-----------|--------|
| `check_s3ap_iam_patterns.py` | 17/17 clean ✅ |
| `check_handler_names.py` | 87 handlers, 0 issues ✅ |
| `check_conditional_refs.py` | 17 templates, 0 issues ✅ |
| `check_stacksets_compatibility.py` | 17 templates, 0 errors ✅ |
| `_check_sensitive_leaks.py` | 160 images, 0 leaks ✅ |
| cfn-guard IAM security | Advisory, 0 new violations ✅ |

---

## 7. Deployment Learnings

Several issues surfaced during AWS verification that are worth documenting:

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| NLB incompatible with FPolicy | Binary framing protocol not passed through | Direct Fargate IP connection |
| jsonschema 4.18+ fails on ARM64 Lambda | rpds-py native dependency | Pin to 4.17.x |
| SCHEMA_PATH differs between Lambda and local | Different working directories | Fallback path resolution |
| Guard Hook rejects Condition-based `Resource: "*"` | Overly strict rule | Updated rule to allow `Condition exists` |
| ECR pull fails in private subnet | Missing VPC Endpoints | Added ECR, STS, S3, Logs, SQS endpoints |
| KEEP_ALIVE timeout race | Server timeout = keep_alive_interval | Increased to 300s |
| NFSv4 events not firing | `vers=4` negotiates to unsupported 4.2 | Explicit `vers=4.1` |

---

## 8. Next Phase Outlook

Phase 10 established the event-driven pipeline. Phase 11 candidates:

1. **TriggerMode integration with all 17 UCs**: Wire FPolicy events to UC-specific Step Functions dispatch rules
2. **FPolicy → UC-specific Step Functions dispatch**: EventBridge rules matching file path prefixes to UC targets
3. **protobuf format evaluation**: ONTAP 9.15.1+ supports protobuf for higher-performance notifications
4. **Cross-Account Observability live verification**: Deploy the shared-services-observability template and validate metric aggregation
5. **Persistent Store**: For compliance-sensitive environments that cannot tolerate event loss during Fargate task restarts
6. **FR-2 migration path**: When AWS ships native S3AP notifications, the TriggerMode parameter provides a clean migration — switch from `EVENT_DRIVEN` to native events without changing UC logic

---

## Who should care about Phase 10?

- **Platform teams** get an event-driven alternative to polling — sub-minute latency instead of hourly intervals
- **Security teams** get StackSets compatibility validation ensuring no hardcoded account IDs leak across environments
- **Operations teams** get workload-appropriate alarm thresholds that reduce alert fatigue
- **Finance teams** get business-hours scheduling that cuts off-hours Lambda costs by ~80%
- **Storage teams** get a documented FPolicy integration pattern with protocol-level verification results
- **Multi-account teams** get ready-to-deploy StackSets admin/execution roles with Organization-scoped trust

---

## Conclusion

Phase 10 solves the problem that has been deferred since Phase 1: how do you get event-driven processing from FSx for ONTAP when S3AP native notifications don't exist?

The answer is ONTAP FPolicy — a mature notification framework that predates S3 Access Points by over a decade. By connecting it to ECS Fargate → SQS → EventBridge, the pattern library now supports both polling and event-driven modes through a single `TriggerMode` parameter. The default remains `POLLING`, so existing deployments are unaffected.

The E2E verification confirmed that NFSv3, NFSv4.0, NFSv4.1, and SMB all work. NFSv4.2 does not — and the most common failure mode is `mount -o vers=4` silently negotiating to 4.2. This is now documented and the setup guide recommends explicit version pinning.

Beyond FPolicy, Phase 10 matures the operational model: StackSets for multi-account deployment, alarm profiles for workload-appropriate monitoring, and cost scheduling for environments that don't need 24/7 polling. Combined with the 6-validator CI pipeline and 1044+ passing tests, the pattern library is ready for production multi-account deployment.

---

**Repository**: [github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**Previous phases**: [Phase 1](https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili) · [Phase 7](https://dev.to/yoshikifujiwara/public-sector-use-cases-unified-output-destination-and-a-localization-batch-fsx-for-ontap-s3-2hmo) · [Phase 8](https://dev.to/yoshikifujiwara/operational-hardening-ci-grade-validation-and-pattern-c-b-hybrid-fsx-for-ontap-s3-access-587h) · [Phase 9](https://dev.to/yoshikifujiwara/production-rollout-vpc-endpoint-auto-detection-and-the-cdk-no-go-fsx-for-ontap-s3-access-587h)
