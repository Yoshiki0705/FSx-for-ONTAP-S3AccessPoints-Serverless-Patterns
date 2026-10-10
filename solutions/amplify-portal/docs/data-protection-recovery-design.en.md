# Data Protection Recovery Tier — Portal Design Guide for the AWS Backup Logically Air-Gapped Vault

🌐 **Language / 言語**: [日本語](data-protection-recovery-design.md) | English

> Purpose: describe the design frame for how the AWS Backup logically air-gapped vault (hereafter "LAG vault") recovery tier attaches to this portal. The AWS facts themselves live in a separate repository (see "References" below). This guide does not re-derive the facts; it only decides the portal's attachment points and where an approval-gated restore flow sits.
>
> This is a design-only guide. It assumes the vault, Vault Lock, RAM share and multi-party approval (MPA) already exist, configured outside the portal by the governance owners.

## Audience and assumptions

This guide is for anyone designing how to add a recovery-point list and an approval-gated restore flow to this Amplify portal, which fronts the S3 Access Points of Amazon FSx for NetApp ONTAP (hereafter "FSx for ONTAP"). It assumes the portal can already list and lock ONTAP snapshots (Tamperproof, SnapLock, ARP status) but has no surface for AWS Backup recovery points or restore jobs.

## The LAG vault as a recovery tier

The LAG vault is the recovery tier for a compromise of the AWS account (the management boundary) itself. Snapshots and SnapMirror destinations inside that same boundary are within reach of a compromised AWS account or ONTAP administrator. The LAG vault stores backups in an AWS Backup service-owned account, outside the reach of ONTAP administration, so it keeps recovery points on the far side of that boundary.

What this tier protects is the availability and integrity of recovery points. It does not protect the confidentiality of data that has been read out; that is the job of other controls — access control, encryption and auditing. The portal screens state this distinction too: listing recovery points or restoring is a "get the data back" operation, not a "stop the exfiltration" one.

## Distinguishing ONTAP snapshots from AWS Backup recovery points

So a reader does not conflate the two, the portal screens and this guide keep them clearly separate.

