# SnapLock audit log volumes — what to look at in the console before you are locked in

🌐 **Language / 言語**: [日本語](../ja/snaplock-audit-log-console-guardrails.md) | English

Creating one SnapLock audit log volume blocks deletion of the **volume, then its SVM, then the file
system** for at least six months. This document shows **where to look on the console screens**, with
the actual screens. CLI and API behaviour is in
[SnapLock / Tamperproof pitfalls](../agent/pitfalls-snaplock.md); the approval design is in
[Tamperproof snapshot design](../tamperproof-snapshot-design.md).

> **Measured, not inferred.** The screens were captured on 2026-08-17 from the `ap-northeast-1`
> console (Japanese display language). Identifiers were replaced at capture time. The locked
> volume's state comes from a live ONTAP 9.18.1P3D1 environment.

---

## Conclusion

The console does warn. But **what the warning covers is narrower than what actually happens.**

| What the console says | What actually happens |
|---|---|
| "you will not be able to delete the SnapLock volume" | Not only the volume: the **SVM, and the file system that SVM belongs to**, also cannot be deleted |
| "the minimum retention of files in an audit log volume is 6 months" | True. And **neither this screen nor the AWS API has a field for choosing anything shorter** |
| (on enterprise mode) "a SnapLock administrator can delete files even during the retention period" | **Not for an audit log volume.** Privileged delete applies to *expired* WORM files; there is no route for unexpired audit log files |

So a screen that reads as "only this volume becomes undeletable" leads to a file system pinned for
months. **The three operating points below close that gap.**

---

## Point 1 — Create screen: the acknowledgement is for SnapLock, not for the audit log

`[FSx]` → `[Volumes]` → `[Create volume]`, then choosing `Amazon FSx for NetApp ONTAP` as the file
system type reveals `SnapLock configuration` under `Advanced`.

![The SnapLock section of the create screen, with the audit log volume choice](../screenshots/masked/snaplock-audit-log/console-create-volume-snaplock.png)

Three things are readable here.

1. **The yellow warning and its acknowledgement checkbox belong to setting `SnapLock configuration`
   to `Enabled`.** The text is consent to committing files in this volume to an immutable WORM
   state; it does not mention audit log volumes. **`Audit log volume` has no acknowledgement of its
   own.**
2. **The warning's statement about deletion stops at "you will not be able to delete the SnapLock
   volume".** The SVM and the file system do not appear.
3. **`Retention mode` defaults to `Enterprise`,** whose description says an administrator can delete
   files during the retention period — so **it reads as though there is a way out.** For an audit log
   volume there is not.

> **Operating point**: set `Audit log volume` to `Yes` **only if you have decided to operate
> privileged delete**. Without privileged delete you do not need an audit log volume, and this
> six-month lock never arises. **The first decision is not the retention value; it is whether you
> use privileged delete at all.**

---

## Point 2 — The three retention fields are not the audit log's retention

Further down the same screen, `Retention period` shows three fields: `Default`, `Minimum` and
`Maximum`.

![All three retention fields are for WORM files](../screenshots/masked/snaplock-audit-log/console-create-volume-retention.png)

The section says **"Specify the retention period of files committed to WORM"**, and each field is
described as the retention assigned to *WORM files*. **There is no field on this screen for the
retention of audit log files.**

This is the easiest thing to misread. Because the retention fields sit directly beneath
`Audit log volume` = `Yes`, **they look like the audit log's retention.** They are not; the audit log
gets the default six months. The volume that actually ended up locked had these three fields at
**Default 0 years / Minimum 0 years / Maximum 30 years** and still could not be deleted for six
months — so **"keep the retention at its minimum and you are safe" does not hold.**

| What it constrains | Where it can be set |
|---|---|
| WORM files on the volume | `Retention period` on this screen; `RetentionPeriod` in `CreateSnaplockConfiguration` |
| **Audit log files** (the cause of the lock) | **Neither the console nor the AWS API.** Only the ONTAP CLI's `snaplock log create -retention-period` |

