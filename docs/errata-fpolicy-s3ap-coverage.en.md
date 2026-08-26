# Errata — FPolicy does not see the S3 Access Point path

🌐 **Language / 言語**: [日本語](errata-fpolicy-s3ap-coverage.md) | English

<!-- drift-exempt-file: this errata sheet has to carry the corrected-from text verbatim to be usable as one -->

Several articles in this series offered FPolicy as the workaround for the event notifications
that FSx for ONTAP S3 Access Points do not provide. Measurement showed that the offer
**does not hold where writes arrive through an S3 access point**. This page holds the
correction text to append to the published articles, and the list of articles it applies to.

## What was wrong

| What the articles said | What was measured |
|---|---|
| S3 AP has no event notifications, so use FPolicy instead | Operations through the access point raise **no** FPolicy notification, so it is not a substitute |
| A `mandatory` synchronous policy can block them | Operations on that path are **not blocked** |
| FPolicy puts access point operations into the audit trail | It does not. The ONTAP native audit log (`vserver audit`) does |

What FPolicy detects is file operations arriving over NFS or SMB. On a volume whose writes
arrive that way, the design in the articles holds unchanged.

## What was measured

| Measurement | Result |
|---|---|
| 90 seconds of no activity (control) | 0 notifications |
| 9 S3 access point data-plane calls (PUT 3 / GET 3 / HEAD 1 / LIST 1 / DELETE 1) | **0 notifications** |
| NFSv3 create + read + delete on the same volume (control) | 3 notifications |
| Synchronous `mandatory` policy with a responding engine | Operations through the access point are **not blocked** |
| UNIX identity + NFS, and WINDOWS identity + SMB | Same result for both |

Structural reason: an FPolicy event accepts only three values for `protocol` — `cifs`, `nfsv3`
and `nfsv4`. `s3`, `object` and `http` are each rejected with HTTP 400. That the access point
writes do reach the volume was confirmed by mounting the same volume over NFS.

Conditions: 2026-08-26, ap-northeast-1, ONTAP 9.18.1P3D1, SINGLE_AZ_1 / 128 MBps.

Full verification record: [the measured FPolicy / S3 access point coverage](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/s3ap-monitoring-coverage-implications.md)

## Text to append (copy and paste at the end of each article)

```markdown
---

## 📢 Correction (2026-08-26)

This article offers FPolicy as the workaround for the event notifications that FSx for ONTAP
S3 Access Points do not provide. Measurement showed that this **holds only where writes arrive
over NFS or SMB**.

Operations through an S3 access point raise no FPolicy notification, and are not blocked even
by a `mandatory` synchronous policy (2026-08-26, ap-northeast-1, ONTAP 9.18.1P3D1: 0
notifications across 9 S3 access point data-plane calls, against 3 for the NFSv3 control on the
same volume. An FPolicy event accepts only `cifs`, `nfsv3` or `nfsv4`; `s3` returns HTTP 400).

To drive something from data written through the access point, use EventBridge Scheduler
polling, or the ONTAP native audit log, which records access point operations as
`Source=HTTP` / `Source=S3` — though not the requester, so the caller has to be correlated
with CloudTrail data events by timestamp.

👉 [Verification record](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/s3ap-monitoring-coverage-implications.md)
```

## Articles this applies to

| Phase / Part | Article | Where the correction belongs |
|---|---|---|
| Phase 10 | [dev.to](https://dev.to/aws-builders/fpolicy-event-driven-pipeline-multi-account-stacksets-and-cost-optimization-fsx-for-ontap-s3-5bd6) | The TL;DR line calling it the FR-2 alternative, and "Why FPolicy" |
| Part 4 (FPolicy Event-Driven) | [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-s3ap-serverless-part4-event-driven-fpolicy) | The TL;DR |
| Phase 13 / Part 5 | [dev.to](https://dev.to/aws-builders/from-serverless-patterns-to-field-ready-reference-architecture-fsx-for-ontap-s3-access-points-dhj) / [Hatena](https://hakobiya.hatenablog.com/entry/fsxn-s3ap-serverless-part5-field-ready-28-patterns) | "Trigger strategy matters", the EVENT_DRIVEN clause |

The repository's own occurrences are corrected in this pull request. To stop the claim coming
back, the `MEASURED_FALSE` rule in `scripts/check_portal_drift.py` scans every tracked
document, and `scripts/check_published_articles.py` applies the same rule to the published
article bodies over the network.

## What this correction does not change

- The design and implementation of the FPolicy pipeline on volumes whose writes arrive over
  NFS or SMB
- The FPolicy server implementation, the Fargate template, or the EventBridge routing
- The case for native event notifications. If anything it is stronger: for writes arriving
  through the access point there is currently no storage-layer event mechanism at all
