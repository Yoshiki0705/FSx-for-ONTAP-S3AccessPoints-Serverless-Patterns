# archive-verify-delete Architecture
🌐 **Language / 言語**: [日本語](architecture.md) | English
## Overview
This pattern copies files to S3 Glacier storage classes, verifies them, and deletes the originals after approval, using the S3 Access Points of Amazon FSx for NetApp ONTAP (FSx for ONTAP) and S3 API calls. Reading, writing and deleting files does not use an NFS mount. Two things do need more: `selection=ATIME` and attribute capture use the ONTAP REST API (a Lambda function inside the VPC), and putting owner, mode and modification time back after a restore needs a host that mounts the volume over NFS. Usage is in the [README](../README.en.md). This document shows the structure, permissions and failure behavior.
## Components
| Component | Role | Where it runs |
|---|---|---|
| `archive` state machine | Select, record, copy, verify, wait for approval, record the approval, delete, summarize | Step Functions (Standard, Distributed Map) |
| `restore` state machine | Select from the ledger, request restore, wait, copy back to the Access Point, verify the restored file | Same |
| `select` | Validate input (refuse a reused `runId`), select by `MTIME`, confirm `ATIME` candidates, apply exclusions | Lambda (outside the VPC) |
| `ontap_rest` | List candidates by `accessed_time`, read file attributes | Lambda (inside the VPC, optional) |
| `record` | Read through the Access Point, compute hashes, write the ledger | Lambda (outside the VPC) |
| `ledger` | Compare the bucket's `HeadObject` with the ledger and set `VERIFIED` or `MISMATCH`; record failures | Lambda |
| `approval` | Write the approval manifest, store the task token, notify. After approval, check approver against starter and set the ledger to `APPROVED` | Lambda |
| `delete` | Only for `APPROVED` items: check ETag and size, delete from the Access Point if they match. `reconcile` settles interrupted items | Lambda |
| `summarize` | Result JSON, EMF metrics, notification, token removal | Lambda |
| `restore` | Restore helpers (select, existence check, restore state, finalize, verify the restored file, reapply script) | Lambda |
| `watchdog` | Publishes how long an approval request has waited (`ApprovalPendingHours`) every 15 minutes | Lambda (EventBridge schedule) |
| Fargate tasks (archive and restore) | Hashing and multipart copy for files above 5 GiB; restore and its verification | ECS Fargate (ARM64, optional, two task roles) |
| Ledger | State, checksums and attributes per `(runId, key)` | DynamoDB (PAY_PER_REQUEST, PITR, deletion protection; UpdateTable turns it off) |
| Archive bucket | Copied objects (`<prefix><runId>/<original key>`) and manifests (`manifests/`) | S3 (created by the stack, no Object Lock) |
| Alarms and notifications | Failed executions, approval wait, stuck deletes, mismatches | CloudWatch alarms, SNS (customer managed key) |
A Lambda function inside the VPC reaches the ONTAP management endpoint but not an Internet-origin Access Point, so the functions are split into `ontap_rest` (inside the VPC) and the rest (outside).
## Flow
```
archive: Plan → [resume: ResumeReconcile → ResumeDefaults → PrepareManifest]
  → [MTIME: SelectMtime | ATIME: AtimeCandidates → SelectFromCandidates]
  → ProcessFiles (Distributed Map, per file):
       attributes → Record → (≤5 GiB: copyObject | >5 GiB: Fargate) → HeadArchived → CompareArchive
       → (optional) second copy → HeadSecond → CompareSecond
  → PrepareManifest → RequestApproval (waitForTaskToken) → ApprovalCheck → DryRunChoice
  → RecordApproval (separation of starter and approver, ledger to APPROVED) → ApprovalRecordedChoice
  → DeleteFiles (Distributed Map, one delete call per file) → Summarize
restore: Select → RestoreFiles (Distributed Map): Prepare → (request restore → wait) → copy
  → Finalize (RESTORED) → verify (Lambda; Fargate above 5 GiB) → RESTORE_VERIFIED / RESTORE_MISMATCH → ReapplyManifest
```
Reaching the delete state requires passing `RequestApproval`, `ApprovalCheck`, `DryRunChoice` and `RecordApproval`. The tests (`test_definitions.py`) check this by removing each state from the transition graph and confirming delete becomes unreachable. In addition, the `delete` function itself does not delete an item whose ledger status is not `APPROVED`: invoking the function directly deletes nothing that has no approval record (`test_approval_gate.py`).
## Verification method
| File size | Copy method | Checksum | Reason |
|---|---|---|---|
| 5 GiB or less | `CopyObject` | `SHA256` (`FULL_OBJECT`) | The bucket's value equals the file's SHA-256 (component check) |
| Above 5 GiB | Multipart `UploadPartCopy` | `CRC64NVME` (`FULL_OBJECT`) | A multipart SHA-256 is `COMPOSITE` and cannot equal the whole-file value |
A `COMPOSITE` result or a missing checksum is not treated as a match; the item becomes `MISMATCH`. After a restore, the file is read back through the Access Point and its SHA-256, CRC64NVME and size are compared with the ledger, giving `RESTORE_VERIFIED` or `RESTORE_MISMATCH`. `RESTORED` only means the copy call succeeded.
## Ledger
| Attribute | Content |
|---|---|
| `runId` (PK), `key` (SK) | Run and file key |
| `status` | `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED`, `RESTORE_MISMATCH`, `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE` |
| `size`, `etag`, `lastModified` | Values at listing time; re-checked just before deletion |
| `sha256`, `sha256B64`, `crc64nvme` | Written by Lambda up to 5 GiB, by Fargate above |
| `archiveBucket`, `archiveKey`, `storageClass` | Destination (`archiveKey` is `<prefix><runId>/<original key>`) |
| `attrs` | `uid`, `gid`, `mode`, `mtime`, `atime` (when available) |
| `secondCopyRequired`, `secondCopy` | Whether a second copy is required, and its verification result |
| `approvedBy`, `approvedAt`, `approvalExecutionArn`, `requestedBy` | The approval record, written only by the `approval` function after approval |
| `claimedBy` | ARN of the execution that holds the delete; lets a delete retry tell its own earlier attempt from someone else's |
| `deletedBy`, `deletedAt`, `restoredAt`, `restoreRunId` | Delete and restore records. `deletedBy` is taken from the ledger's `approvedBy` |
The transition to `APPROVED` is a conditional write the `approval` function makes, after approval, only on `VERIFIED` items. `DELETING` can be entered only from `APPROVED`, or from a `DELETING` item carrying the caller's own `claimedBy`. Two executions therefore cannot delete the same file, and an item without an approval record is not deleted. When the delete call ends in an exception, whether the file is gone is unknown, so the item keeps `DELETING` and `claimedBy`. The Step Functions retry decides from the Access Point: no file means `DELETED` (`already gone on retry`); a file means delete it.
## IAM
| Principal | Main permissions | Permissions it lacks |
|---|---|---|
| `delete` | Access Point `s3:GetObject`, `s3:DeleteObject`; ledger `GetItem`, `UpdateItem`, `Query`; reading execution status (`reconcile`) | Writing to other buckets |
| `approval` | Ledger `Query`, `UpdateItem`; read and write `manifests/*`; `PutParameter` on `/<stack>/approvals/*`; `sns:Publish` | Delete |
| `record` | Access Point `s3:GetObject`; ledger `PutItem` | Delete, writing to the Access Point, updating the ledger |
| `select` | Access Point `ListBucket`, `GetObject`; read and write `manifests/*`; ledger `Query`, `PutItem` | Delete, writing to the Access Point |
| Archive Fargate task role | Access Point `GetObject`, `ListBucket`; archive bucket read and write; ledger `UpdateItem` | Delete, writing to the Access Point |
| Restore Fargate task role | Access Point `GetObject`, `PutObject`; archive bucket read; ledger `GetItem`, `UpdateItem` | Delete |
| `archive` state machine role | Invoke Lambda, the S3 read and write `CopyObject` needs, start ECS (archive task only) | `s3:DeleteObject`, writing to the Access Point |
| `restore` state machine role | Invoke Lambda, `PutObject` on the Access Point (`CopyObject`), start ECS (restore task only) | `s3:DeleteObject` |
Access to the Access Point is allowed twice: in the IAM role and in the Access Point policy. The role side lists both the alias form (`arn:aws:s3:::<alias>/*`) and the Access Point ARN form (`accesspoint/<name>/object/*`); with only one of them the stack deploys but a call can be denied at run time. CloudFormation cannot attach an Access Point policy, so render it from the role ARNs in the stack outputs with `tools/render_access_point_policy.py` and attach it with `aws s3control put-access-point-policy` (README, "Access Point policy"). The policy grants `s3:DeleteObject` to the delete function's role only and `s3:PutObject` to the restore roles only. The tests (`test_definitions.py`, `test_review_followup.py`) check that only the `delete` function holds `s3:DeleteObject`, that only the two restore principals hold `s3:PutObject` on the Access Point, and that the template contains no property or action for Object Lock, Vault Lock, SnapLock or retention. IAM cannot restrict the values written to a ledger item, so write access is limited by keeping the number of principals that can update items small.
## Failure scenarios and blast radius
| Failure | Result | Blast radius |
|---|---|---|
| A file was rewritten after copying | ETag mismatch, `CHANGED`, not deleted | That file |
| A file was rewritten while being copied | `CopySourceIfMatch` returns `PreconditionFailed`, `CHANGED` | That file |
| The bucket's checksum differs from the ledger, or is absent | `MISMATCH`, not deleted | That file |
| A file was rewritten between verification and deletion | Not detected (Access Point `DeleteObject` does not support conditional deletes) | That file; the window is one API round trip |
| The approver does not respond | Stopped after `ApprovalTimeoutHours`, `REJECTED_OR_TIMED_OUT`, nothing deleted. `ApprovalPendingAlarm` fires earlier | The execution |
| The starter approved their own run (`RequireSeparateApprover=true`) | `RecordApproval` refuses: `APPROVAL_REFUSED`; nothing becomes `APPROVED`, nothing is deleted | The execution |
| `dryRun` given as a string | Input error, nothing happens | The execution |
| A `runId` that was already used | Input error (continues only with `resume`) | The execution |
| A Lambda or Fargate step fails | `FAILED` after Retry, reason in the ledger, not deleted | That file |
| A Fargate task does not finish | `States.Timeout` at `FargateTimeoutSeconds` (default 7200 s), one retry, then `FAILED` | That file |
| An exception after the delete call (timeout, failed ledger write) | The item keeps `DELETING` and `claimedBy`; the retry reads the Access Point and records `DELETED` or deletes | That file |
| Retries are exhausted, or the execution stopped, leaving `DELETING` or `APPROVED` | Outcome `COMPLETED_WITH_ERRORS`; `FilesStuckDeletingAlarm` fires; settle with `resume` (README, "Recovering from an interrupted delete") | That file |
| A restored file differs from the ledger | `RESTORE_MISMATCH`; `RestoreMismatchAlarm` fires; left out of the attribute reapply script | That file |
| A file with the same name exists at the restore target | `EXISTS`, not overwritten | That file |
## Rollback
After copying, stopping the execution before approval leaves the files in place. After deletion, use the restore state machine. Items left as `DELETING` or `CHANGED` are also selected for restore when the archive bucket holds a copy. The archive bucket's objects and the ledger remain when the stack is deleted (`DeletionPolicy: Retain`).
## Output classification
The ledger and manifests contain file paths, and a path can contain a person's name or a case identifier, so `data_classification` defaults to `RESTRICTED` ("Restricted — Limited access" in `shared/data_classification.py`). The parameter `DataClassification` changes it. Treat the file contents with the same classification as the original data.