> **Operating point**: before setting `Audit log volume` to `Yes`, **confirm whether you can choose
> the retention that will apply.** From the console you cannot. If you need to control the value,
> create the volume on the ONTAP side.

---

## Point 3 — After the fact: three fields that look fine, and one that carries the reason

This is the detail page of a volume that is already locked.

![A locked volume's detail page. Audit log volume reads No and it still cannot be deleted](../screenshots/masked/snaplock-audit-log/console-volume-detail-locked.png)

**This volume cannot be deleted.** Yet the fields you would naturally check while looking for the
reason all look unremarkable.

| Field | Value | How it reads |
|---|---|---|
| `Lifecycle state` | ⚠ Created | Normal. It is not stuck in `Deleting` |
| `Audit log volume` | **No** | Not an audit log, so it should be deletable |
| `Default retention` / `Minimum retention` | 0 years / 0 years | No retention is configured |
| `Privileged delete` | Permanently disabled | Suspicious, but this is a different terminal state |
| **`Lifecycle transition message`** | **Cannot delete the volume because it contains unexpired log files.** | **The only answer** |

`Audit log volume` reads `No` because **the designation was removed afterwards**. Removing it
succeeds. But what blocks deletion is not the designation: it is the **retention already applied to
the audit log files that were written**, and that survives un-designating. AWS Support described it
the same way (`AuditLogVolume` reports the current designation; ONTAP's `snaplock.is_audit_log` is a
historical marker meaning "was designated at least once", so it stays `true`).

> **Operating point**: when investigating a volume that will not delete, **read
> `Lifecycle transition message` first.** State, retention and audit log designation none of them
> report whether a lock exists.

---

## Reading the expiry

The console detail page does not show the expiry. Read it one of two ways.

ONTAP CLI, over SSH to the management endpoint:

```
volume snaplock show -vserver <svm> -volume <volume> -instance
```

The `Expiry Time` field is the expiry. ONTAP REST returns the same value.

```
GET /api/storage/volumes/{uuid}?fields=snaplock
```

Measured 2026-08-17: `snaplock.expiry_time` was `2027-02-06T17:04:33+09:00`, `is_audit_log` was
`true`, and `retention` was `{default: P0Y, minimum: P0Y, maximum: P30Y}`. **It is `expiry_time`,
not the configured retention, that tells you when deletion becomes possible.**

---

## What AWS Support answered (from a case in 2026-08)

| Question | Answer |
|---|---|
| Deleting or unlocking before the retention expires | **Not possible.** There is no route other than waiting for expiry |
| Billing consideration | Raise it with the "Account and Billing Support" channel **after the resources have been deleted**. Consideration is not guaranteed |
| How to read the expiry | SSH to the management endpoint and read `Expiry Time` from `volume snaplock show -instance` |
| Where the warning lives | The console's `Audit log volume` field, and the `CreateVolume` / `UpdateVolume` API documentation (through the `AuditLogVolume` link), both state the six-month minimum |
| Why `AuditLogVolume: false` still cannot be deleted | What blocks deletion is not the designation but the retention already applied to the audit log files |
| The documentation improvement request | Forwarded to the documentation team. Neither inclusion nor timing is committed |
| Keeping a case open for months | A case cannot stay open that long, so **open a new case referencing the previous case ID** when the deletion is attempted after expiry |

> A documentation change that has been *submitted* is not a documentation change that has been
> *published*. Treat it as not reflected until it appears.

---

## Related documents

- [SnapLock / Tamperproof pitfalls](../agent/pitfalls-snaplock.md) — CLI and API behaviour, with error codes
- [Tamperproof snapshot design](../tamperproof-snapshot-design.md) — pre-flight checks and how the tiers are split
- [Deleting data after retention expires — design](../retention-expiry-deletion-design.md) — the post-expiry deletion workflow
- [AWS: Deleting SnapLock volumes](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/snaplock-delete-volume.html) — primary source for the chain up to the parent resources
- [NetApp KB: What is the minimum retention of SnapLock audit log?](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Protection_and_Security/SnapLock/What_is_the_minimum_retention_of_SnapLock_audit_log%3F) — primary source for the six months
