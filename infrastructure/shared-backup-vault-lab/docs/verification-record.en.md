# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)

🌐 **Language / 言語**: [日本語](verification-record.md) | English

> Language / 言語: [日本語](verification-record.md) | English

This document is the single source of truth for the state of the shared-vault lab. The status line in the README and the runbook points at this file.

## Status

Date and environment of the real-environment run: 2026-10-12 (JST). The owner and the recipient were both in ap-northeast-1, with ap-northeast-3 as the second Region, run with the lab's own scripts and templates. The record table below carries one row per item for V1 to V7. E13 (an environment with organization sharing on) is not recorded because this environment used the invitation path with organization sharing off. MPA was not run (see "Treatment of MPA" below).

The status-line grammar has an intermediate state until every item holds. Environments are exclusive and cannot satisfy every item at once, so only the items that hold are listed.

- Zero holding records: `# Real-environment run: not yet done (status source: docs/verification-record.md)`
- Partly holding: `# Real-environment run: recorded [V1][V4]; not recorded [E13] (status source: docs/verification-record.md)`
- The items listed under `recorded` hold against the current code digest; `not recorded` is the rest. Only when `recorded` is empty is the line written `not yet done`.

## Definition of the verification items

This table is authoritative for the public V / E definitions. Every number in the README, the runbook and the output of 06 / 07 resolves here. The `scripts:` column names the scripts that emit the item. `07-ui` is the UI-check mode of 07 (`--ui`).

| Item | Meaning | scripts |
|---|---|---|
| V1 | The recipient's `--by-shared` lists exactly one shared vault, its ARN account is the owner, and its `VaultType` is LAG | scripts: 06 |
| V2 | The owner's `--by-shared` is empty (direction of the share) | scripts: 06 |
| V3 | For the portal role, the state without the shared vault ARN is denied and the state with it added succeeds (two stages) | scripts: 07, 07-ui |
| V4 | A call without `--backup-vault-account-id` returns `AccessDeniedException`; the call with it succeeds | scripts: 06 |
| V5 | The deployed function invokes `listSharedBackupVaults` without an error, and the shared vault is selectable in the UI | scripts: 07, 07-ui |
| V6 | Seconds from revoking the share until it leaves the list, the error codes in that window, and the UI notice | scripts: 07, 07-ui, 09 |
| V7 | A recovery point in the shared vault restores into the recipient's SVM | scripts: 06, 08 |
| V8 | Treatment of a backup from an AWS-managed-key file system (the negative side). It needs a second file system, so it is a separate decision | scripts: MANUAL (direct API observation; the lab scripts do not emit it) <!-- allow:not-a-claim: this row defines a verification item and names which scripts cover it, not a claim of vendor absence --> |
| E1 | `aws cloudformation deploy` refuses a `Rules` mismatch and the air-gapped vault stack reaches AVAILABLE | scripts: 03 |
| E2 | `AWS::RAM::ResourceShare` with `ResourceArns` / `Principals` shares the air-gapped vault, and the invitation is PENDING where organization sharing is off | scripts: 03, 05 |
| E3 | The tags of the CloudFormation-created file system, SVM and volume are readable via `fsx list-tags-for-resource` | scripts: 02 |
| E4 | The inline KMS policy on `BackupRole` lets both a same-Region and a cross-Region copy succeed | scripts: 04 |
| E5 | The duration of a cross-Region copy, and the expiry equal to the source creation time plus N days | scripts: 04, 06 |
| E6 | A recovery point in another Region restores into the recipient file system in that Region | scripts: 08 |
| E7 | The behaviour of retrying a failed copy job with the same idempotency token (a new job, or the original) | scripts: MANUAL (observable only with a direct `start-copy-job`) |
| E8 | A restore succeeds with the recipient's dedicated role (the Restores managed policy only) | scripts: 08 |
| E9 | The key difference between reading and writing restore metadata, and that the portal-built metadata also works | scripts: 08 |
| E10 | Whether a copy job into the air-gapped vault carries a `StatusMessage` (if it does, it is the "Completed with issues" signal) | scripts: 04 |
| E11 | `delete-stack` succeeds after the share has been removed with `ram delete-resource-share` | scripts: 10 |
| E12 | The behaviour of the CloudFormation volume deletion, and that deleting the volume via the API before deleting the stack works | scripts: 10 |
| E13 | Access without an invitation works where organization sharing is on, and `AllowExternalPrincipals=false` succeeds | scripts: 03, 05 |
| E14 | The SSO-token minutes-left computation matches the real cache | scripts: 01 |
| E15 | The attribute names of the pricing API and the mapping of the estimate rows | scripts: 01 |
| E16 | `describe-type` returns `TypeNotFoundException` in a Region that does not offer the type; a Region without `SINGLE_AZ_1` refuses the 02 create request on the spot | scripts: 01, 02 |
| E17 | An ARN-scoped on-demand backup succeeds even when `ResourceTypeOptInPreference` for `FSx` is `false` | scripts: 01, 04 |
| E18 | `iam simulate-principal-policy` returns a meaningful result for the SSO role, and whether SCP / RCP are included in the evaluation | scripts: 01 |
| E19 | The organization-sharing state is readable from the owner profile (when it is a management account) | scripts: 01 |
| E20 | The Playwright spec passes against the real portal screens, and `rpRestoreConfirm` is disabled before confirmation | scripts: 07-ui |
| E21 | Toggling `ShareEnabled` succeeds at deleting an already-absent share and creates a new share and invitation | scripts: 03, 05 |
| E22 | `aws cloudformation deploy --parameter-overrides file://…` accepts the example files | scripts: MANUAL (observed on the direct-deploy path; the scripts do not emit it) |
| E23 | The CloudFormation resource-permission enumeration covers exactly the permissions that are needed | scripts: MANUAL (a shortfall surfaces only on a deploy; the 01 simulation is not a guarantee of sufficiency) |
| E24 | Which Region's `list-copy-jobs` a cross-Region copy job appears in (source, destination, both) | scripts: MANUAL (direct `list-copy-jobs` observation; 04 / 10 read both but do not emit which one carries it) |
| E25 | That the 07 `--ui` launch path works in a real account (dev-server start, chromium detection, reading the report) | scripts: 07-ui |
| E26 | That `ce get-cost-and-usage` returns a value under the `Project` tag filter, and the treatment of untagged cost | scripts: 06 |

