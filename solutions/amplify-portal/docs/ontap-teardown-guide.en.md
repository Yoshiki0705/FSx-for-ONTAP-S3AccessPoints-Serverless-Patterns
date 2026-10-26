
🌐 **Language / 言語**: [日本語](ontap-teardown-guide.md) | English

Operational notes for the ONTAP resource-deletion (teardown) actions added to the portal's
Resource Management section. They were added to delete resources that cannot be removed until
their dependencies are unwound, in the order they have to be unwound — the case that comes up
when cleaning up a verification environment. This collects each action's REST endpoint, its
synchronous/asynchronous behaviour, and the dependency order in one place.

> **Verification status**: all actions were exercised once, on a disposable SVM on
> fs-0123456789abcdef0 (ONTAP 9.18.1P6), on 2026-10-26. The differences only a real cluster
> revealed — SVM delete goes through the FSx API, audit's consolidation wait, audit's `log_path`,
> and the FPolicy engine refusal wording — are reflected in the implementation and this note.

## New actions

| Action | Kind | Path | Sync/async | Status |
|---|---|---|---|---|
| `listFpolicyEngines` | read | ONTAP REST GET `/protocols/fpolicy/{svm.uuid}/engines` | sync | verified |
| `deleteFpolicyEngine` | delete | ONTAP REST DELETE `/protocols/fpolicy/{svm.uuid}/engines/{name}` | sync | verified |
| `getAuditConfig` | read | ONTAP REST GET `/protocols/audit/{svm.uuid}` (`log_path`) + `.../object-store` | sync | verified |
| `deleteAudit` | delete | ONTAP REST PATCH (disable) + DELETE (retried for consolidation) | async (202→job) | verified |
| `deleteObjectStoreAudit` | delete | ONTAP REST PATCH (disable) + DELETE `.../object-store` | async (202→job) | verified |
| `listSvms` | read | **AWS FSx API** DescribeStorageVirtualMachines (scoped to the file system) | sync | verified |
| `getSvmDeletionImpact` | read | ONTAP REST GET `/storage/volumes?...&fields=is_svm_root` | sync | verified |
| `deleteSvm` | delete | **AWS FSx API** DeleteStorageVirtualMachine (not ONTAP REST) | async | verified |
| `deleteFlexClone` | delete | ONTAP REST PATCH (offline) + DELETE `/storage/volumes/{uuid}` | async (202→job) | verified |

Beyond these, UI was added for backend actions that already existed but had no UI:
`deleteObjectStoreBucket`, `listObjectStoreBuckets`, `updateQosPolicy`, `listExpiredRetention`,
and `assignSnapshotPolicy` (behaviour unchanged).

## Sources (official REST reference)

Figures and behaviour are summarised from NetApp's official REST reference (verbatim quotation
avoided). Content was rephrased for compliance with licensing restrictions.

- [Delete an FPolicy external engine configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-fpolicy-engines-.html):
  an engine attached to a policy cannot be deleted (the basis for the order). Response is synchronous.
