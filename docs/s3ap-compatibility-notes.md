# S3AP Compatibility Notes

## What FSx for ONTAP S3 Access Points Provide

FSx for ONTAP S3 Access Points provide an S3-facing access boundary for file data stored in FSx for ONTAP. Data remains on FSx for ONTAP and can continue to be accessed through NFS and SMB.

## Tested Operations

| Operation | Status |
|-----------|--------|
| ListObjectsV2 | ✅ Tested |
| GetObject | ✅ Tested |
| PutObject (max 5 GB) | ✅ Tested |
| Range GET | ✅ Tested |
| HeadObject | ✅ Tested |
| DeleteObject | ✅ Tested |
| MultipartUpload | ✅ Supported (per AWS docs) |

## Not Equivalent to Full S3 Bucket Semantics

Not all bucket-level features or integration patterns apply directly:

- Native S3 bucket notifications (GetBucketNotificationConfiguration not supported)
- Bucket lifecycle policies
- Bucket versioning
- Object Lock (on the S3AP itself)
- Presigned URLs (see repository compatibility testing)

## Recommended Trigger Patterns

| Pattern | Description |
|---------|-------------|
| POLLING (default) | EventBridge Scheduler + Discovery Lambda |
| EVENT_DRIVEN | FPolicy-based, near-real-time; not native S3 bucket notifications |
| HYBRID | Both polling and event-driven with deduplication |

## Related Documentation

- [S3AP Authorization Model](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [S3AP Benchmark Results](s3ap-benchmark-results.md)
- [S3AP Performance Considerations](s3ap-performance-considerations.md)
- [Deployment Profiles](deployment-profiles.md)
