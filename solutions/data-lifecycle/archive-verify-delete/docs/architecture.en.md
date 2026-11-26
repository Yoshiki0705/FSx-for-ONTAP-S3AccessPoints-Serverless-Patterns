# archive-verify-delete Architecture
🌐 **Language / 言語**: [日本語](architecture.md) | English
## Overview
This pattern copies files to S3 Glacier storage classes, verifies them, and deletes the originals after approval, using only the S3 Access Points of Amazon FSx for NetApp ONTAP (FSx for ONTAP) and S3 API calls. The volume is not mounted. Usage is in the [README](../README.en.md). This document shows the structure, permissions and failure behavior.
## Components
| Component | Role | Where it runs |
|---|---|---|
| `archive` state machine | Select, record, copy, verify, wait for approval, delete, summarize | Step Functions (Standard, Distributed Map) |
| `restore` state machine | Select from the ledger, request restore, wait, copy back to the Access Point | Same |
| `select` | Validate input, select by `MTIME`, confirm `ATIME` candidates | Lambda (outside the VPC) |
| `ontap_rest` | List candidates by `accessed_time`, read file attributes | Lambda (inside the VPC, optional) |
| `record` | Read through the Access Point, compute hashes, write the ledger | Lambda (outside the VPC) |
| `ledger` | Compare the bucket's `HeadObject` with the ledger and set `VERIFIED` or `MISMATCH`; record failures | Lambda |
| `approval` | Write the approval manifest, store the task token, notify | Lambda |
| `delete` | Check ETag and size, delete from the Access Point if they match | Lambda |
| `summarize` | Result JSON, EMF metrics, notification, token removal | Lambda |
| `restore` | Restore helpers (select, existence check, restore state, finalize, reapply script) | Lambda |
| Fargate task | Hashing and multipart copy for files above 5 GiB | ECS Fargate (ARM64, optional) |
| Ledger | State, checksums and attributes per `(runId, key)` | DynamoDB (PAY_PER_REQUEST, PITR) |
| Archive bucket | Copied objects (`data/`) and manifests (`manifests/`) | S3 (created by the stack, no Object Lock) |
A Lambda function inside the VPC reaches the ONTAP management endpoint but not an Internet-origin Access Point, so the functions are split into `ontap_rest` (inside the VPC) and the rest (outside).
## Flow
```
archive: Plan → [MTIME: SelectMtime | ATIME: AtimeCandidates → SelectFromCandidates]
  → ProcessFiles (Distributed Map, per file):
       attributes → Record → (≤5 GiB: copyObject | >5 GiB: Fargate) → HeadArchived → CompareArchive
       → (optional) second copy → HeadSecond → CompareSecond
  → PrepareManifest → RequestApproval (waitForTaskToken) → ApprovalCheck → DryRunChoice
  → DeleteFiles (Distributed Map, one delete call per file) → Summarize
```
The delete state can be reached only through `RequestApproval`, `ApprovalCheck` and `DryRunChoice`. A test (`test_definitions.py`) removes each of these states from the transition graph and checks that the delete state becomes unreachable.
## Verification method
| File size | Copy | Checksum | Reason |
|---|---|---|---|
| 5 GiB or less | `CopyObject` | `SHA256` (`FULL_OBJECT`) | The bucket's value equals the file's SHA-256 (component check) |
| Above 5 GiB | Multipart `UploadPartCopy` | `CRC64NVME` (`FULL_OBJECT`) | A multipart SHA-256 is `COMPOSITE` and does not equal the whole-file value |
A `COMPOSITE` checksum, or no checksum, is never treated as a match; the file becomes `MISMATCH`.
## Ledger
| Attribute | Content |
|---|---|
| `runId` (PK), `key` (SK) | Run and file key |
| `status` | `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETING`, `DELETED`, `RESTORED`, `CHANGED`, `MISMATCH`, `FAILED` |
| `size`, `etag`, `lastModified` | Values at listing time, checked again just before deletion |
| `sha256`, `sha256B64`, `crc64nvme` | Written by Lambda up to 5 GiB, by Fargate above |
| `archiveBucket`, `archiveKey`, `storageClass` | Destination |
| `attrs` | `uid`, `gid`, `mode`, `mtime`, `atime` when available |
| `secondCopyRequired`, `secondCopy` | Whether a second copy is required and its verification result |
| `deletedBy`, `deletedAt`, `restoredAt`, `restoreRunId` | Deletion and restore records |
The move to `DELETED` is a conditional write. Only the execution that moves an item from `VERIFIED` to `DELETING` proceeds to delete, so of two concurrent executions on the same file, only one deletes it. If the delete call fails, the item returns to `VERIFIED` so a Step Functions retry can succeed.
## IAM
| Principal | Main permissions | Permissions it does not have |
|---|---|---|
| `delete` | Access Point `s3:GetObject`, `s3:DeleteObject`; ledger `GetItem`, `UpdateItem` | Writing to other buckets |
| `record` | Access Point `s3:GetObject`; ledger `PutItem` | Delete |
| `select` | Access Point `ListBucket`, `GetObject`; read/write `manifests/*` | Delete |
| `approval` | Ledger `Query`; write `manifests/*`; `PutParameter` on `/<stack>/approvals/*`; `sns:Publish` | Delete |
| Fargate task | Access Point read/write; bucket read/write; ledger update | Delete |
| State machine roles | Invoke Lambda; the S3 read/write that `CopyObject` needs; start ECS tasks | `s3:DeleteObject` |
Access Point permissions are written in both forms: the alias form (`arn:aws:s3:::<alias>/*`) and the Access Point ARN form (`accesspoint/<name>/object/*`). A policy with only one form can deploy and still be denied at runtime. Tests (`test_definitions.py`) check that `delete` is the only resource holding `s3:DeleteObject`, and that the template has no property or action for Object Lock, Vault Lock, SnapLock or retention.
## Failure scenarios and blast radius
| Failure | Result | Blast radius |
|---|---|---|
| The file is modified after it is copied | ETag mismatch, `CHANGED`, not deleted | That file |
| The file is modified while it is copied | `CopySourceIfMatch` returns `PreconditionFailed`, `CHANGED` | That file |
| The bucket's checksum differs from the ledger, or is absent | `MISMATCH`, not deleted | That file |
| The file is modified between the check and the delete | Not detected (the Access Point's `DeleteObject` does not support conditional deletes) | That file; the window is one API round trip |
| The approver does not respond | Stops at `ApprovalTimeoutHours` with `REJECTED_OR_TIMED_OUT`, nothing deleted | The execution |
| `dryRun` is passed as a string | Input error, nothing happens | The execution |
| Lambda or Fargate fails | `FAILED` after retries, reason in the ledger, not deleted | That file |
| The execution stops in the middle of a delete | The item may remain `DELETING`; decide by hand from the ledger | That file |
| A file with the same name exists at the restore target | `EXISTS`, not overwritten | That file |
## Rollback
After a copy, stopping the execution before approval leaves the files in place. After a delete, use the `restore` state machine. The archive bucket's objects and the ledger remain after the stack is deleted (`DeletionPolicy: Retain`).
## Output classification
The ledger and manifests are `operational-metadata` (paths, sizes, hashes, attributes). File contents carry the same classification as the original data.