## Real-environment record

One row is one item's result in one run. A row is the result of a single run, not a generalization to another environment or scale. Rows are produced by `python3 scripts/lib/lab_helpers.py record-row`, which prints a candidate from `lab-run.local.jsonl`; a person masks the account id and ARNs and pastes it. Rows are never written automatically.

The item is in the closed set of the definition table above, `result` is of the form `N✅ N❌ N⚠`, and an item backs a claim only when `❌` is 0 and `✅` is at least 1. The `code digest` is 12 hex digits, and only a row matching the current code digest holds. `portal-ref` is filled for V3, V5, V6 and V7 rows and is `-` otherwise.

| Date (UTC) | Region | Config | AWS CLI | Code digest | portal-ref | Item | Result | Duration | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | - | V1 | 1✅ 0❌ 0⚠ | 18s | script 06_verify.sh. PASS in both Regions. `--by-shared` lists one LAG vault, ARN account is the owner, VaultType LOGICALLY_AIR_GAPPED_BACKUP_VAULT; the by-shared row has no VaultState and NumberOfRecoveryPoints 0 |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | - | V2 | 1✅ 0❌ 0⚠ | 18s | script 06_verify.sh. The owner's `--by-shared` is empty in both Regions |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | - | V4 | 1✅ 0❌ 0⚠ | 18s | script 06_verify.sh. Without `--backup-vault-account-id` it is AccessDeniedException; with it the call succeeds and returns 1 recovery point. ARN shape arn:aws:backup:<region>:<owner>:recovery-point:<id> |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | 6231351a42a9 | V3 | 1✅ 0❌ 0⚠ | 41s | script 07_portal_config.sh (--ui, arn-present). The role policy lists the shared vault ARN; the spec's two arn-present tests PASS (air-gapped chip and owner account shown; the restore dialog opens with a disabled confirm and closes without restoring) |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | 6231351a42a9 | V5 | 1✅ 0❌ 0⚠ | 41s | script 07_portal_config.sh. listSharedBackupVaults succeeds and shows the owner account |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | 6231351a42a9 | V6 | 1✅ 0❌ 0⚠ | 2s | script 09_revoke_share.sh. After the revoke the vault leaves by-shared in about 1 to 2 s (both Regions); a later list-recovery-points is AccessDeniedException. The already-restored volume is untouched |
| 2026-10-12 | ap-northeast-1 | SINGLE_AZ_1 128MBps 1024GiB | aws-cli/2.36.5 | b8ec32a85b54 | 6231351a42a9 | V7 | 1✅ 0❌ 0⚠ | 1362s | script 08_restore.sh (--via cli). Restored from the shared recovery point into the recipient's existing file system; the job reached COMPLETED, vol_restored reached CREATED (1 GiB, junction /vol_restored), the restore role was accepted, and the restored volume carried the Project tag |

