# Feature Request: Retention control and deletion-lock visibility for FSx for ONTAP SnapLock audit log volumes

> 🌐 **Language / 言語**: [日本語](snaplock-audit-log-retention.md) | English

**Submitted by**: Yoshiki Fujiwara (AWS Community Builder)
**Date**: 2026-08-06
**Project**: [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**Context**: Improvement requests arising from creating a SnapLock audit log volume in a verification environment, which left the whole file system undeletable for a minimum of six months
**Status**: 📋 Filed, awaiting response (partial response received)
**Related**: [Tamperproof Snapshot Design Guide](../tamperproof-snapshot-design.md) / [FR-1 to FR-4 (already submitted)](./fsxn-s3ap-improvements.md)

> **On request numbering**: this document uses `SL-1` to `SL-3` because its scope is SnapLock. The numbers `FR-5` to `FR-10` are already in use by two documents covering different scopes.

---

## Executive Summary

**Anyone using only the AWS API accepts a six-month minimum deletion lock on an entire file system without being able to choose the retention period that creates it.**

A long retention period is reasonable as an immutability guarantee. The request is not to weaken the lock. It is for a way to **know the lock is coming before the operation** and a way to **choose the retention period**.

| # | Request | Nature |
|---|---|---|
| SL-1 | Add an audit-log retention parameter to `CreateSnaplockConfiguration`, or state the applied default and the scope of the deletion lock in the API and console | Feature addition |
| SL-2 | Have `DeleteVolume` return an error when unexpired WORM files or audit logs block it (today it returns silently) | Behaviour fix |
| SL-3 | Make `DescribeVolumes` `AuditLogVolume` agree with the ONTAP state, or add a field that determines deletability | Behaviour fix |

AWS Support has confirmed that deleting the volume before expiry is **not possible**, that releasing the file system deletion lock alone is **not possible**, and that **no route exists other than closing the account**. There is therefore no remedy after the fact, which leaves disclosure beforehand as the only control.

---

## What happened

A SnapLock ENTERPRISE volume was created for verification, and a SnapLock audit log volume was created on the same SVM. No retention period was specified, because the AWS API offers no way to specify one. The default of six months applied, and all of the following became undeletable.

```
Unexpired audit log (six-month retention)
        ↓ blocks
   audit log volume        ← DELETE fails (ONTAP error 525057)
        ↓ blocks
   SVM
        ↓ blocks
   file system             ← charges continue until expiry
```

The file system also carries other verification volumes, which can now neither be moved nor deleted.

### Attempts and results

| Attempt | Result |
|---|---|
| `DeleteVolume` | Transitions to `DELETING`, then returns to `CREATED` **without an error** |
| `DeleteVolume` + `BypassSnaplockEnterpriseRetention=true` | Same (no effect) |
| `DeleteVolume` + `SkipFinalBackup=true` | Same |
| `UpdateVolume` with `AuditLogVolume=false` | Not applied |
| ONTAP `DELETE /api/storage/snaplock/audit-logs/{svm.uuid}` (mounted) | Fails (13763189: must be unmounted) |
| ONTAP `PATCH` with `nas.path=""` to unmount | Succeeds |
| ONTAP `DELETE /api/storage/snaplock/audit-logs/{svm.uuid}` (retry) | Succeeds (SVM-level designation cleared) |
| ONTAP `PATCH` with `snaplock.is_audit_log=false` | Rejected (262196: read-only) |
| ONTAP `DELETE /api/storage/volumes/{uuid}` (after offline) | Fails (525057: unexpired SnapLock Enterprise audit log) |

---

## SL-1: A way to specify audit log retention

### Current behaviour

`CreateSnaplockConfiguration` has the following six fields, and **none of them sets the audit log retention period**.

| Field | What it binds |
|---|---|
| `SnaplockType` | Volume type (`COMPLIANCE` / `ENTERPRISE`) |
| `AuditLogVolume` | Whether this volume becomes an audit log volume |
| `AutocommitPeriod` | Time before an unchanged file becomes WORM |
| `PrivilegedDelete` | Whether privileged delete is available (`PERMANENTLY_DISABLED` is terminal) |
| `RetentionPeriod` | Retention for **WORM files on the volume** |
| `VolumeAppendModeEnabled` | Append mode |

`RetentionPeriod` is for WORM files, not for the audit log. They are separate parameters, and setting one to its minimum does not affect the other. In this case `RetentionPeriod` was already at the minimum (`Default 0 YEARS` / `Minimum 0 YEARS`), yet the audit-log side received the six-month default and the deletion lock followed.

Audit log retention can only be set through the ONTAP CLI, with `snaplock log create -retention-period`.

### Impact on this project

This project publishes reference implementations built on the AWS API and CloudFormation. Presenting a pattern that uses `AuditLogVolume=true` would hand readers a six-month deletion lock with no way to choose the period. The portal therefore has no path to create an audit log volume, and points to the ONTAP CLI when one is needed. The AWS-native route cannot complete the task.

### Requested behaviour

Either of the following.

1. Add a parameter to `CreateSnaplockConfiguration` that sets the audit log retention period.
2. If that is difficult, then when `AuditLogVolume=true` is specified, state **the retention default that will apply** and **that the volume, its SVM and the file system cannot be deleted for that period** in the API response, in the console, and in the `CreateVolume` documentation.

Option 2 changes no default, so it is backward compatible, and disclosure alone prevents a repeat.

### Not verified

Whether a value shorter than six months is actually rejected has not been verified. That understanding comes from the documentation. Verifying it would require creating a second audit log volume, which would add another deletion lock, so it was not attempted.

---

## SL-2: Return an error when deletion is blocked

### Current behaviour

`DeleteVolume` against a volume holding unexpired WORM files or an unexpired audit log **returns no error**. `Lifecycle` moves to `DELETING` and returns to `CREATED` tens of seconds later. Adding `BypassSnaplockEnterpriseRetention=true` or `SkipFinalBackup=true` makes no difference.

The same operation through the ONTAP REST API returns an error that states the reason (525057). The information exists in the lower layer and is lost at the AWS API layer.

### Impact on this project

Automation, infrastructure as code and agent-driven operations branch on the response. With no error returned, the call reads as a successful delete, so the next step runs — delete the SVM, then the file system — and fails the same way. The failure only surfaces by polling `Lifecycle`, and without knowing that, the natural next move is to retry with more flags.

### Requested behaviour

When deletion is refused because of retention, have `DeleteVolume` fail and include the reason (unexpired WORM files / unexpired audit log / legal hold) and the `expiry_time` in the message. Passing through what ONTAP already returns would be sufficient.

---

## SL-3: Make `AuditLogVolume` agree with the actual state

### Current behaviour

After the SVM-level audit log designation is cleared through the ONTAP REST API, `DescribeVolumes` begins returning `AuditLogVolume: False`. The volume's `snaplock.is_audit_log` is read-only and cannot be cleared (`PATCH` is rejected with 262196), so **deletability does not change**.

As of this writing the volume reports `AuditLogVolume: False` and is still undeletable.

### Impact on this project

To anyone reading only the AWS API, this says the volume is no longer an audit log volume and should therefore be deletable. Because deletability has not changed, diagnosis cannot be completed at the AWS API layer and requires ONTAP REST API access. In an AWS-API-based tool such as the portal, surfacing this value as-is misleads the operator.

### Requested behaviour

Either of the following.

1. Make `AuditLogVolume` agree with the ONTAP `snaplock.is_audit_log` value.
2. If that is difficult, add a field to `DescribeVolumes` that determines deletability — for example `SnaplockConfiguration.ExpiryTime`, or the reason deletion is blocked.

---

## AWS Support findings (2026-08)

| Request | Response |
|---|---|
| Can the audit log volume be deleted before retention expiry | **No** (confirmed internally) |
| Can the file system deletion lock alone be released | **No** |
| Does any route exist other than closing the account | **No such route exists** (explicit) |

The requests corresponding to SL-1 to SL-3, and the remaining questions, are still under review.

---

## Related Documents

- [Tamperproof Snapshot Design Guide](../tamperproof-snapshot-design.md) — SnapLock volumes versus snapshot locking, and the pre-flight checklist
- [FR-1 to FR-4 (already submitted)](./fsxn-s3ap-improvements.md) — FSx for ONTAP S3 AP core features
- [Lambda / HealthOmics integration gaps](./lambda-healthomics-s3ap-gaps.en.md) — a different scope
