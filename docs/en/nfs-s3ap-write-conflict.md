# NFS / S3 AP Write Conflict Considerations

> 🌐 Language: **English** | [日本語](../ja/nfs-s3ap-write-conflict.md)

## Overview

FSx for ONTAP S3 Access Points expose the same data accessible via NFS/SMB. When both protocols write to the same file simultaneously, ONTAP handles consistency through its WAFL (Write Anywhere File Layout) — but application-level conflicts can still occur.

## When Conflicts Happen

| Scenario | Risk | Mitigation |
|----------|:---:|-----------|
| NFS write + S3 AP PutObject to same file | High | Use separate output paths |
| NFS read + S3 AP GetObject (same file) | None | Fully safe (read-read) |
| AI output write-back via S3 AP + NFS client editing same file | Medium | Use `OutputDestination=STANDARD_S3` |
| S3 AP PutObject + NFS append to different files | None | No conflict |

## Recommended Pattern

```
NFS/SMB clients → FSx for ONTAP Volume (source data, read-write)
                         ↓ (read via S3 AP)
AI Lambda → S3 AP GetObject (read source)
         → Standard S3 Bucket (write results)  ← OutputDestination=STANDARD_S3
```

This avoids write contention entirely. AI results go to a separate S3 bucket, not back to the ONTAP volume.

## If Write-Back Is Required (OutputDestination=FSXN_S3AP)

When AI results must be visible to NFS/SMB users on the same volume:

1. **Write to a dedicated output directory** (e.g., `/vol1/ai-outputs/`) that NFS clients only read
2. **Use ONTAP file locks**: S3 AP PutObject acquires an exclusive lock during write
3. **Avoid concurrent edits**: Schedule AI processing during off-hours when NFS write activity is low
4. **Monitor**: ONTAP `statistics` show lock contention per volume

## ONTAP Behavior

- S3 AP PutObject is atomic (entire object replacement, not partial)
- NFS advisory locks are NOT visible to S3 AP operations
- ONTAP WAFL ensures file system consistency at the block level
- No data corruption risk — but last-writer-wins semantics apply

## Reference

- [FSx for ONTAP: Multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/multiprotocol-access.html)
