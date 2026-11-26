# archive-verify-delete: Archive with S3 API Calls Only: Copy, Verify, Delete After Approval
🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.en.md)
## Overview
This pattern moves rarely read files on an Amazon FSx for NetApp ONTAP (FSx for ONTAP) volume to S3 Glacier storage classes. Reading, writing and deleting files uses the S3 API of S3 Access Points; no NFS mount is used for that. Two things do need more: selecting by last access time (`selection=ATIME`) and capturing attributes use the ONTAP REST API (a Lambda function inside the VPC, ONTAP credentials, the management endpoint), and putting owner, mode and modification time back after a restore needs a host that mounts the volume over NFS.
Each file goes through the steps below. A file whose conditions stop holding at any step is taken out of the delete set.
1. Record size, ETag, SHA-256 and CRC64NVME in a ledger (a DynamoDB table)
2. Copy it to an archive bucket with `CopyObject`, specifying the storage class (key `<prefix><runId>/<original key>`)
3. Compare the checksum the bucket returns with the ledger
4. A person approves the list of matching files. The approval is recorded in the ledger as `APPROVED`, and it is refused when the approver is the principal that started the run (default; the comparison is of declared values and is not proof of identity)
5. Only files the ledger shows as `APPROVED` are deleted, after checking that the Access Point's ETag and size still equal the ledger's

