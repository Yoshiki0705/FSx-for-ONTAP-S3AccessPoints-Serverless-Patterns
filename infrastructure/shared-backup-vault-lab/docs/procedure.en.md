# Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)

🌐 **Language / 言語**: [日本語](procedure.md) | English

# Runbook for the shared-vault verification lab

> Language / 言語: [日本語](procedure.md) | English

What this runbook keeps is only the parts code cannot express and the parts it could but that are left manual on purpose. Creating resources, backup, copy, restore, revocation and teardown are done by the scripts and CloudFormation, and the portal UI check is launched by `07_portal_config.sh --ui` through a Playwright spec. The permission table is in the [README](../README.en.md).

## The four opening items

1. Date and environment of the real-environment run: not yet done. Read everything below as unverified until it is confirmed on a real account. The screen-path check (the Playwright spec) is also not yet run in a browser, and the not-automated parts and the not-yet-run parts are distinct.
2. The period during which deletion is blocked: the LAG retention N. The minimum is 7 days, the AWS-fixed lower bound for a LAG vault. For the upper bound, see the AWS documentation ([`MinRetentionDays` / `MaxRetentionDays` of CreateLogicallyAirGappedBackupVault](https://docs.aws.amazon.com/aws-backup/latest/devguide/API_CreateLogicallyAirGappedBackupVault.html)). The start is the source backup creation time, not the copy completion time (observed once, N = 7). While it holds a recovery point the vault cannot be deleted either. An empty vault could be deleted (observed once). The Vault Lock documentation states that, after the grace time expires, a compliance-mode vault cannot be deleted or altered by any user or by AWS while it holds a recovery point [E-012].
3. Why the KMS key is not scheduled for deletion before the recovery point expires: a KMS key removed from the stack has its deletion scheduled, the waiting period is 7 to 30 days (30 by default), and while pending it cannot be used for cryptographic operations. The effect of the key becoming unusable before the LAG recovery point expires is untested, so the key is kept with `Retain` and deletion is done only by `10_teardown.sh --delete-key` after it confirms every LAG vault is empty. This does not say "the recovery point breaks unless the key is kept."
4. Cost: the running file system, the stored backups and copies, and the KMS key are billed. The current unit price comes from `01_preflight.sh --estimate-cost`, the actuals from `06_verify.sh --cost`. The price-list retrieval date and the uncertainty of the price-list row mapping are in the README. The split between resource hold from the lock and cost is in [the README "Cost and resource hold" section](../README.en.md#cost-and-resource-hold).

## How this runbook fits in

The permission table, the exit codes, the parameters and the script-to-Region mapping are in the README. This runbook covers only what those do not fill.

## The two accounts and sign-in

Two accounts are used, owner and recipient. Which account is which is the reader's decision. 01 checks that the two chosen are different and that each account id matches its profile. SSO sign-in is `aws sso login --profile <profile>`, and the authorization is a person's interaction in a browser.

<!-- SCREENSHOT: lab-sso-account-chooser.png | the IAM Identity Center account list showing two selectable accounts | none (no account id or email) -->

## Where to look in the owner console

06 emits the same facts through the API, but this is where you confirm with your own eyes that the API values and the screen agree. The console language is set to English (so the labels are common across the Japanese and English documents).

- AWS Backup > Vaults > the LAG vault detail: type, lock, min and max retention, encryption key kind.
- Jobs > Copy jobs: the completed copy job.
- The LAG vault > Recovery points: one point and its expiry.
- RAM > Shared by me: the ACTIVE share and its resource type.

<!-- SCREENSHOT: lab-backup-lag-vault-owner.png | AWS Backup LAG vault detail: type, lock, min and max retention, encryption key kind | mask the account id and the vault ARN -->
<!-- SCREENSHOT: lab-backup-copy-job.png | the completed copy job in Jobs > Copy jobs | mask the account id and the recovery-point ARNs -->
<!-- SCREENSHOT: lab-backup-lag-recovery-points.png | the LAG vault Recovery points list showing one point and its expiry | mask the account id and the recovery-point ARN -->
<!-- SCREENSHOT: lab-backup-account-sharing.png | the Account sharing section of the vault detail showing the recipient | mask both account ids -->
<!-- SCREENSHOT: lab-ram-owner-share.png | RAM > Shared by me showing the ACTIVE share and its resource type | mask the account ids and the resource-share ARN -->

## Where to look in the recipient console

- RAM > Shared with me: the pending invitation and the accept action.
- Backup > Vaults > shared through RAM: the shared vault and the owner column.
- The recovery-point restore form: the SVM, volume name and junction path.
- Jobs > Restore jobs: running and completed.
- FSx > volumes: the restored volume.

<!-- SCREENSHOT: lab-ram-recipient-invitation.png | RAM > Shared with me showing the pending invitation and the accept action | mask both account ids and the invitation ARN -->
<!-- SCREENSHOT: lab-backup-shared-vault-recipient.png | Backup > Vaults showing the shared vault and the owner column | mask both account ids and the vault ARN -->
<!-- SCREENSHOT: lab-backup-restore-form.png | the recovery-point restore form showing the SVM, volume name and junction path | mask the file-system and SVM ids -->
<!-- SCREENSHOT: lab-backup-restore-job.png | Jobs > Restore jobs showing a running and a completed restore | mask the account id and the restore-job ARN -->
<!-- SCREENSHOT: lab-fsx-restored-volume.png | FSx volumes showing the restored volume | mask the file-system, SVM and volume ids -->

## Scope of the portal UI check

The portal UI check is launched by `07_portal_config.sh --ui --expect <state>`. Preparing the credentials, installing the prerequisites (Node, `node_modules`, chromium) and counting a skip as a failure are held by 07, so they are not written here. The spec sees element presence and text only, not look-and-feel. The spec is not yet run in a browser (E25).

<!-- SCREENSHOT: portal-ja-recovery-region-selector.png | the Recovery points panel region selector | mask the account id in any ARN shown -->
<!-- SCREENSHOT: portal-en-recovery-region-selector.png | the Recovery points panel region selector (English UI) | mask the account id in any ARN shown -->
<!-- SCREENSHOT: portal-ja-recovery-shared-vault.png | the shared-vault choice and the owner-account column | mask both account ids -->
<!-- SCREENSHOT: portal-en-recovery-shared-vault.png | the shared-vault choice and the owner-account column (English UI) | mask both account ids -->

## Wait time for enabling the cost-allocation tag and where the billing screen is

The cost is read by `06_verify.sh --cost`. What this runbook keeps is the wait until the `Project` cost-allocation tag takes effect after it is enabled, and which Cost Explorer screen filters by the tag. The one-line enable command is in the README; the scripts do not run it. The wait is to be confirmed in the documentation and written in (at implementation time).

<!-- SCREENSHOT: lab-billing-cost-explorer-tag.png | Cost Explorer filtered by the Project tag, same period as 06 --cost | mask the account id -->
<!-- SCREENSHOT: portal-ja-recovery-restore-dialog.png | the restore dialog with its confirmation checkbox | mask the file-system and SVM ids -->
<!-- SCREENSHOT: portal-en-recovery-restore-dialog.png | the restore dialog with its confirmation checkbox (English UI) | mask the file-system and SVM ids -->

## Prerequisites not in code

- The reader's organization SCPs and other accounts' auto-remediation cannot be enumerated from the reader's own account API lists. A copy into the LAG vault may fail because of another team's revoke action.
- Check the LAG vault supported Regions before choosing the destination. The list is in the AWS Backup LAG vault documentation and is revised, so it is linked rather than copied here ([the page](https://docs.aws.amazon.com/aws-backup/latest/devguide/logicallyairgappedvault.html)). This does not say "no API is found."

<!-- SCREENSHOT: portal-ja-recovery-revoked-notice.png | the return to the default display and the notice after revocation | mask the account id -->
<!-- SCREENSHOT: portal-en-recovery-revoked-notice.png | the return to the default display and the notice after revocation (English UI) | mask the account id -->

## When updating an existing sandbox

A reader who holds an existing sandbox and reruns `make sandbox` with updated dependencies may see `07 --deploy` fail with `UPDATE_FAILED`. The cause is that the AwsCliLayer replacement is refused on an Express-mode sandbox, written up in the AwsCliLayer row of `docs/agent/portal-cdk-quality-gates.md`. The choice of recovery (deleting and recreating removes the Cognito users and DynamoDB) is a decision for someone responsible for the portal's user data. This lab holds no pre-detection; the guidance is read after the failure.

## The MPA path, out of scope for this lab

Multi-party approval (MPA) on a LAG vault gates the `CreateRestoreAccessVault` approval behind a 3-to-20-person approval team, a path separate from the RAM-share restore this lab verifies. It needs a second AWS Organization (a recovery org) in addition to the primary org, and `MpaApprovalTeamArn` must be set at vault creation (it cannot be changed afterwards; a change replaces the vault). This lab's single-organization, two-account setup does not provide those, so it does not exercise MPA; the template's `MpaApprovalTeamArn` parameter is left empty. This path is not run on real environment (tracked in follow-up issue #471). See [the AWS Backup MPA guide](https://docs.aws.amazon.com/aws-backup/latest/devguide/multipartyapproval.html) and [what Multi-party approval is](https://docs.aws.amazon.com/mpa/latest/userguide/what-is.html). <!-- allow:not-a-claim: these are documented MPA prerequisites cited from the linked AWS MPA guide, not a claim of vendor absence -->

## Screenshot list

Markers are of the form `<!-- SCREENSHOT: <filename> | the content that should appear | what to mask -->`, placed at the relevant point and, in equal number, in this list. Markers are written in English. The originals of P01 to P04 are written out by the spec to `LAB_CAPTURE_DIR` (not taken by hand). The capture itself is not yet done.

| ID | Filename (proposed) | Screen |
|---|---|---|
| S01 | lab-sso-account-chooser.png | the IAM Identity Center account list |
| S02 | lab-backup-lag-vault-owner.png | the owner LAG vault detail |
| S03 | lab-backup-copy-job.png | the owner copy job |
| S04 | lab-backup-lag-recovery-points.png | the owner recovery points |
| S05 | lab-backup-account-sharing.png | the owner Account sharing |
| S06 | lab-ram-owner-share.png | the owner RAM share |
| S07 | lab-ram-recipient-invitation.png | the recipient RAM invitation |
| S08 | lab-backup-shared-vault-recipient.png | the recipient shared vault |
| S09 | lab-backup-restore-form.png | the recipient restore form |
| S10 | lab-backup-restore-job.png | the recipient restore job |
| S11 | lab-fsx-restored-volume.png | the recipient restored volume |
| S12 | lab-billing-cost-explorer-tag.png | the Cost Explorer tag filter |
| P01 | portal-ja-recovery-region-selector.png | the portal Region selector (Japanese UI) |
| P01 | portal-en-recovery-region-selector.png | the portal Region selector (English UI) |
| P02 | portal-ja-recovery-shared-vault.png | the portal shared-vault choice (Japanese UI) |
| P02 | portal-en-recovery-shared-vault.png | the portal shared-vault choice (English UI) |
| P03 | portal-ja-recovery-restore-dialog.png | the portal restore dialog (Japanese UI) |
| P03 | portal-en-recovery-restore-dialog.png | the portal restore dialog (English UI) |
| P04 | portal-ja-recovery-revoked-notice.png | the portal post-revocation notice (Japanese UI) |
| P04 | portal-en-recovery-revoked-notice.png | the portal post-revocation notice (English UI) |