- [Delete an audit configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-audit-.html) /
  [Delete an S3 audit configuration](https://docs.netapp.com/us-en/ontap-restapi/delete-protocols-audit-object-store.html):
  202 async. Delete fails while auditing is enabled (`140902421`); final consolidation in progress is `140902422`.
- [Delete an SVM](https://docs.netapp.com/us-en/ontap-restapi/delete-svm-svms-.html): 202 async.

## Teardown order (operational notes)

### FPolicy

```
disable policy → delete policy → delete event → delete engine
```

An engine cannot be deleted while a policy references it. The FPolicy panel's Engines tab shows
this order and keeps each step a separate action (there is no one-click teardown). The `native`
engine is built into ONTAP and is shown disabled rather than deletable.

### Audit and volumes

```
(when the volume is an audit log destination) delete audit → delete volume
```

A volume that is an audit log destination cannot be deleted. Remove (disable) the audit first.
`deleteAudit` / `deleteObjectStoreAudit` disable via PATCH when enabled and then DELETE, a
two-step. **Two things measured on 9.18.1P6:**

- **The two steps are needed** (they do not collapse into one). Deleting while enabled is
  accepted with a 202 and then fails inside the job with `resource in use`; disabling first
  avoids that path.
- **The delete immediately after the disable fails with `Final consolidation is in progress`**
  and succeeds on a retry ~20s later. So `deleteAudit` retries the post-disable delete with a
  short backoff, but only for that consolidation error (any other error returns at once).

The log destination is reported as `log_path` (a junction path) in the REST response, not
`log.volume.name` (passing `log.volume` at create time is refused with code 262179).

Re-pointing audit to a different volume is out of scope: it involves design choices (destination
volume, log format, retention) beyond teardown.

### SVM

```
delete all non-root volumes → delete the SVM (with its root volume)
```

An SVM cannot be deleted while it still owns non-root volumes. As the widest-blast-radius action,
the UI keeps the execute button disabled until the re-typed SVM name matches.

**Two constraints measured on fs-002 (FSx for ONTAP specific):**

1. **The SVM delete cannot go through ONTAP REST** [E-013]**.** With the fsxadmin account, ONTAP REST
   `DELETE /svm/svms/{uuid}` is refused with `not authorized for that command` (code 6), even
   with zero non-root volumes. The SVM is an AWS-managed resource, so the delete goes through the
   **AWS FSx API** (`DeleteStorageVirtualMachine`). `deleteSvm` uses the boto3 fsx client, and
   `listSvms` is also sourced from the FSx API so it carries the FSx SVM id (svm-...) the UI needs.
2. **The FSx and ONTAP planes lag each other.** The FSx API counts volumes in ONTAP's recovery
   queue as non-root volumes, and a volume created or deleted through ONTAP REST is not reflected
   in the FSx inventory immediately. So even when `getSvmDeletionImpact` reports zero non-root
   volumes on the ONTAP side, the FSx API delete can be refused with
   `Cannot delete storage virtual machine while it has non-root volumes`. `deleteSvm` surfaces
   that refusal with a note that an ONTAP-side delete may not yet be visible to FSx.

### FlexClone

```
(when the parent cannot be deleted) split or delete the clone → delete the parent
```

A parent volume cannot be deleted while a clone exists. `deleteFlexClone` removes the clone
volume itself with the same shape as a plain volume delete (unmount → offline → delete, each
job-waited). When a parent delete is blocked by clones, the UI lists the clones tied to that
parent. The base snapshot left on the parent after a split is the operator's to remove.

## Shared design

- Destructive deletes require `confirm=true` in the backend and refuse before any ONTAP call
  when it is absent.
- 202 async operations wait for the job (long-running ones such as an SVM root delete tolerate
  a still-running job).
- Deletes read back (GET 404/empty) to confirm removal.
- Caller-supplied names reaching a REST path are checked with `_is_unsafe_path` and percent-encoded.
- Authentication failures stop immediately and are not retried (to avoid locking fsxadmin).
- Nothing bypasses or shortens retention locks (SnapLock / snapshot locking / Object Lock /
  Tamperproof). The `assignSnapshotPolicy` UI routes only a retention-bearing assignment through
  the existing SnaplockConfirmDialog (`acknowledgeIrreversible`), never a plain confirm.

### FlexClone delete and the parent delete (note)

A deleted clone stays in ONTAP's recovery queue (up to 12 hours), during which the parent volume
delete is blocked with `because it has one or more clones`. In normal portal use this clears by
waiting; to remove it immediately in a verification environment, a cluster administrator purges
the recovery queue (`volume recovery-queue purge`, outside the portal). When a parent delete is
blocked by clones, the UI lists the clones tied to that parent.

## Real-machine check results (2026-10-26, ONTAP 9.18.1P6)

All actions were exercised once on a disposable SVM `teardownprobe`:

| Item | Result |
|---|---|
| FlexClone delete | unmount→offline→delete succeeded, read-back confirmed removal |
| Parent delete with clone | refused with `because it has one or more clones` (also while a deleted clone sits in the recovery queue) |
| Audit delete | two steps required; the delete right after disable fails on consolidation, succeeds on retry; destination is `log_path` |
| FPolicy engine delete | synchronous; refused while referenced with code 9764940 `At least one policy is using ...` |
| SVM deletion impact | `is_svm_root` separates root from non-root correctly |
| SVM delete | ONTAP REST not permitted for fsxadmin (code 6) → succeeds via the **FSx API**; the FSx API also counts recovery-queue volumes, so an ONTAP-side delete may need to propagate first |

Irreversible deletes were run only after presenting each target for approval, one at a time, and
all resources were deleted afterwards to return the environment to its prior state.