To restore, the pattern finds the files in the ledger, requests a restore in the bucket, waits for it, copies the files back to the Access Point with `CopyObject`, then reads each restored file back and compares it with the ledger's SHA-256 and CRC64NVME.
The pattern does not use S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock or snapshot locking, and none of them appears in the template. No retention period is set, so objects in the archive bucket can be deleted by anyone with permission.
The assumptions behind this pattern and a comparison with other approaches are in [Comparing 9 kinds of mechanisms for moving files to archive classes](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md).
## What was measured and what was not
| Category | Content |
|---|---|
| Components checked once each on a real system (recorded in the comparison above; 2026-11-24 and 2026-11-26, ap-northeast-1, first-generation `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, UNIX-style volume, Access Point user is UNIX root) | With `ChecksumAlgorithm=SHA256` on `CopyObject`, the bucket's `ChecksumSHA256` was `FULL_OBJECT` and equal to the file's SHA-256 (up to 8 MiB). For a 5.5 GiB multipart copy, SHA-256 became `COMPOSITE` and CRC64NVME was `FULL_OBJECT` and equal. `--copy-source-if-match` with an old ETag returned `PreconditionFailed`. The Access Point's `DeleteObject` returned `NotImplemented` when given `If-Match`. A Step Functions SDK integration accepted the Access Point alias as `Bucket` |
| Checked in this repository | Unit tests with moto, and tests of the state machine and IAM structure. No connection to AWS. The permissions and settings in "Deployment and operating prerequisites" below are checked by tests |
| Checked once each in the seven-file run including 5.5 GiB (2026-11-26, same environment as above, `selection=ATIME`, `GLACIER`, 7 files) | Selection by `accessed_time` and capture of uid, gid, mode, mtime and atime through the ONTAP REST API (the root is the volume root and the path has no leading slash; `unix_permissions` comes back as the integer `640`). The Distributed Map `ItemReader` and `ResultWriter`. A 5.5 GiB Fargate multipart copy (with `CopySourceIfMatch`; CRC64NVME equal to the ledger). Hashing of a 5.3 GB (about 4.94 GiB) file in Lambda (69.8 s, 2048 MB configured, 152 MB used). The second copy. Deletion after approval. A file rewritten over NFS while the run waited for approval became `CHANGED` and was not deleted. A rejected approval deleted nothing. Restore with `Expedited` (including the 5.5 GiB file) and equal SHA-256 for the 6 restored files (the seventh of the 7 files had been rewritten, so it was neither deleted nor restored). Restoring uid, gid, mode and mtime with `reapply.sh` |
| Checked once each in the exclusion-and-approval run (2026-11-26, same environment, `GLACIER`, second copy on. Dry run with `selection=ATIME`, real run with `selection=MTIME` and attributes from ONTAP REST. Files from 64 B to 1 MiB and one 51 GiB sparse file) | Items not covered by the seven-file run including 5.5 GiB. With `maxFiles=50`, three 64 B files and one 131,071 B file fell below the minimum size and a 131,073 B file stayed. `*.vmdk` and a legal-hold prefix were excluded. The 51 GiB sparse file was recorded as `SKIPPED_TOO_LARGE` and not copied. A reused `runId` and a real-run input without `requestedBy` stopped as input errors. An approval with the same ARN as the starter ended `APPROVAL_REFUSED` and nothing was deleted. Invoking the `delete` function directly without approval returned `NOT_APPROVED` and deleted nothing. With a different approver 3 files were deleted and the 1 file rewritten during the wait stayed as `CHANGED`. After the restore, 3 files were `RESTORE_VERIFIED`. Alarms published to the KMS-encrypted topic |
| Checked once each in the direct-invocation check (2026-11-26, same account and Access Point, `selection=MTIME`, `GLACIER`, no Fargate, eight 256 KiB files, `MapConcurrency=1`) | Stopping the execution right after the approval left `APPROVED` items. Calling the `delete` function directly on them returned `NOT_APPROVED` both with another execution's `claim` (`approval not current`) and with the stopped execution's own ARN as the `claim` (`claiming execution is not running`), and nothing was deleted. `reconcile` returned the remaining items to `VERIFIED`. A normal delete in a running execution turned every approved item `DELETED`. The task token parameter was gone after an approval and after a rejection. The token had been encrypted with the stack's KMS key |
### Environment and results per step
The environment is ap-northeast-1, first-generation FSx for ONTAP `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, a volume with UNIX security style, and an Access Point whose file system user is UNIX root. The date is 2026-11-26 (times are Japan Standard Time), and each step was run once. The configuration was `selection=ATIME`, `GLACIER`, a second copy, and Fargate on arm64 with 2 vCPU and 8 GiB. The data was 6 small files (three of 64 B and three of 8 MiB, owner 1234:5678, mode 640, mtime and atime 2020-01-02) and one file of 5,905,580,032 B.
| Step | Result | Duration |
|---|---|---|
| 1. Deploy | Succeeded | |
| 2. Dry run (`dryRun=true`) | Succeeded. All 7 files `VERIFIED` (SHA-256 equal for 6, CRC64NVME equal for 1), and the second copy also `VERIFIED`. 0 bytes deleted, and all 7 files remained over NFS | 244 s (including about 70 s waiting for approval) |
| 3. Rewrite while waiting for approval | One file was overwritten over NFS with 4 KiB of the same size (mtime updated). After approval it became `CHANGED` (ETag or size differs) and was not deleted | |
| 4. Real run (`dryRun=false`) and approval | 6 files `DELETED`, 1 file `CHANGED`. `bytesDeleted` was 5,922,357,440. Over NFS the 6 files were gone and only the rewritten file remained | 310 s (172 s until the approval request, about 6 s from approval to completion) |
| 5. Restore (`tier=Expedited`, `days=1`) | 6 files `RESTORED` (including the 5.5 GiB file). SHA-256 equal for all 6 to the value recorded over NFS before step 1. The `CHANGED` file was not a target | 287 s (the 5 small files in about 2.5 minutes; the 5.5 GiB Fargate copy took 2 min 38 s) |
| 6. Approval rejected (`send-task-failure`) | The execution ended as `REJECTED_OR_TIMED_OUT`, 3 files stayed `VERIFIED`, `deletedBy` was empty, and all 3 files remained over NFS | 16 s |
| Extra: hashing 5.3 GB (about 4.94 GiB) in Lambda | `VERIFIED` (SHA-256 equal to the NFS value), and the second copy also `VERIFIED` | `record` function 69.8 s (2048 MB configured, 152 MB used) |
| Extra: duplicate restore request | The second request returned HTTP 409 `RestoreAlreadyInProgress`. The Step Functions SDK integration returns it as `S3.S3Exception` | |
All resources were removed afterwards, and the removal was confirmed by reading them back.
### Usage (one run each, not a bill)
| Run | Files | Duration | State transitions (parent + child Map executions) | Fargate tasks |
|---|---|---|---|---|
| Dry run | 7 | 244 s | 12 + 107 = 119 | 2 (hash and copy 96 s, second copy 35 s) |
| Real run | 7 | 310 s | 13 + 114 = 127 | 2 (94 s, 35 s) |
| Restore | 6 | 287 s | 4 + 103 = 107 | 1 (156 s) |
| Rejection | 3 | 16 s | 10 + 45 = 55 | 0 |
- Total Lambda duration (CloudWatch; includes failed invocations, excludes the 4.94 GiB run): `select` 13 invocations 5.9 s, `ontap_rest` 11 invocations 13.4 s (2 failed), `record` 17 invocations 11.7 s, `ledger` 34 invocations 9.1 s, `approval` 6 invocations 4.3 s, `delete` 7 invocations 5.6 s, `summarize` 5 invocations 5.1 s, `restore` 26 invocations 9.2 s
- Fargate: 5 tasks, about 416 s in total (2 vCPU, 8 GiB, arm64). DynamoDB (on-demand): 68.5 RCU read and 74 WCU written, totalled over all runs
- S3 request counts were not measured (request metrics were not enabled)
State transitions in the exclusion-and-approval run (2026-11-26, small files, second copy on, `MapConcurrency=2`), one run each; they vary with file size and path.

| Execution | Files | Duration | State transitions (parent + child Map executions) | Per file |
|---|---|---|---|---|
| dry run | 4 | 66 s (including about 20 s of approval wait) | 12 + 60 = 72 | 18 |
| real run (3 deleted, 1 `CHANGED`) | 4 | 45 s (including the approval wait) | 14 + 64 = 78 | 19.5 |
| restore (Expedited, with verification, 1 `EXISTS`) | 4 | 192 s | 4 + 52 = 56 | 14 |
### Deployment and operating prerequisites
The template and the script that builds the policies are written to meet these conditions. Check them when changing the template or moving the design to another mechanism.
| # | Condition | Symptom when it is not met | How the pattern handles it |
|---|---|---|---|
| 1 | With `selection=ATIME`, the archive state machine's role can invoke the ONTAP REST function | The selection step fails | The role has `lambda:InvokeFunction` |
| 2 | The ONTAP REST function can handle the certificate on the FSx for ONTAP management endpoint, which is not signed by a public CA | Always verifying TLS fails with `CERTIFICATE_VERIFY_FAILED` | Parameter `OntapVerifySsl` (default `false`). While it is `false`, the ONTAP credentials are sent over a connection that does not authenticate the peer (the path stays inside the VPC) |
| 3 | A duplicate restore request is treated as a restore in progress. It returns HTTP 409 `RestoreAlreadyInProgress`, and the Step Functions SDK integration returns it as `S3.S3Exception` | A `Catch` for `S3.RestoreAlreadyInProgressException` does not match, and the file fails | `S3.S3Exception` is caught and routed to the wait loop |
| 4 | The state machine roles can configure the log destination | The deploy fails with `The state machine IAM Role is not authorized to access the Log Destination` | The roles have `logs:CreateLogDelivery` and the related permissions |
| 5 | The `delete` and `restore` functions have `s3:ListBucket`. For a caller without it, `HeadObject` on a missing key returns 403, not 404 | A retry after deletion and `reconcile` fail with 403 | `s3:ListBucket` is allowed in both IAM and the Access Point policy |
| 6 | CloudWatch alarms can publish to the KMS-encrypted topic. Both the key policy and the topic policy need to allow `cloudwatch.amazonaws.com` | Alarm notifications fail with `CloudWatch Alarms is not authorized to perform: SNS:Publish` | Both policies carry the statement |
| 7 | The state machine role has `events:PutRule` and the related permissions that `ecs:runTask.sync` states need. Without Fargate (`FargateImageUri` empty) the definitions still contain these states, so they are checked at creation | The deploy fails with `is not authorized to create managed-rule` | The permissions sit outside the `UseFargate` condition |
### Behaviors confirmed in the end-to-end runs
The pattern's design relies on these behaviors.
- With `selection=ATIME`, the pattern's own reads update `accessed_time`. After one run with `dryRun=true`, the hashing read sets each file's atime to the run time, so the same input with `dryRun=false` selects nothing (it ended with 0 files when the real run followed the dry run). Use `selection=MTIME` to run the real job on the same candidates right after a dry run (`LastModified` is not changed by reads)
- On the ETag, the official wording and the measurement here are these. The official page ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), read 2026-11-26) says "The ETag reflects changes only to the contents of an object, not its metadata". In one measurement in this environment, three files with the same size and mtime and different contents returned the same ETag. The pattern therefore treats the ETag-and-size check before deletion as unable to detect a content change that keeps size and mtime. A same-size rewrite that updated mtime during the approval wait was detected (step 3 of the seven-file run including 5.5 GiB, and the real run of the exclusion-and-approval run) [E-023]
- Deleting the last file in a directory through the Access Point also removes the now-empty parent directory (seen in the exclusion-and-approval run). The restore `CopyObject` recreates it
- Restored files had owner 0:1, mode 644, and the restore time as mtime. Running the generated `reapply.sh` as root on a host that mounts the volume over NFS put back the original uid, gid, mode and mtime (1234:5678, 640, 2020-01-02 03:04:05) without changing the SHA-256 of the contents
- The restore state machine also selects a file left as `CHANGED` when the archive bucket holds its copy. If the Access Point already has the key, it is left as `EXISTS` and not overwritten (seen once in the restore of the exclusion-and-approval run)
- The `Expedited` restore request for the 5.5 GiB file was accepted and completed within about 4 minutes
### Not checked
- Duration and cost with many files. File system throughput and client latency at other concurrency settings
- Waiting for `Standard` and `Bulk` restores (only `Expedited` was run)
- Retries on `S3.SlowDownException` (the name the SDK integration returns was not observed; the same kind of mismatch as prerequisite 3 may occur)
- Deletes and approvals in CloudTrail data events. S3 data events (`DeleteObject` and others) are recorded only when a trail has data events enabled. This run did not check whether the account's trail includes data events for this Access Point. `SendTaskSuccess` is a management event; its record was not checked either
- The refusal and the acceptance of an approval were compared with the same SSO principal declaring different ARNs in the approval output. The approver value is declared, so a different IAM principal should give the same result, but a real second principal was not used
- Copying and restoring files above 50 GiB (only leaving them out of the selection was checked, with a sparse file)
- NTFS volumes, non-root users, second generation, Multi-AZ
- In restore, the `EXISTS` path other than not selecting `CHANGED` files (a file with the same name on NFS)
- Waiting until `ApprovalPendingAlarm` actually goes to `ALARM` (only that the metric is published was checked)
- One case of zero candidates remains unexplained. A run about 10 seconds after resetting atime with `touch -d` returned no candidates. A check about 17 minutes later returned the 2020 values, and other checks also returned 6 files. The cause was not identified and it did not recur
- A run on real hardware of the delete retry and resume path (`DELETING` with the same `claimedBy`). This path is covered by unit tests only
### Remaining write window before deletion
One write window remains in the check before deletion. The Access Point's `DeleteObject` does not support conditional deletes, so a write between the `HeadObject` check and the delete is not detected. The window is one API round trip.
## Flow
### Archive
`olderThanDays` is required. `dryRun` defaults to `true`. A run with `dryRun=false` needs the starting principal's ARN in `requestedBy` when `RequireSeparateApprover=true` (default).
| Step | Processing | Implementation |
|---|---|---|
| 1. Select | `MTIME`: `LastModified` from the Access Point's `ListObjectsV2`. `ATIME`: `accessed_time` from the ONTAP REST API (Lambda inside the VPC). Apply the exclusions (table below) | `select`, `ontap_rest` |
| 2. Record | Size, ETag, SHA-256, CRC64NVME, and uid, gid, mode, mtime, atime where available, into the ledger. Lambda up to 5 GiB, Fargate above | `record`, Fargate task |
| 3. Copy | Up to 5 GiB: the SDK integration's `copyObject` (`SHA256`, the ledger's ETag as `CopySourceIfMatch`). Above: Fargate multipart copy (`CRC64NVME`) | Step Functions, Fargate |
| 4. Verify | Compare size and checksum from the bucket's `HeadObject` (`ChecksumMode=ENABLED`) with the ledger. A mismatch stays as `MISMATCH` and leaves the delete set | `ledger` |
| 5. Second copy (optional) | Copy from the Access Point to another bucket in the same Region and verify the same way. A mismatch leaves the delete set | Step Functions, `ledger` |
| 6. Approve | Write the matching list to `manifests/<runId>.json`, notify through SNS, wait with `waitForTaskToken`. The notification says so when there is only one copy and when files cannot be restored | `approval` |
| 7. Record the approval | Only when `dryRun=false`. Refuse when the approver is the starter. Otherwise move each listed file from `VERIFIED` to `APPROVED` in the ledger and write `manifests/<runId>-approval.json` | `approval` |
| 8. Delete | Only files the ledger shows as `APPROVED`. Check ETag and size per file; `DeleteObject` if unchanged, otherwise keep as `CHANGED` | `delete` |
| 9. Record | `manifests/<runId>-result.json` and EMF metrics (counts, bytes, exclusions). `COMPLETED_WITH_ERRORS` when `DELETING` or `APPROVED` items remain | `summarize` |
Even with `dryRun=true` the run goes through step 6. Copies are made and storage in the archive class is charged (with a minimum storage duration). Keep `maxFiles` small when trying it. Nothing is deleted.
Ledger statuses advance through `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED`, with exits `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE` and `RESTORE_MISMATCH`. Only `APPROVED` files (and, when a second copy is required, whose second copy is also verified) can be deleted.

