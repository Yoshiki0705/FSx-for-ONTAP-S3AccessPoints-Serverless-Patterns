# Real-environment run: not yet done (status source: docs/verification-record.md)

> Language / 言語: [日本語](verification-record.md) | English

This document is the single source of truth for the state of the shared-vault lab. The status line in the README and the runbook points at this file.

## Status

Date and environment of the real-environment run: not yet done. There are zero recorded rows. While no recorded row holds, writing a word such as `verified` (or its Japanese equivalents) under the lab fails a test (the rules below under "Limits of the mechanical enforcement").

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

(No records. The real-environment run is not yet done.)

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
