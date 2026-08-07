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

1. **Write to a dedicated output directory** (e.g., `/vol1/ai-outputs/`) that NFS clients only read. This is the mitigation that actually works: it removes the possibility of a conflict rather than managing one.
2. **Do not expect locking to arbitrate it.** S3 has no open or lock semantics, and ONTAP's cross-protocol locking is between NFS and SMB. An S3 AP write is not serialised against a concurrent NFS writer to the same file.
3. **Separate in time if you cannot separate in path**: schedule AI processing when NFS write activity is low. This narrows the window; it does not close it.
4. **Detect it after the fact**: because there is no lock to observe, lock-contention counters will not show this class of conflict. What does show it is access events on the path — ONTAP audit logs, or FPolicy delivered through EventBridge (see `solutions/event-driven/fpolicy/`) — where an S3 write and an NFS write to the same file appear as two events close together.

## ONTAP Behavior

- S3 AP PutObject is atomic in the sense that it replaces the whole object; a reader never sees a half-written object
- Atomic is not the same as exclusive. Two writers are ordered, not prevented
- NFS advisory locks are NOT visible to S3 AP operations
- ONTAP WAFL ensures file system consistency at the block level
- No data corruption risk — but last-writer-wins semantics apply, so one of the two writes is silently lost

> The last point is the one worth carrying away. "No corruption" is a statement about
> the file system, not about your data: the file will be internally valid and will
> contain exactly one of the two versions.

## Reference

- [FSx for ONTAP: Multiprotocol access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/multiprotocol-access.html)