A `runId` that was already used is an input error. To continue an interrupted run, give the same `runId` with `"resume": true` (see "Recovering from an interrupted delete" below). The archive key carries the `runId`, so a dry run and a real run, or a re-archive after a rewrite, do not overwrite one another's objects. Without versioning an overwrite deletes the earlier object, which can mean an early-deletion charge in classes with a minimum storage duration.

What the selection leaves out:

| Condition | Default | Why |
|---|---|---|
| Above 50 GiB | Left out and recorded as `SKIPPED_TOO_LARGE` in the ledger. `allowOversize: true` includes them | The official page ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), read 2026-11-26) says "Maximum object size is 50 GiB for uploads, but you can download objects larger than that". A restore writes through the Access Point, so this pattern cannot restore a larger file there (it can be downloaded from the bucket directly) [E-021] |
| Below `MinFileSizeBytes` | 131,072 bytes (128 KiB). The input's `minSizeBytes` changes it | According to [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare) (read 2026-11-26), Standard-IA and Glacier Instant Retrieval bill at least 128 KB per object, and Glacier Flexible Retrieval and Deep Archive add 40 KB of metadata per object (32 KB at that class's rate, 8 KB at the Standard rate). For small files that is more than the data itself |
| `ExcludePatterns` (globs), `ExcludePrefixes` | `ExcludePatterns`: the list below; `ExcludePrefixes`: empty | The stack's values always apply; the input's `excludePatterns` and `excludePrefixes` can only add. Put legal-hold prefixes here |

