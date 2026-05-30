# AWS Support Case Draft — S3 AP ServiceUnavailable after Throughput Capacity Change

## Subject

FSx for ONTAP S3 Access Points return ServiceUnavailable after throughput capacity change (128 → 256 → 128 MBps)

## Severity

General guidance (non-production impact — benchmark testing environment)

## Service

Amazon FSx for ONTAP

## Category

S3 Access Points / Performance

---

## Description

After changing the throughput capacity of our FSx for ONTAP file system, all S3 Access Points attached to the file system return `ServiceUnavailable` errors. The issue persists even after reverting the throughput capacity back to the original value.

### Environment

- **File System ID**: fs-09ffe72a3b2b7dbbd
- **Region**: ap-northeast-1
- **Deployment Type**: SINGLE_AZ_1
- **ONTAP Version**: (current)
- **SVMs affected**: All (FSxN_OnPre, verification-svm)
- **S3 AP NetworkOrigin**: Internet (all affected APs)

### Timeline

| Time (JST) | Action |
|------------|--------|
| 2026-05-23 09:12 | `update-file-system` ThroughputCapacity 128 → 256 MBps |
| 2026-05-23 09:37 | ThroughputCapacity change completed (256 MBps confirmed) |
| 2026-05-23 09:37+ | All S3 APs return `ServiceUnavailable` or `ConnectionClosedError` |
| 2026-05-23 09:50 | Initiated revert: ThroughputCapacity 256 → 128 MBps |
| 2026-05-23 ~10:15 | Revert completed (128 MBps confirmed) |
| 2026-05-23 10:20+ | S3 APs still return `ServiceUnavailable` |

### Error Details

**From Lambda (VPC-external, Internet access):**
```
ServiceUnavailable: Service is unable to handle request.
```

**From Lambda (VPC-external, different S3 AP alias):**
```
ConnectionClosedError: Connection was closed before we received a valid response from endpoint URL
```

### S3 APs Tested (all return errors)

1. `eda-demo-s3ap` (Volume: eda_demo_vol, SVM: FSxN_OnPre)
2. `fsxn-eda-s3ap` (Volume: s3ap_headobj_test, SVM: FSxN_OnPre)
3. `verification-test-ap` (Volume: verification_vol, SVM: verification-svm)

### File System Status

- File system Lifecycle: `AVAILABLE`
- All S3 AP attachments Lifecycle: `AVAILABLE`
- No pending administrative actions
- ThroughputCapacity: 128 MBps (reverted)

### Questions

1. Is there a known recovery time for S3 Access Points after a throughput capacity change?
2. Is there an action we can take to restore S3 AP functionality (e.g., detach/reattach, or wait for a specific duration)?
3. Does the throughput capacity change trigger a data LIF failover or ONTAP node reboot that affects the S3 AP data plane?
4. Is there documentation on expected S3 AP behavior during/after throughput capacity changes?

### Impact

- Benchmark testing is blocked
- No production workload impact (test environment)
- NFS/SMB access status unknown (no EC2 SSH access available to verify)

---

## 投稿先

AWS Support Console: https://console.aws.amazon.com/support/
Service: Amazon FSx
Category: General guidance or Technical issue
