# Why Native S3 AP Notifications Still Matter

🌐 **Language / 言語**: [日本語](native-s3ap-notifications-evidence.md) | English

## Overview

This document sets out the case for native event notifications on FSx for ONTAP S3 Access Points, based on evidence gathered from implementing and operating an FPolicy-based alternative.

> **Framing**: Our FPolicy-based event-driven pattern is a *proven, working workaround*. But it carries operational costs that a native capability would eliminate. The purpose here is to quantify those costs so they can be used as feedback to the AWS service team.

## Customer Problem (Working Backwards)

### Hypothetical Press Release

> "Amazon FSx for ONTAP S3 Access Points now support native event notifications to Amazon EventBridge. Customers can detect file changes in real time and trigger serverless workflows without operating an FPolicy server."

### Customer Problem Statement

Enterprise customers want to build change-detection-to-automatic-processing pipelines over file data stored on FSx for ONTAP. Because S3 Access Points do not support `GetBucketNotificationConfiguration`, only two options exist today:

1. **Polling**: periodic scans via EventBridge Scheduler + `ListObjectsV2` (no real-time behaviour)
2. **FPolicy**: operate an ONTAP-native FPolicy External Server yourself (high operational complexity)

Neither resembles the native S3 experience of "just configure EventBridge on the bucket".

## Operational Issues Revealed by Our FPolicy Implementation

### Issue 1: Operating a long-running TCP listener

| Item | Today (FPolicy) | With native notifications |
|------|-----------------|---------------------------|
| Always-on component | ECS Fargate task (24/7) | None (event-driven) |
| Monthly cost (listener only) | ~$30-50 | $0 |
| Failure points | TCP disconnects, task restarts | None |
| Scaling | Manual (adjust task count) | Automatic (EventBridge) |

### Issue 2: Tracking Fargate task IPs

The FPolicy External Engine identifies FPolicy servers by IP address. When a Fargate task restarts its IP changes, so:

- We implemented an IP Updater Lambda (ECS task state change event → update the engine IP via the ONTAP REST API)
- Events may be lost during the 30-60 seconds while the update is in flight
- EC2 + Elastic IP avoids this, but gives up the serverless benefits of Fargate

**With native notifications**: no IP management. You configure an EventBridge rule and you are done.

### Issue 3: Reconfiguring the ONTAP external-engine

Every change to the FPolicy server (IP, port, certificate) requires reconfiguring the external-engine through the ONTAP REST API:

```bash
# Required today, on every deployment
curl -k -u fsxadmin:PASSWORD \
  -X PATCH "https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines/fpolicy_aws_engine" \
  -d '{"primary_servers": ["<NEW_TASK_IP>"]}'
```

**With native notifications**: no ONTAP-side configuration changes at all.

### Issue 4: FPolicy protocol and version dependencies

| Constraint | Impact |
|------------|--------|
| NFSv4.2 not supported | FPolicy is unusable in NFSv4.2-only environments |
| XML-based protocol | A custom parser is required |
| ONTAP version dependencies | Persistent Store needs 9.14.1+; `is-mandatory` needs 9.15.1+ |
| Per-SVM configuration | Multi-SVM environments need configuration on each SVM |

**With native notifications**: protocol-independent, with detection at the S3 API level.

### Issue 5: Unclear event durability semantics

FPolicy event delivery guarantees:
- `is-mandatory=false`: events are lost when the server is unavailable (at-most-once)
- `is-mandatory=true`: file operations are blocked (a trade-off against availability)
- Persistent Store: buffers events, but behaviour when the volume runs out of capacity is unclear

**With native notifications**: at-least-once delivery guarantees comparable to S3 Event Notifications would be expected.

### Issue 6: Cross-account event routing complexity

Current architecture:
```
Account A (FSx for ONTAP + FPolicy)
  → Fargate → SQS → Bridge Lambda → EventBridge Custom Bus
    → EventBridge Rule → Cross-Account Target (Account B)
```