Always exclude data files of Iceberg, Delta or Hive tables, files of a running database, and VM disk images (`*.vmdk`, `*.vhd`, `*.qcow2` and the like). The pattern moves files one at a time and knows nothing about table metadata or the process that holds a file open. Tidy a table with the table's own features (detach partitions, expire snapshots) and target only the paths left after that. Whether something is under legal hold is your legal team's decision; the pattern does not make it.
The default of `ExcludePatterns` is a starting point, not a complete list; it names file types that commonly cause real damage. VM disk images (`*.vmdk`, `*.vhd`, `*.vhdx`, `*.vdi`, `*.qcow2`) are written continuously while the VM is open, so a file-by-file copy is a broken copy. Database data and log files (SQL Server `*.mdf`, `*.ndf`, `*.ldf`; MySQL InnoDB `*.ibd`; Oracle `*.dbf`) are held open and written by the database. Table-format metadata directories (Delta `_delta_log/`, Hudi `.hoodie/`, Iceberg `metadata/`) list the data files, so moving only the data files breaks the table. Matching is case-sensitive (`*.VMDK` does not match). A directory named `metadata/` that is not an Iceberg table is excluded too. Table data files such as `*.parquet` are not in the default; add the patterns that fit your volume. Set the parameter to empty only if the volume holds none of these.
### Restore
The input is `runId` and exactly one of `keys` or `prefix`. `tier` (default `Bulk`) and `days` (default 7) are optional.
1. Select `DELETED` files from the ledger. `DELETING` and `CHANGED` files are selected too when the archive bucket holds their copy (so items left by an interrupted delete can be restored)
2. If the Access Point already has the key, leave it as `EXISTS` and do not overwrite
3. Request `RestoreObject` for S3 Glacier Flexible Retrieval and S3 Glacier Deep Archive objects (not needed for S3 Glacier Instant Retrieval)
4. Waiting is by polling (read the `Restore` header from `HeadObject` every `RestorePollMinutes`, give up after `RestoreMaxWaitHours`). EventBridge `Object Restore Completed` is not used; the bucket's EventBridge notifications are on, so this can be switched later
5. `CopyObject` from the bucket back to the Access Point (Fargate above 5 GiB). The ledger says `RESTORED`
6. Read the restored file back through the Access Point, hash it, and compare with the ledger's SHA-256, CRC64NVME and size (Fargate above 5 GiB). A match is `RESTORE_VERIFIED`, a difference `RESTORE_MISMATCH`
7. Write the attribute reapply script `manifests/<runId>-reapply.sh`, for `RESTORE_VERIFIED` files only

