# Data Freshness and RPO

## Replication Model

This pattern uses **scheduled asynchronous SnapMirror replication** from on-premises ONTAP to Amazon FSx for NetApp ONTAP. Per AWS documentation, replication can be scheduled as frequently as every 5 minutes.

> **Important**: FSx for ONTAP supports only volume-level SnapMirror. Synchronous SnapMirror (including StrictSync) and SVM Disaster Recovery (SVMDR) are not supported.
> 
> Reference: [AWS FSx ONTAP SnapMirror Documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)

## Data Freshness Timeline

```
Source file written    → SnapMirror update triggered → Transfer complete → S3 AP readable → Quick visible
     t=0                    t=0 (on-demand)              t+2-10s            t+0s (immediate)   t+sync interval
                         or t=schedule (max 5min)
```

## RPO Characteristics

| Scenario | RPO | Notes |
|----------|-----|-------|
| Scheduled replication (5-min) | ≤ 5 minutes | Standard continuous protection |
| On-demand trigger (this tool) | Seconds | Manual update triggered immediately |
| Combined (schedule + on-demand) | Near zero during demo | On-demand fills gaps between schedules |

## Key Timestamps for Verification

| Timestamp | Source | How to check |
|-----------|--------|--------------|
| Source file modification time | On-prem ONTAP | `stat` or NFS/SMB attributes |
| Last SnapMirror transfer end | FSx ONTAP REST API | `GET /api/snapmirror/relationships/{uuid}?fields=transfer` |
| S3 AP object availability | S3 API | `ListObjectsV2` / `GetObject` via S3 AP alias |
| Quick dataset refresh | Amazon Quick console | Data source sync status |

## Consistency Considerations

- SnapMirror transfers a **crash-consistent** point-in-time snapshot of the source volume
- Files open for write at transfer time may not include the latest in-flight writes
- S3 Access Point reflects the destination volume state immediately after SnapMirror transfer completes
- Amazon Quick dataset refresh introduces additional latency depending on sync schedule configuration

## Terminology

| Term | Meaning in this context |
|------|------------------------|
| "Near real-time" | Data available in AWS within seconds of on-demand trigger, or within schedule interval |
| "Scheduled replication" | ONTAP-managed periodic SnapMirror update (minimum 5-minute interval on FSx) |
| "On-demand sync" | Manual `snapmirror update` triggered by this tool's one-click button |

## What This Pattern Does NOT Provide

- Synchronous replication (not supported on FSx for ONTAP)
- Sub-second RPO guarantees
- Transaction-level consistency across source and destination
- Automatic conflict resolution for bi-directional writes
