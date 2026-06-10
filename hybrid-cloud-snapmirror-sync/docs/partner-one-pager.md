# Partner One-Pager: Hybrid Cloud SnapMirror Sync

> 1. This pattern demonstrates how existing enterprise file data on ONTAP can be made available for cloud analytics and BI **without first moving everything into an S3 data lake**.
> 2. SnapMirror keeps FSx for ONTAP updated as a **near real-time replicated copy**.
> 3. S3 Access Points expose the replicated file data to AWS services, while **Amazon Quick / Quick Sight provides the business-facing UI**.

---

## Target Customer

- Organizations using on-premises NetApp ONTAP for enterprise file data
- Need cloud analytics/AI capabilities without full data migration
- Want to preserve existing NAS operations while enabling new workloads

## Customer Pain Points

- Enterprise file data on NAS is disconnected from cloud analytics/AI services
- Full S3 copy creates dual-management overhead and staleness
- Business users cannot self-serve insights from operational file data
- Data freshness gap between source files and analytical systems

## Solution Value

| Layer | Component | Value |
|-------|-----------|-------|
| Replication | SnapMirror (scheduled, near real-time) | Continuous data availability in AWS without migration |
| Storage | FSx for NetApp ONTAP | Managed ONTAP in AWS with NFS/SMB/S3 API |
| Access | S3 Access Points for FSx ONTAP | Connect file data to S3-native analytics/AI services |
| Consumption | Amazon Quick / Quick Sight | Business users analyze data via natural language or dashboards |

## Partner Motion

| Phase | Activity | Deliverable |
|-------|----------|-------------|
| Demo | Run DEMO_MODE or live hybrid setup | Customer sees end-to-end data flow |
| PoC | Deploy with customer's ONTAP + FSx | Validate latency, freshness, access patterns |
| Production Readiness | Security review, governance, monitoring | Architecture decision record |
| Managed Operations | Ongoing SnapMirror health, Quick refresh | Operational runbook |

## 3-Minute Demo Talk Track

1. "Enterprise file data lives on an on-premises ONTAP system."
2. "SnapMirror continuously replicates changes to FSx for ONTAP in AWS — scheduled as frequently as every 5 minutes, or triggered on-demand."
3. "S3 Access Points expose that file data through the S3 API — no data copy to a separate bucket needed."
4. "Amazon Quick / Quick Sight lets business users search, visualize, and act on that data immediately."
5. "The source of truth stays on-premises. AWS provides the analytics and AI layer. No dual-copy, no stale data, no migration required."

## Feature Boundaries

- SnapMirror is scheduled replication (minimum 5-minute interval), not synchronous transaction sharing
- FSx S3 Access Points provide S3 API access to file data — not a standard S3 bucket
- Amazon Quick is the consumption/insight layer — not the source of truth
- Source of truth must be defined by the customer's data governance

## Success Metrics

| Metric | Description |
|--------|-------------|
| Time to insight | Minutes from file creation to searchable in Quick |
| Data freshness | SnapMirror replication lag (scheduled + on-demand) |
| Manual copy eliminated | No S3 sync jobs or ETL pipelines needed |
| Self-service users | Number of business users accessing Quick dashboards |
| Operational overhead | Reduction in data preparation steps |
