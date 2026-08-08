# File Portal — Scaling & Capacity Planning Guide

🌐 **Language / 言語**: [日本語](../ja/portal-scaling-guide.md) | **English**

> Understanding scaling characteristics, throughput sharing, and growth planning.

## Component Scaling Overview

| Component | Scaling Method | Downtime | Bottleneck Risk |
|-----------|---------------|----------|:---:|
| Lambda (File) | Automatic (concurrent execution) | None | Low |
| Lambda (Admin/VPC) | Automatic | None | Low |
| AppSync | Automatic | None | Low |
| Cognito | Up to 1M users | None | Low |
| DynamoDB | On-demand auto-scales | None | Low |
| S3 (AP origin) | Automatic | None | Low |
| **FSx for ONTAP** | **Manual throughput/storage scaling** | **Minutes during throughput change** | **Primary** |

The portal's serverless components auto-scale without intervention. The only scaling bottleneck is FSx for ONTAP throughput capacity.

---

## Throughput Sharing

S3 AP, NFS, and SMB share the same FSx for ONTAP throughput budget:

```
FSx for ONTAP Throughput (e.g., 128 MBps)
├── NFS clients (EDA workstations, HPC jobs)
├── SMB clients (Windows file shares)
└── S3 AP (portal file browsing + AI processing)
```

### Impact Assessment

| Portal Operation | Typical Throughput | Impact on NFS/SMB |
|-----------------|-------------------|-------------------|
| Directory listing (ListObjectsV2) | < 1 MBps | Negligible |
| Single file read (GetObject) | 1–10 MBps | Negligible |
| AI batch processing (multiple files) | 10–50 MBps | Monitor |
| Bulk download/restore | 50+ MBps | High — use QoS |

### Monitoring

Monitor `ThroughputUtilization` in CloudWatch:
- < 70%: No action needed
- 70–85%: Consider QoS policy for portal volume
- \> 85%: Scale up throughput or defer batch operations

### Mitigation Options

1. **QoS Policy** — Limit portal volume's throughput ceiling:
   ```
   ONTAP REST: POST /api/storage/qos/policies
   {
     "name": "portal-limit",
     "fixed": { "max_throughput_mbps": 64 }
   }
   ```

2. **Throughput Scale-up** — Increase FSx for ONTAP capacity:
   - 128 → 256 → 512 → 1024 → 2048 MBps
   - Takes a few minutes; brief I/O pause during switch
   - No data loss or volume remount required

3. **Scheduling** — Run AI batch processing during off-peak hours via EventBridge Scheduler

---

## Growth Estimation

### Users

| Metric | Typical Value | Scaling Concern |
|--------|--------------|:---:|
| Concurrent portal users | 1–50 | None (Lambda auto-scales) |
| Daily active users | 10–200 | None (Cognito free tier: 50K MAU) |
| AI requests/day | 10–500 | Bedrock throttling at high volume |
| Audit queries/day | 1–20 | Athena cost (minimal) |

### Storage

| Metric | Planning Note |
|--------|--------------|
| Volume size | FSx for ONTAP auto-grows with FlexVol (configure auto-size policy) |
| Snapshot retention | Tamperproof snapshots consume space permanently — budget accordingly |
| DynamoDB (chat history) | TTL auto-deletes after 90 days; steady-state size is bounded |
| CloudTrail logs | Lifecycle policy controls retention; FISC 7-year = significant S3 cost |

### Bedrock (AI Agent)

| Model | Requests/month | Estimated Cost |
|-------|---------------|---------------|
| Nova Lite | 1,000 | ~$1–10 |
| Nova Lite | 10,000 | ~$10–100 |
| Claude 3.5 Haiku | 1,000 | ~$10–50 |
| Claude 3.5 Haiku | 10,000 | ~$100–500 |

Cost depends heavily on input context size (file contents read into prompts).

---

## Limits and Quotas

| Resource | Default Limit | Adjustable |
|----------|--------------|:---:|
| Lambda concurrent executions | 1,000/region | ✅ (Service Quotas) |
| AppSync requests/second | 1,000 | ✅ |
| S3 AP requests/second | 5,500 GET, 3,500 PUT per prefix | Automatic partitioning |
| Bedrock requests/minute | Model-dependent | ✅ (Provisioned Throughput) |
| Cognito sign-in rate | 25/second | ✅ |
| FSx for ONTAP throughput | Per file system config | ✅ (scale up) |

For most portal deployments (< 100 concurrent users), default limits are sufficient.

---

## Recommendations by Scale

| Team Size | Throughput | Recommendations |
|-----------|-----------|----------------|
| 1–10 users | 128 MBps | Default config. DemoMode for testing |
| 10–50 users | 128–256 MBps | Add QoS policy if NFS coexists |
| 50–200 users | 256–512 MBps | Monitor CloudWatch. Consider provisioned Bedrock throughput |
| 200+ users | 512+ MBps | Multi-AZ FSx. Dedicated portal volume. CloudFront for static assets |

---

## Related Documents

- [PoC to Production Guide](./portal-poc-to-production.md)
- [S3 AP Performance Considerations](../s3ap-performance-considerations.en.md)
- [Cost Calculator](../cost-calculator.md) (Japanese)
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md)