| Aspect | ONTAP snapshots (already in the portal) | AWS Backup recovery points (not built; this guide's subject) |
|------|-----------------------------------|------------------------------------------|
| Storage location | Inside the same FSx for ONTAP file system | An AWS Backup vault (for a LAG vault, an AWS service-owned account) |
| Management boundary | Inside the ONTAP / AWS account boundary | A LAG vault is outside the boundary |
| Existing portal surface | `functions/snapshots`, `functions/data-protection` (list, lock status, ARP status, Tamperproof lock) | None |
| Expected API | ONTAP REST (`GET /api/storage/volumes/{uuid}/snapshots`, etc.) | AWS Backup (`backup:ListRecoveryPointsByBackupVault`, etc.) |
| What it protects | Recovery points against nearby tampering or accidental deletion | Recovery points against a whole-AWS-account compromise |

## Where it attaches to the portal

The portal already has the pieces to carry this recovery tier as-is. What is new is a handler that calls AWS Backup and the wiring that connects it to the existing approval and orchestration mechanisms.

- **Recovery-point list panel**: place an AWS Backup recovery-point list next to the existing snapshot list in the Data Protection section. Label it distinctly so it is not confused with ONTAP snapshots. This is a read-only surface.
- **Approval-gated restore flow**: starting a restore reuses the existing human approval (`agent-chat`'s `request_action_approval`, "safety-controller") and the existing irreversibility acknowledgement guard (`_require_ack` / `acknowledgeIrreversible`) to gather approval in stages. The restore itself activates the dormant AppSync -> Step Functions wiring (`amplify/custom/step-functions.ts`, call site commented out) and runs as a tracked execution with a human-approval wait state.
- **Restore to a new volume**: a restore always targets a new volume and never overwrites the original. This matches the referenced Option D and the LAG vault doc.

## Reusing the existing approval and guard

The portal already has the mechanisms to put irreversible operations behind human approval. The new restore flow reuses them rather than building its own.

| Existing mechanism | Where it lives | Use in the restore flow |
|------------|---------------------|------------------|
| Irreversibility acknowledgement guard | `functions/data-protection` (`_require_ack`), `functions/snapshots` (`acknowledgeIrreversible`) | Require an explicit acknowledgement, with a one-sentence consequence, when a restore is requested |
| Human approval tool | `functions/agent-chat` (`request_action_approval`, "safety-controller") | Route the request through approval before the restore job starts |
| AppSync -> Step Functions wiring | `amplify/custom/step-functions.ts` (dormant) | Orchestrate the restore execution with a human-approval wait state |

The read-only list panel needs no `acknowledgeIrreversible`. The acknowledgement guard and human approval apply only to the write and irreversible step of starting a restore job.

## Cross-Region and cross-account visibility

The recovery-point list can also target a RAM-shared vault in another account or Region. Per the referenced Option D, `aws backup list-recovery-points-by-backup-vault` takes `--backup-vault-account-id` to list from a shared recovery account. The portal list panel is designed to accept the same argument, so it can show recovery points in another account or Region and whether a restore to them is possible.

Three states are worth monitoring. The portal does not build alerting for them; it defers that to the observability side (`fsxn-observability-integrations`). The split is that the portal holds visibility and flows, while observability holds the alerting.

- Vault copy-job failures.
- "Completed with issues" (when the source file system is encrypted with an AWS managed key, the backup is not copied to the vault and the job ends in this state; registered as evidence [E-009] in the source repository).
- RAM-share revocation (the shared recovery account loses its list and restore permissions; source [E-014]).

Attach the design to the existing `docs/multi-account/ram-sharing.md` and `docs/multi-region/disaster-recovery.md`.

## Note on a vendor limitation

Among the AWS-documented facts, this guide cites the ones that bear on the design as already-registered evidence in the source repository. It does not re-derive them here.

- Malware Protection for AWS Backup does not scan FSx for ONTAP recovery points (registered as [E-008] in the source repository). Check restored contents with FlexClone and a scan through S3 Access Points.
- If the source file system is encrypted with an AWS managed key, the backup is not copied to the LAG vault and the job ends "Completed with issues" ([E-009]). Using a LAG vault assumes the source file system is encrypted with a customer managed key.
- Backups cover RW volumes only; DP, LSM, FlexCache and SnapMirror destination volumes and SnapLock FlexGroup volumes are not backed up ([E-010]).

## The deferred, irreversible boundary

This guide and the follow-on portal work do NOT do the following. Each is a decision owned outside the portal, by the governance side, and needs a disposable test environment.

- **Do not create a vault or set Vault Lock.** Vault Lock compliance mode is always on and cannot be turned off later ([E-020]). The vault encryption key is fixed at creation and cannot be changed later ([E-020]). Creating the vault is irreversible and is an out-of-portal decision owned by the account/governance side.
- **Do not configure real MPA approvers.** The MPA approval-team resources live in `us-east-1` and gate real recovery access. Wiring real approvers is a separate Issue that needs a disposable test environment.
- The portal work is limited to: a read path (list) + an approval-gated restore (requesting a restore to a new volume) + a design guide + cross-account/Region visibility. It assumes the vault, Vault Lock, RAM share and MPA are already configured elsewhere.

## The read-only list implemented in #459

#459 implements the list panel from "Where it attaches to the portal" as a read-only surface. It adds a "Recovery points" panel to the portal's Data Protection section at the same granularity as the existing ARP/AI and SnapLock features.

- **The list comes from the API.** The panel calls `ListRecoveryPointsByBackupVault` with `ByResourceType="FSx"`, so it lists only FSx for ONTAP recovery points. Both the AWS Backup console vault list and the vault detail carry a note that the displayed recovery-point count may be approximate and that the exact count comes from `ListRecoveryPointsByBackupVault` (O-1). The panel shows the API result, not that approximate count.
- **The columns are created, status, resource type, size and encryption.** Alongside these it shows the vault name and a badge marking a logically air-gapped vault (`VaultType == "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"`).
- **Status is surfaced as `Status` plus `StatusMessage`, verbatim.** The recovery-point `Status` enum is `COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED | CREATING`; "Completed with issues" is not in it. That is a copy-/backup-job state, not a recovery-point `Status`, so the panel keys no UI label on the literal "Completed with issues". Monitoring and interpreting that state is left to #461 / the observability side.
- **There is no malware-scan column.** FSx for ONTAP is out of scope for Malware Protection for AWS Backup ([E-008]), so a same-named column would mislead.
- **This panel shows no source-account-ID column and no account switcher.** The handler accepts a `backupVaultAccountId` argument for a future cross-account surface, but ships no UI that sets it. The cross-account UI is deferred to #461 and requesting a restore to #460.

## The approval-gated restore implemented in #460
#460 implements the "approval-gated restore flow" from this guide as requesting a restore to a new volume. The restore calls `backup:StartRestoreJob` to create a new FSx for ONTAP volume inside an existing file system from a selected recovery point. It is the portal's first write / irreversible AWS Backup path.
- **A restore always creates a new volume; there is no overwrite control.** The AWS Backup documentation [restoring-fsx.html](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-fsx.html) carries two statements: (1) you cannot restore to an existing Amazon FSx file system and cannot restore individual files or folders; (2) Amazon FSx for NetApp ONTAP allows restoring a volume to an existing file system. They address different targets and do not contradict. Statement (1) is about the file system as a restore target: a restore never writes into or over an existing file system's data and never restores individual files or folders. Statement (2) is a placement exception unique to FSx for ONTAP: the new resource it creates is a new volume, and that new volume may be placed into an existing file system (via the chosen SVM) rather than forcing a whole new file system. So the portal presents restore as "create a NEW volume in an existing file system", and it cannot overwrite an existing volume or restore individual files [E-011]. The rule is registered as [E-011] in the source repository.
- **It reuses the two approval gates.** The server-side hard gate is `_require_ack` (it refuses to call `StartRestoreJob` unless `acknowledgeIrreversible` is `true`), the same mechanism as `functions/data-protection/handler.py`. The UI restates the one-sentence consequence in a confirm dialog shaped like `SnaplockConfirmDialog` and takes a checkbox acknowledgement before sending `acknowledgeIrreversible: true`. A restore is additive (it creates a new volume), so a checkbox is sufficient rather than the typed keyword the SnapLock operations use. On the chat side, `request_action_approval` ("safety-controller") is the human-approval advisory before a destructive action is proposed.
- **It collects new-volume metadata only.** The form takes name (required), SVM (required, a dropdown constrained to `restoreAllowedSvmIds`), junction path (required), volume size MB (required numeric), storage efficiency (optional checkbox, default off) and tiering policy (optional dropdown, default). The existing target file system is determined by the chosen SVM (the ONTAP restore metadata has no separate file-system key). The handler checks the SVM against `ALLOWED_SVM_IDS` and refuses one outside the set.
- **On success it shows the restore job id; it does not poll.** It surfaces the `RestoreJobId` from the success response and a "track progress in the AWS Backup console or observability" line. It does not poll `DescribeRestoreJob` on a timer, which overlaps #133/#134 (Restore Job State Change ingestion).
- **The restore-job Status is a different enum from the recovery-point Status.** The restore-job `Status` is `PENDING | RUNNING | COMPLETED | ABORTED | FAILED`, distinct from the recovery-point `Status` enum used in #459 (`COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED | CREATING`). The two are not conflated.
- **The Step Functions human-approval wait state (multi-party approval) is deferred.** No human-approval (`waitForTaskToken` / manual-approval) state machine is deployed in this repository; `amplify/custom/step-functions.ts` is a dormant construct with its callers commented out. #460 gates with `_require_ack` + the confirm dialog + the chat advisory, and defers the state-machine multi-party approval to a follow-on Issue.
- **Confirming a real restore success is deferred to an Issue checkbox.** No recovery points exist in the account, so #460 ships unit tests with `StartRestoreJob`/`DescribeRestoreJob` mocked only.

## Follow-on Issues

This guide is the design frame the following three follow-on Issues implement. Each Issue maps to a part of this guide.

- [#459](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/459) — list recovery points (read-only). The list panel in "Where it attaches to the portal".
- [#460](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/460) — approval-gated restore. The approval-gated restore flow and the reuse of the existing approval and guard.
- [#461](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/issues/461) — cross-Region and cross-account visibility. The corresponding section of this guide.

## References

These hold the AWS facts. This guide does not re-derive them; it cites them as design inputs.

- [AWS Backup Logically Air-Gapped Vault for Amazon FSx for NetApp ONTAP](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/data-protection/aws-backup-logically-air-gapped-vault.md) — vault prerequisites (customer managed key required; AWS-managed-key file systems are not copied and the job ends "Completed with issues"; RW volumes only), configuration options, restore and restore testing, and how to choose an isolation option.
- [Ransomware Recovery Runbook — Option D](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/runbooks/ransomware-recovery.md), the "Option D" recovery-account restore (`list-recovery-points-by-backup-vault` with `--backup-vault-account-id`, `start-restore-job` to a new volume).