Restored files had owner 0:1, mode 644, and the restore time as mtime (checked in the environment above). `CopyObject` does not restore the original values.
A `RESTORE_MISMATCH` file is not selected for restore by default: its copy on the Access Point did not match the ledger, and selecting it would leave it as `EXISTS`. To redo it, add `"retryMismatched": true` (a JSON boolean) to the restore input. Only then are the items that the ledger of that `runId` currently shows as `RESTORE_MISMATCH` selected, and the mismatched copy on the Access Point is overwritten with the bucket's copy. Items in any other status never overwrite an existing file, with or without the flag. After the overwrite, the same read-back ends in `RESTORE_VERIFIED` or `RESTORE_MISMATCH`.
### Recovering from an interrupted delete
A Lambda that stops mid-delete or exhausted retries can leave items as `DELETING` or `APPROVED` in the ledger. The result shows this as `COMPLETED_WITH_ERRORS`, `stuckDeleting` and `notDeleted`, and `FilesStuckDeletingAlarm` fires. Starting the archive state machine with the same `runId` and `"resume": true` runs `reconcile`, which settles the items as below, then asks for a new approval for the files that remain.
| Ledger | Access Point | Result |
|---|---|---|
| `DELETING` | No file | `DELETED` (the delete had happened; `reconciled: true`) |
| `DELETING`, `APPROVED` | File present, ETag and size equal the ledger | Back to `VERIFIED`; deleting needs a new approval |
| `DELETING`, `APPROVED` | File present, differs from the ledger | `CHANGED` |
| Either | The execution that holds the item is still running | Left alone |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
When an item left as `DELETING` has to be brought back, the restore state machine restores it from the archive bucket's copy.
## Approval
The notification does not contain the task token. The token is in a Systems Manager Parameter Store SecureString (`/<stack>/approvals/<runId>`). An approver is someone with permission to read that parameter and to call `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# Reject:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
After approval, the `approval` function compares `approver` with the `requestedBy` of the start input (`RequireSeparateApprover=true`, default). The same principal ends the run as `APPROVAL_REFUSED` without marking anything `APPROVED`. A role ARN and a session ARN of that role count as the same principal. Otherwise each listed file becomes `APPROVED` in the ledger with `approvedBy`, `approvedAt` and the execution ARN. The `delete` function deletes only files with this record; invoking it directly deletes nothing that lacks one.

`approver` and `requestedBy` are both declared by the callers. The ledger's `deletedBy` is taken from its `approvedBy`. The principals that actually started and approved are in CloudTrail's `StartExecution` and `SendTaskSuccess` events. To guarantee separation of duties per principal, separate the starting and approving roles in IAM. The comparison of starter and approver compares two declared values. It does not enforce that a different principal approved, and this document does not claim that it does. The control after the fact is CloudTrail's `userIdentity`: match the principals that ran `StartExecution` and `SendTaskSuccess`.
### Approval validity and the task token
The `delete` function deletes only items whose ledger status is `APPROVED`, whose `approvalExecutionArn` equals the current execution, and whose `approvedAt` is within `ApprovalValidityHours` (default 24 hours). If an execution is stopped after the approval, the `APPROVED` items remain, but they do not match another execution's `claim`, so calling the `delete` function directly returns `NOT_APPROVED`. An approval older than the window is refused the same way. `reconcile` returns the remaining items to `VERIFIED`. A `claim` that is the stopped execution's own ARN (the ledger shows it) is refused too unless that execution is `RUNNING`. The call is also refused when the execution's state cannot be read.

The task token is deleted when the approval is accepted (the `approval` function), when an approval by the starter's own principal is refused, and after a rejection, a timeout or a failed execution (`summarize`). A token left behind by an execution that never reached `summarize` is deleted by `watchdog` once it is older than the approval timeout plus one hour. The token is encrypted with the stack's customer-managed KMS key (output `ApprovalTokenKeyArn`), so reading it takes `ssm:GetParameter` and `kms:Decrypt` on that key.

An example IAM policy for the approver role. IAM cannot scope `states:SendTaskSuccess` and `states:SendTaskFailure` to a resource ([Step Functions authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsstepfunctions.html), viewed 2026-11-26) [E-024], so they cannot be limited to this state machine's executions. Whoever holds the token can answer that execution, so what can be narrowed is the path to the token. Do not give this role `StartExecution`.
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApprovalToken",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/<stack>/approvals/*"
    },
    {
      "Sid": "DecryptApprovalToken",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "<ApprovalTokenKeyArn>",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.<region>.amazonaws.com"}}
    },
    {
      "Sid": "ReportApproval",
      "Effect": "Allow",
      "Action": ["states:SendTaskSuccess", "states:SendTaskFailure"],
      "Resource": "*"
    }
  ]
}
```
## Reapplying attributes
At the end of a restore, `manifests/<runId>-reapply.sh` is written. Run it as root on a host that mounts the volume over NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
The script contains only `chown`, `chmod` and `touch -d`. Ledger values are checked against strict formats, and each key is made a single shell word by quoting. A value that does not match becomes a comment and is not executed. Whether the ONTAP REST API can set owner, group, mode and modification time has not been verified, so that route is not implemented.
## Deployment
### Prerequisites
- Both the alias and the ARN of the Access Point (IAM needs both forms; a policy with only the alias deploys but is denied at run time)
- An Access Point policy. This stack does not create the Access Point (it takes an existing one as a parameter) and does not manage its policy, so attach it after the deploy as shown below. Without it the first S3 call is denied at run time
- A name for the archive bucket (the stack creates it: `DeletionPolicy: Retain`, Block Public Access, SSE-S3 by default, optional KMS, EventBridge notifications on, TLS required)
- Only for `selection=ATIME` and attribute capture: VPC, subnets, a secret with the ONTAP credentials, the management endpoint, the volume UUID, `OntapVerifySsl`. The FSx for ONTAP management endpoint's certificate is not signed by a public CA, so the default is `false` (no verification). In that mode the ONTAP credentials travel over a connection whose peer is not authenticated (the path stays inside the VPC). With `true` verification fails and the run stops at selection (seen on a live system). The VPC Lambda needs a route to Secrets Manager and S3 (VPC endpoints or NAT)
- Only for files above 5 GiB: an image in ECR. The Access Point is Internet-origin, so the Fargate subnets need a NAT gateway or a public IP
- A confirmed notification subscription. An SNS email subscription does nothing until the recipient clicks the confirmation link; without it nobody sees the approval request
### Steps
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # replace every <PLACEHOLDER>
sam build && sam deploy
```
After the deploy, attach the Access Point policy. The script renders, from the role ARNs in the stack outputs, a policy that grants `s3:DeleteObject` to the `delete` function's role only and `s3:PutObject` to the restore roles only.
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # no PendingConfirmation left
```
If the Access Point already has a policy this replaces it; merge the existing statements first.
For Fargate, build the image from the repository root, push it to your own ECR repository, and set `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Run first with `dryRun` omitted (that is, `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
To delete, pass `"dryRun": false` as a JSON boolean and put the starting principal in `requestedBy`. The string `"false"` is an input error and nothing is deleted.
## Directory layout
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, ledger, 9 Lambda functions, 2 state machines, Fargate (optional), alarms
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
The domain logic (checksums, input validation, ledger, verification after restore) is in [`shared/archive_verify/`](../../../shared/archive_verify/) and tested in `shared/tests/`. Access Point reads and writes go through `shared/s3ap_helper.py`.
## Local tests
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
To confirm that a broken delete decision is caught, `test_does_not_delete_when_etag_changed` and `test_does_not_delete_when_size_differs_but_etag_equal` were run once against a stub with the ETag comparison removed; both failed with `assert 'DELETED' == 'CHANGED'`. The approval-record check and the 50 GiB exclusion were written test-first and run once against the earlier code, failing with `assert 'DELETED' != 'DELETED'` and `KeyError: 'skippedTooLarge'`, before they were implemented.
## Success Metrics
### Outcome
Move rarely read files to S3 Glacier storage classes after verification and human approval, reduce the volume's used capacity, and be able to find and restore moved files from the ledger.
### Metrics
Target values are yours to set; none are given here.
| Category | Metric | Definition |
|---|---|---|
| Business Outcome | Capacity freed | Difference in volume used space before and after the run (after snapshots are tidied). `bytesDeleted` (`-result.json`) is the total size of deleted files, not the space freed: while snapshots remain the volume's usage does not fall, and for compressed or deduplicated data less space is freed than the logical size |
| Business Outcome | Expected monthly storage saving | (GB moved off the capacity pool × price difference) − (archive class storage, per-object overhead, retrieval charges). Prices: see "Cost estimation" below |
| Technical KPI | Verification match rate | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Files not deleted | Sum of `CHANGED`, `MISMATCH` and `FAILED` |
| Technical KPI | Restore verification match rate | `RESTORE_VERIFIED` ÷ (`RESTORE_VERIFIED` + `RESTORE_MISMATCH`) |
| Quality KPI | Files deleted without approval | Must be 0. Count `DELETED` items with an empty `approvedBy` or `approvedAt` |
| Cost KPI | Lambda, Fargate, DynamoDB, S3 requests, state transitions and archive class storage per run | Estimate with the formula in "Cost estimation" from a measured `dryRun=true` run with a small `maxFiles` |
| Go / No-Go | Technical: in a run on the real environment, every copied file is `VERIFIED`, a deliberately created `CHANGED` file is not deleted, a self-approval by the starter is refused, restored files are `RESTORE_VERIFIED`. Business: the expected saving exceeds the operating cost (approval effort, handling restore requests); the entry point and target response time for restore requests (including the class's restore time) are decided; users have been told | Do not use `dryRun=false` on a production volume until all are met. Name who decides each (data owner, approver, operations owner) first |

PoC planning and pre-production checks are in the FSx for ONTAP Adoption Playbook's [pre-production review checklist](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md) and [pre-migration inventory](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md) (both in Japanese). For this pattern's PoC, raising `maxFiles` through 20, 200 and 2,000 while recording parent duration, state transitions and Fargate seconds gives per-file values. A PoC plan table is in the section on getting started in your own environment of the Playbook's [archive use cases and integrations note](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/archive-use-cases-and-integrations.md) (in Japanese).
### Measurement Method
Step Functions execution history and logs (`/aws/vendedlogs/states/<stack>-archive` and `-restore`, without execution data), `manifests/<runId>-result.json`, `manifests/<runId>-approval.json`, CloudWatch EMF metrics (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `FilesStuckDeleting`, `BytesVerified`, `BytesDeleted`, `RestoreVerified`, `RestoreMismatch`, `ApprovalPendingHours`), and the ledger.

Alarms (all to the notification topic):

| Alarm | Condition |
|---|---|
| `ArchiveExecutionsFailedAlarm`, `RestoreExecutionsFailedAlarm` | One or more failed, timed-out or aborted executions in 5 minutes |
| `ApprovalPendingAlarm` | An approval request has waited longer than `ApprovalAlarmHours` (default 24) |
| `FilesStuckDeletingAlarm` | A run ended with `DELETING` or `APPROVED` items |
| `FilesMismatchAlarm` | An archived copy did not match (`MISMATCH`) |
| `RestoreMismatchAlarm` | A restored file did not match the ledger |
The notification topic is encrypted with a customer managed KMS key. The AWS managed key (`alias/aws/sns`) has a key policy that cannot be edited, and EventBridge and CloudWatch alarms can publish to an encrypted topic only with a customer managed key that allows the service principals `kms:GenerateDataKey*` and `kms:Decrypt` ([Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html), read 2026-11-26). The second run confirmed that EventBridge failure notifications and alarm notifications arrive. [E-022]
## Performance Considerations
The default concurrency is based on the one measurement below. The rest are design factors and were not measured.
- Each source file is read twice: once through the Access Point for hashing, and once server-side by `CopyObject`. Read requests are charged, and data in the capacity pool also incurs capacity pool read charges
- Concurrency is `MapConcurrency` (default 1, for both archive and restore). In one measurement a Lambda function read 5.3 GB (about 4.94 GiB) through the Access Point in 69.8 seconds, about 76 MB/s on one stream, which is about 60% of this environment's 128 MBps throughput capacity. Two streams would be about 152 MB/s, above that capacity. Each file is read twice and the same volume serves your users, so the default is 1. Parallel reads were not measured. Before raising it, watch the file system's `DataReadBytes` and client latency during a run
- The 5 GiB default for `LargeFileThresholdBytes` follows from the single-request `CopyObject` limit. At the speed above Lambda's 15 minutes would cover about 63 GiB, but that is one data point
- The listing loads every `ListObjectsV2` result into one Lambda's memory. Split with `prefix` beyond a few million objects
- `selection=ATIME` walks directories depth-first. The scan limit is 200,000 entries (`ONTAP_SCAN_LIMIT`); past it, partial results are returned
- Restore waiting time depends on the class and `tier`. AWS documents S3 Glacier Deep Archive as within 12 hours for Standard and 48 hours for Bulk. `RestoreMaxWaitHours` defaults to 72. For classes with long waits, a larger `RestorePollMinutes` means fewer polling transitions
- Fargate tasks are bounded by `FargateTimeoutSeconds` (default 7200 s). Every Task has a `TimeoutSeconds`, and a timeout is retried
## Cost estimation
No bill was measured. Below are measured usage values and published per-object terms to estimate from.
State transitions per file in the two runs (one run each):

| Execution | State transitions per file | Source |
|---|---|---|
| Archive dry run | 17 (119 ÷ 7), 18 (72 ÷ 4) | The seven-file run including 5.5 GiB; the exclusion-and-approval run |
| Archive real run (including deletes) | 18 (127 ÷ 7), 19.5 (78 ÷ 4) | Same |
| Restore (`Expedited`; the exclusion-and-approval run with verification) | 18 (107 ÷ 6), 14 (56 ÷ 4) | Same |
Classes with long waits add transitions with every poll.
Per-object storage terms ([Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare), read 2026-11-26):

| Class | Minimum storage duration | Per-object overhead, minimum billable size |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 days | Minimum billable object size 128 KB |
| S3 Glacier Flexible Retrieval | 90 days | 40 KB of metadata (32 KB at this class's rate, 8 KB at the S3 Standard rate) |
| S3 Glacier Deep Archive | 180 days | 40 KB of metadata (same split) |
Formula: monthly cost ≈ files × transitions per file × price per transition + Lambda and Fargate duration × price + files × (request prices for `CopyObject`, `HeadObject`, `DeleteObject` and the like) + storage (data + files × overhead) × class price + retrieval charges when restoring. Take prices from [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) and [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) for your Region and date; none are written here.
## Governance Note
> This pattern provides technical architecture guidance. It is not legal, compliance or regulatory advice. Consult qualified professionals.
- Verification results and the approval are assistive signals for a person's final decision. No AI is used
- The pattern does not meet retention or immutability requirements. Object Lock and similar features are not used, so anyone with permission can delete
- Output classification: the ledger and manifests contain file paths, sizes, hashes and attributes. A path can contain a person's name or a patient or case identifier, so outputs carry `data_classification` `RESTRICTED` by default ("Restricted — Limited access" in `shared/data_classification.py`). When the data's own classification is stricter, set the `DataClassification` parameter to it. You decide the classification. File contents go to the archive bucket; treat them as the original data is classified
- Human Review: approval is required for every run. There is no confidence-based auto-approval. By default, nothing is deleted when the starter and the approver are the same principal. This compares declared values and is not proof of identity; CloudTrail `userIdentity` is the after-the-fact control
- IAM: only the `delete` function's role holds `s3:DeleteObject` on the Access Point, and only the restore state machine and the restore Fargate task role hold `s3:PutObject` there. The archive Fargate task only copies and can neither delete nor overwrite source files. No principal can delete ledger items
- Audit: approvals and deletes are recorded in the ledger (`approvedBy`, `approvedAt`, `requestedBy`, `deletedBy`, `deletedAt`), `manifests/<runId>-approval.json`, and Step Functions history and logs. CloudTrail records the deletes only when a trail has S3 data events enabled; this was not checked in the run
- Number of copies: without a second copy, the archive bucket's object is the only copy after deletion. The approval notification says so
## Constraints and unverified items
- A direct copy from the Access Point to a bucket in another Region returned `AccessDenied` (one Access Point, once). The second copy only targets buckets in the same Region
- Checked on a UNIX-style volume. A content change that keeps size and mtime is not detected by the ETag-and-size check (see "Behaviors confirmed in the end-to-end runs"). Whether `chown` changes the ETag was not checked
- Attribute capture uses directory listings, reading the whole parent directory for one file; large directories are slow
- Versioning on the archive bucket is not Object Lock. Versions remain, but anyone with permission can delete them
- Files above 50 GiB are not selected by default. If included with `allowOversize: true`, they cannot be restored to the Access Point; download them from the bucket
- `requestedBy` and `approver` are declared values. Check separation per principal with IAM and CloudTrail
## Related documents
- [Architecture](docs/architecture.en.md)
- [S3 Access Points compatibility notes](../../../docs/s3ap-compatibility-notes.md)
- [Comparison of 9 mechanisms for moving files to archive classes](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (in Japanese)

---

<!-- playbook-reading:start -->
## Read before going to production

How the constraints that surface after deploying translate into design decisions is covered in the [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). The same content in two places means the copy that stops being updated outlives the one that was corrected.

- [Data Utilization](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — constraints of reaching data through an access point (every pattern)
- [Data Protection](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — where the decisions concentrate for this pattern
- [Build](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — run through before production (every pattern)
<!-- playbook-reading:end -->
