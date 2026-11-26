# archive-verify-delete: Archive with S3 API Calls Only: Copy, Verify, Delete After Approval
🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Overview
This pattern moves rarely read files on an Amazon FSx for NetApp ONTAP (FSx for ONTAP) volume to S3 Glacier storage classes. The volume is not mounted. Only S3 API calls through S3 Access Points are used.
One file moves through the steps below, and a file whose conditions fail along the way is left out of deletion.
1. Record its size, ETag, SHA-256 and CRC64NVME in the ledger (a DynamoDB table)
2. Copy it to the archive bucket with `CopyObject`, specifying the storage class
3. Compare the checksum the bucket returns with the ledger value
4. A person approves the list of files that matched
5. Check that the Access Point's ETag and size equal the ledger values, then delete the file from the Access Point

To restore, find the file in the ledger, request a restore in the bucket, wait for it to complete, and copy it back to the Access Point with `CopyObject`.
This pattern does not use S3 Object Lock, S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock or snapshot locking, and the template contains none of them. No retention period is set, so objects in the archive bucket can be deleted by anyone with permission.
The premises of this pattern and its comparison with other approaches are in [Comparison of 8 mechanisms for moving files to archive classes](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (in Japanese).
## What was measured and what was not
| Category | Content |
|---|---|
| Components checked once each on a real system (recorded in the comparison above; 2026-11-24 and 2026-11-26, ap-northeast-1, first-generation `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, UNIX-style volume, Access Point user is UNIX root) | With `ChecksumAlgorithm=SHA256` on `CopyObject`, the bucket's `ChecksumSHA256` was `FULL_OBJECT` and equal to the file's SHA-256 (up to 8 MiB). For a 5.5 GiB multipart copy, SHA-256 became `COMPOSITE` and CRC64NVME was `FULL_OBJECT` and equal. `--copy-source-if-match` with an old ETag returned `PreconditionFailed`. The Access Point's `DeleteObject` does not support `If-Match`. A Step Functions SDK integration accepted the Access Point alias as `Bucket` |
| Checked in this repository | Unit tests with moto, and tests of the state machine and IAM structure. No connection to AWS. Three defects found in the end-to-end run above (invoke permission for the ONTAP REST function, TLS verification, the error name of a duplicate restore request) were fixed with tests that reproduce them |
| Checked once each in an end-to-end run on a real system (2026-11-26, same environment as above, `selection=ATIME`, `GLACIER`, 7 files) | Selection by `accessed_time` and capture of uid, gid, mode, mtime and atime through the ONTAP REST API (the root is the volume root and the path has no leading slash; `unix_permissions` comes back as the integer `640`). The Distributed Map `ItemReader` and `ResultWriter`. A 5.5 GiB Fargate multipart copy (with `CopySourceIfMatch`; CRC64NVME equal to the ledger). Hashing of a 5.3 GB (about 4.94 GiB) file in Lambda (69.8 s, 2048 MB configured, 152 MB used). The second copy. Deletion after approval. A file rewritten over NFS while the run waited for approval became `CHANGED` and was not deleted. A rejected approval deleted nothing. Restore with `Expedited` (including the 5.5 GiB file) and equal SHA-256 for the 6 restored files (the seventh of the 7 files had been rewritten, so it was neither deleted nor restored). Restoring uid, gid, mode and mtime with `reapply.sh` |
| Not checked yet | Duration and cost with many files. Completion of `Standard` and `Bulk` restores (only `Expedited` was run). Retry on `S3.SlowDownException` (the only error name observed from the Step Functions SDK integration is `S3.S3Exception` for `RestoreAlreadyInProgress`). NTFS volumes, non-root users, second generation, Multi-AZ. CloudTrail data-event records of the deletes |
The end-to-end run showed four behaviors:
- With `selection=ATIME`, the pattern's own reads update `accessed_time`. After one run with `dryRun=true`, the hashing reads set the files' atime to the run time, so the same input with `dryRun=false` selects nothing (it ended with 0 files). To run the real pass on the same candidates right after a dry run, use `selection=MTIME` (`LastModified` does not change on read)
- Deleting the last file in a directory through the Access Point also removes the now-empty parent directory (seen with `arc-e2e/large/`). The restore `CopyObject` creates the parent again
- A restored file had owner 0:1, mode 644 and the restore time as its modification time. After running `reapply.sh` the original uid, gid, mode and mtime were back
- The run used an Access Point policy that allows each role (the roles of the `select`, `record`, `delete` and `restore` functions, the Fargate task role, and the two state machine roles). Behavior without such a policy was not checked
One write window remains in the check before deletion. The Access Point's `DeleteObject` does not support conditional deletes, so a write between the `HeadObject` check and the delete is not detected. The window is one API round trip.
## Flow
### Archive
`olderThanDays` is required in the input, and `dryRun` defaults to `true`.
| Step | Processing | Implementation |
|---|---|---|
| 1. Select | `MTIME`: `LastModified` from the Access Point's `ListObjectsV2`. `ATIME`: `accessed_time` from the ONTAP REST API (Lambda inside the VPC) | `select`, `ontap_rest` |
| 2. Record | Size, ETag, SHA-256, CRC64NVME and, when available, uid, gid, mode, mtime, atime, into the ledger. Lambda up to 5 GiB, Fargate above | `record`, Fargate task |
| 3. Copy | Up to 5 GiB: SDK integration `copyObject` (`SHA256`, the ledger ETag as `CopySourceIfMatch`). Above: Fargate multipart copy (`CRC64NVME`) | Step Functions, Fargate |
| 4. Verify | Compare the size and checksum from the bucket's `HeadObject` (`ChecksumMode=ENABLED`) with the ledger. A mismatch stays as `MISMATCH` and is left out of deletion | `ledger` |
| 5. Second copy (optional) | Copy from the Access Point to another bucket in the same Region and verify the same way. A mismatch removes the file from deletion | Step Functions, `ledger` |
| 6. Approve | Write the matched list to `manifests/<runId>.json`, notify through SNS and wait with `waitForTaskToken` | `approval` |
| 7. Delete | Only when `dryRun=false`. For each file, check ETag and size and, if equal, call `DeleteObject`. A difference stays as `CHANGED` | `delete` |
| 8. Record | `manifests/<runId>-result.json` and EMF metrics (counts, bytes) | `summarize` |
With `dryRun=true` the run still proceeds up to step 6. That means the copy is performed and storage charges for the archive class apply (S3 Glacier Deep Archive has a minimum storage duration). Use a small `maxFiles` when trying it out. Nothing is deleted.
Ledger statuses advance in the order `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETED`, `RESTORED`, with side exits `CHANGED`, `MISMATCH` and `FAILED`. Only `VERIFIED` files (including the second-copy check when a second copy is required) can be deleted.
### Restore
The input is `runId` and exactly one of `keys` or `prefix`. `tier` (default `Bulk`) and `days` (default 7) can be given.
1. Select `DELETED` files in the ledger
2. If the Access Point already has the same key, record it as `EXISTS` and do not overwrite
3. Request `RestoreObject` for objects in S3 Glacier Flexible Retrieval and S3 Glacier Deep Archive (not needed for S3 Glacier Instant Retrieval)
4. Completion is polled: every `RestorePollMinutes` the `Restore` header of `HeadObject` is read, and the wait stops at `RestoreMaxWaitHours`. The EventBridge `Object Restore Completed` event is not used. EventBridge notifications are enabled on the bucket, so this can be switched later
5. `CopyObject` from the bucket to the Access Point (Fargate above 5 GiB)
6. Set the ledger to `RESTORED` and write the attribute reapply script `manifests/<runId>-reapply.sh`

A restored file had owner 0:1, mode 644 and a modification time equal to the restore time (one check in the environment above). The original values are not restored by `CopyObject`.
## Approval
The approval notification does not contain the token. The token is in an AWS Systems Manager Parameter Store SecureString (`/<stack>/approvals/<runId>`). The approver needs permission to read that parameter and `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# Reject:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` is self-declared. The value you enter goes into the ledger's `deletedBy`, but the proof of who actually approved is the CloudTrail `SendTaskSuccess` event. If `approver` is empty, or `approved` is not `true`, nothing is deleted.
## Reapplying attributes
At the end of a restore, `manifests/<runId>-reapply.sh` is written. Run it as root on a host that mounts the volume over NFS.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
The script contains only `chown`, `chmod` and `touch -d`. Ledger values are checked against strict formats, and each key is made a single shell word by quoting. A value that does not match becomes a comment and is not executed. Whether the ONTAP REST API can set owner, group, mode and modification time has not been verified, so that route is not implemented.
## Deployment
### Prerequisites
- Both the alias and the ARN of the Access Point (IAM needs both forms; an alias-only policy can deploy and still be denied at runtime)
- A name for the archive bucket (the stack creates it with `DeletionPolicy: Retain`, Block Public Access, SSE-S3 by default, optional KMS, EventBridge notifications enabled, TLS required)
- Only for `selection=ATIME` and attribute capture: a VPC, subnets, the secret holding the ONTAP credentials, the management endpoint, the volume UUID and `OntapVerifySsl`. The certificate on the FSx for ONTAP management endpoint is not signed by a public CA, so the default is `false` (no verification), and the ONTAP credentials are then sent over a connection whose peer is not authenticated (the path is inside the VPC). With `true`, selection stopped on a certificate error (observed). A route from the Lambda function in the VPC to Secrets Manager and S3 (VPC endpoints or NAT) is needed
- Only for files above 5 GiB: an image in ECR. The Access Point is Internet-origin, so the Fargate subnets need NAT or a public IP
### Steps
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # replace <PLACEHOLDER>
sam build && sam deploy
```
To use Fargate, build the image from the repository root, push it to your own ECR repository and set `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Run first with an input that omits `dryRun` (so it is `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
To delete, pass `"dryRun": false` as a JSON boolean. The string `"false"` is an input error and nothing is deleted.
## Directory layout
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, ledger, 8 Lambda functions, 2 state machines, Fargate (optional)
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
The domain logic (checksums, input validation, ledger) is in [`shared/archive_verify/`](../../../shared/archive_verify/) and is tested in `shared/tests/`. Reads and writes to the Access Point go through `shared/s3ap_helper.py`.
## Local tests
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
To confirm that a broken delete check is detected, `test_does_not_delete_when_etag_changed` and `test_does_not_delete_when_size_differs_but_etag_equal` were run once against a stub with the ETag comparison removed; both failed with `assert 'DELETED' == 'CHANGED'`. With the check restored, 29 tests pass.
## Success Metrics
### Outcome
Move rarely read files to S3 Glacier storage classes after verification and human approval, reduce the volume's used capacity, and be able to find and restore moved files from the ledger.
### Metrics
Targets are set by the operator. No numbers are given here.
| Category | Metric | Definition |
|---|---|---|
| Business Outcome | Capacity released | `bytesDeleted` (`-result.json`). Volume usage does not fall while snapshots remain |
| Technical KPI | Verification match rate | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Files not deleted | Total of `CHANGED`, `MISMATCH` and `FAILED` |
| Quality KPI | Files deleted without approval | Must be 0. Count `DELETED` items whose `deletedBy` is empty |
| Cost KPI | Per run: Lambda, Fargate, DynamoDB, S3 requests, archive-class storage | Not measured. Estimate first with `dryRun=true` and a small `maxFiles` |
| Go / No-Go | In an end-to-end run on a real system, every copied file becomes `VERIFIED`, a deliberately created `CHANGED` is not deleted, and a restored file's SHA-256 matches | Do not use `dryRun=false` on a production volume until these are met |
### Measurement Method
Step Functions execution history, `manifests/<runId>-result.json`, CloudWatch EMF metrics (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `BytesVerified`, `BytesDeleted`), and the ledger.
## Performance Considerations
Not measured. The following are design factors.
- The source file is read twice. The first read is through the Access Point for hashing, and the second is the server-side read by `CopyObject`. Read request charges apply, and for data in the capacity pool the capacity pool read charge also applies
- Parallelism is `MapConcurrency` (default 10). Start small and adjust to the load on the Access Point and ONTAP
- Lambda's limit is 15 minutes. The read speed from the Access Point has not been measured, so it is unknown whether the default `LargeFileThresholdBytes` of 5 GiB is enough. If not, lower it; Fargate then takes more files
- The listing loads all `ListObjectsV2` results into the memory of one Lambda function. Above a few million objects, split the work with `prefix`
- `selection=ATIME` walks directories depth first. The scan limit is 200,000 entries (`ONTAP_SCAN_LIMIT`); beyond it the partial result is returned
- Restore wait time depends on the class and `tier`. AWS documents S3 Glacier Deep Archive as within 12 hours for Standard and within 48 hours for Bulk. The default `RestoreMaxWaitHours` is 72
## Governance Note
> This pattern provides technical architecture guidance. It is not legal, compliance or regulatory advice. Consult qualified professionals in your organization.
- The verification result and the approval are assistive signals for a person's final decision. No AI is used
- If retention periods or immutability are required, this pattern does not meet them. It does not use Object Lock or similar, so anyone with permission can delete
- Output classification: the ledger and manifests hold file paths, sizes, hashes and attributes (`dataClassification: operational-metadata`). File contents go into the archive bucket, so treat them with the same classification as the original data
- Human Review: approval is required for every run. There is no automatic approval based on a confidence value
- IAM: only the role of the `delete` function holds `s3:DeleteObject`. The Fargate task only copies and has no delete permission. No one is granted permission to delete ledger items
- Audit: approval and deletion are recorded in the ledger (`deletedBy`, `deletedAt`), the Step Functions execution history and CloudTrail
## Constraints and unverified items
- A direct copy from the Access Point to a bucket in another Region returned `AccessDenied` (one Access Point, once). The second copy targets a bucket in the same Region only
- Checked on a UNIX-style volume. Whether an overwrite that restores the modification time, or `chown`, is detected by the ETag has not been checked
- Attributes are read through the directory listing. Reading the whole parent directory for one file is slow for large directories
- Versioning on the archive bucket is not Object Lock. Versions are kept, but anyone with permission can delete versions too
## Related documents
- [Architecture](docs/architecture.en.md)
- [S3 Access Points compatibility notes](../../../docs/s3ap-compatibility-notes.md)
- [Comparison of 8 mechanisms for moving files to archive classes](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (in Japanese)