**With native notifications**:
```
Account A (FSx for ONTAP + S3 AP)
  → EventBridge (native) → Cross-Account Rule → Account B
```

### Issue 7: Poor integration with native S3 patterns

The following work by configuration alone on an S3 bucket, but are unavailable on an S3 AP for FSx for ONTAP:

| Native S3 capability | S3 bucket | S3 AP for FSx for ONTAP |
|----------------------|:---:|:---:|
| EventBridge notifications | ✅ | ❌ |
| S3 Event Notifications (SQS/SNS/Lambda) | ✅ | ❌ |
| S3 Inventory | ✅ | ❌ |
| S3 Batch Operations | ✅ | ❌ |
| Object Lifecycle | ✅ | ❌ |

## Quantified Impact

### Operational cost comparison (monthly, medium-sized workload)

| Component | FPolicy approach | Native notifications (expected) |
|-----------|------------------|--------------------------------|
| Fargate (24/7) | $30-50 | $0 |
| IP Updater Lambda | $1-2 | $0 |
| SQS Queue | $1-5 | $0-1 (EventBridge) |
| Bridge Lambda | $1-3 | $0 |
| ONTAP configuration effort | 2-4 hours/month | 0 |
| **Total** | **$33-60 + operational effort** | **$0-1** |

### Complexity comparison

| Metric | FPolicy approach | Native notifications (expected) |
|--------|------------------|--------------------------------|
| CloudFormation resources | 15-20 | 3-5 |
| Lambda functions | 2 (IP Updater + Bridge) | 0 |
| External dependency (ONTAP REST API) | Yes | No |
| Initial setup time | 2-4 hours | 10-15 minutes |
| Troubleshooting surface | TCP connections, FPolicy config, IP updates, SQS | EventBridge rules only |

## Impact by Customer Segment

| Segment | Problem today | Improvement with native notifications |
|---------|---------------|---------------------------------------|
| **ISV / SaaS** | Requires FPolicy operational expertise | Apply S3-compatible event-driven patterns as-is |
| **Enterprise IT** | Requires coordination between ONTAP and AWS administrators | Self-contained on the AWS side |
| **SI partners** | Must include FPolicy design, build, and operations in scope | Can propose standard EventBridge patterns |
| **Regulated industries** | Hard to demonstrate event durability | SLA equivalent to S3 Event Notifications |

## Proposed Feature Specification

### Option A: EventBridge integration

```
FSx for ONTAP Volume (via S3 AP)
  → EventBridge (s3:ObjectCreated, s3:ObjectRemoved, etc.)
    → Any EventBridge Target
```

### Option B: S3 Event Notifications compatibility

```
FSx for ONTAP Volume (via S3 AP)
  → S3 Event Notification Configuration
    → SQS / SNS / Lambda (directly)
```

### Desirable characteristics

- At-least-once delivery guarantee
- S3 event schema compatibility (so existing S3 event handling code can be reused)
- Cross-account delivery support
- Filtering (prefix, suffix)
- Detection of changes made via NFS/SMB as well (not only changes made through the S3 API)

## Maturity of the Current Workaround

The FPolicy event-driven pattern in this repository has reached the following maturity:

- ✅ Verified end-to-end on both NFSv3 and SMB
- ✅ Zero-event-loss design via Persistent Store (ONTAP 9.14.1+)
- ✅ Handles Fargate restarts through automatic IP updates
- ✅ Idempotency guaranteed via DynamoDB
- ✅ Replay Storm Protection (flow control)
- ✅ Three Deployment Profiles (PoC / Production / Compliance)

These make it a genuinely functional workaround, but all of it is complexity that a native capability would remove.

## References

- [FSx for ONTAP S3 AP Improvements Feature Requests](fsxn-s3ap-improvements.md)
- [Trigger Mode Decision Guide](../trigger-mode-decision-guide.md)
- [Deployment Profiles](../deployment-profiles.md)
- [FPolicy Event-Driven pattern](../../solutions/event-driven/fpolicy/README.md)