Each row is one item's result in one run (n=1), not a generalization to another environment or scale. The digest and portal-ref correspond to the code at commit time.

## Where a cross-Region copy job appears (the E24 observation)

The cross-Region copy job (Tokyo source to the Osaka LAG vault) appeared in the SOURCE Region's list-copy-jobs with the destination vault ARN in ap-northeast-3; it did not appear in the destination Region's list (observed once). Both copies' recovery points carry the same delete date (source-backup creation time plus 7 days), cross-Region included. E24 is a MANUAL item, so it is kept here as an observation rather than in the record table.

## Treatment of MPA

Multi-party approval (MPA) was not run (recorded as not applicable in this environment). MPA needs two AWS Organizations (a primary and a separate recovery org) and an approval team of 3 to 20 approvers. This lab's single-organization, two-account setup does not provide them. It is tracked in follow-up issue #471. The template's `MpaApprovalTeamArn` parameter and the prerequisites are in the MPA section of the README and the runbook, and it is not run on real environment. <!-- allow:not-a-claim: these are documented MPA prerequisites cited from the AWS MPA guide in the README and runbook, not a claim of vendor absence -->

## Real-environment screenshots

These are the screens and CLI output observed in the real environment. Account ids, resource ids, ARNs, recovery-point ids and KMS key ids are masked (blacked out or cropped), and the portal screens use the spec's dummy account 111122223333. The runbook's capture-plan markers (`<!-- SCREENSHOT: ... -->`) are a capture guide and are distinct from the 9 images placed here.

| File name | Screen / output | Item |
|---|---|---|
| lab-recipient-shared-vault-list.png | The recipient's `--by-shared` list (one LAG vault) | V1 |
| lab-recipient-shared-vault-detail.png | The shared vault detail seen from the recipient | V1 |
| lab-recipient-shared-vault-osaka.png | The shared vault in the second Region (Osaka) | V1 |
| lab-recipient-shared-vault-revoked.png | The state after the revoke left the list | V6 |
| lab-recipient-restored-volume.png | The restored vol_restored | V7 |
| lab-owner-vault-detail.png | The owner's LAG vault detail | V5 |
| lab-owner-copy-jobs.png | The owner's copy jobs (cross-Region destination ARN) | E24 |
| P02-arn-present.png | The portal shared-vault choice (arn-present) | V3, V5 |
| P03-restore-dialog.png | The portal restore dialog (confirm disabled) | V3 |

## Reference: first manual observations

The following were observed by means other than these scripts. Each carries a date and n=1. **They are not a basis for `verified`** (they are not the output of these scripts, so under the third minimum line they cannot back a claim). The README parameter table does not copy these values; it links to this section instead.

| Observation | Value | Condition |
|---|---|---|
| Condition for `LAB_ALLOW_EXTERNAL_PRINCIPALS=false` | Holds only when organization sharing is on | 2026-10-11, observed once; not reproduced |
| SSO token lifetime | 1 hour | 2026-10-11, observed once; the `LAB_MIN_SSO_MINUTES` default of 30 minutes is set below this observation |
| Portal sign-in URL (`PORTAL_URL`) | The local dev server when empty | 2026-10-11, observed once; running in a browser is not yet run on real environment |
| Expiry | Source backup creation time plus retention N (N = 7) | 2026-10-11, observed once; the effect of deleting the source key early is untested |
| Time until the file system is AVAILABLE | About 15 minutes | 2026-10-11, observed once; the timeout is 60 minutes |
| Same-Region copy job | 13 min 45 s | 2026-10-11, observed once; cross-Region is not observed |
| Restore job | 21 min 17 s | 2026-10-11, observed once; same-Region, AWS-owned-key vault only |
| Revoke to leaving the list | 1 to 8 s | 2026-10-11, observed once; five-second polling |

## Limits of the mechanical enforcement

What `test_verification_record.py` checks is the form of the record rows, the closed set, the absence of placeholders, and a match with the current code digest. **It does not check that a row came from a real run.** A person produces a row from a run's output, so the strength of the evidence still depends in part on the honesty of whoever pastes the record. To reduce that, each script prints `digest=<12 hex> run=<ISO 8601 UTC>` on exit and records the same line in `lab-run.local.jsonl`. `record-row` copies the date, digest, item and result counts from that record, but `lab-run.local.jsonl` is itself a local file of whoever ran it and is not impossible to forge.
