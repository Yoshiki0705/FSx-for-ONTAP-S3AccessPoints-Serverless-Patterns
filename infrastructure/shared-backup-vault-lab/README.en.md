# Real-environment run: not yet done (status source: docs/verification-record.md)

# Shared-vault verification lab

> Language / 言語: [日本語](README.md) | English

A lab that reproduces, from code and parameters alone, the path where an AWS Backup logically air-gapped (LAG) vault is shared across two accounts over RAM and its recovery points are listed and restored from the recipient account and the Amplify portal. It is three CloudFormation templates, ten numbered scripts, a portal UI-check spec, and a runbook and verification record in Japanese and English.

## Opening notice

- **The real-environment run is not yet done.** Nothing here has run against a real account yet. Each script and document carries a status line at the top, and the single source of truth for the state is [`docs/verification-record.md`](docs/verification-record.en.md).
- **Creating a LAG vault is irreversible.** The retention (7 to 35 days) is fixed at creation, and the vault cannot be deleted while it holds a recovery point. An empty vault could be deleted (observed once). The detail is at the top of [`docs/procedure.en.md`](docs/procedure.en.md).
- **It costs money.** The running file system, the stored backups and copies, and the KMS key are billed. [`10_teardown.sh`](scripts/10_teardown.sh) does the cleanup and lists what remains.

## Quick start

```bash
cp lab.env.example lab.local.env     # replace the values for your environment
./scripts/01_preflight.sh --side both   # check prerequisites before any charge (read only)
./scripts/02_deploy.sh --side owner --apply
./scripts/02_deploy.sh --side recipient --apply
./scripts/03_deploy_lag_share.sh --retention-days 7 --apply --confirm <TOKEN>
./scripts/04_backup_and_copy.sh --phase all --retention-days 7 --apply --confirm <TOKEN>
./scripts/05_accept_share.sh --apply
./scripts/06_verify.sh
./scripts/10_teardown.sh --apply     # cleanup; lists what remains
```

A script that changes state prints a plan and stops with exit code 10 unless `--apply` is given. An irreversible operation (03, 04, 10) also requires a token tied to the parameters (`--confirm`). The token string is printed with the plan by a run without `--apply`.

## Parameters

Every variable is listed with a dummy value in `lab.env.example`. Every environment-dependent value is a `LAB_`-prefixed variable, covering the account id, profile, Region, VPC, subnet, SG and names. Some defaults and conditions rest on a single manual observation; the observed values and conditions are in [the reference section of `docs/verification-record.en.md`](docs/verification-record.en.md#reference-first-manual-observations) (the README does not copy observed values).

| Variable | Required | Default | Used by |
|---|---|---|---|
| `LAB_OWNER_PROFILE` / `LAB_RECIPIENT_PROFILE` | yes | — | all scripts |
| `LAB_OWNER_ACCOUNT_ID` / `LAB_RECIPIENT_ACCOUNT_ID` | yes | — | all scripts |
| `LAB_PRIMARY_REGION` | yes | — | all scripts |
| `LAB_OWNER_SUBNET_ID` | yes | — | 01, 02 (owner) |
| `LAB_RECIPIENT_SUBNET_ID` | yes when EXISTING is empty | — | 01, 02 (recipient) |
| `LAB_SECOND_REGION` | — | empty (one Region) | 01, 02 (recipient), 03-10 |
| `LAB_TAG` | — | `shared-vault-lab` | tag, stack names, alias, default names |
| `LAB_STANDARD_VAULT_NAME` / `LAB_LAG_VAULT_NAME` / `LAB_SHARE_NAME` | — | `${LAB_TAG}-*` | 02-10 |
| `LAB_ALLOW_EXTERNAL_PRINCIPALS` | — | `true` | 03 |
| `LAB_RECIPIENT_EXISTING_FS_ID` | — | empty (creates a minimal FS) | 01, 02 (recipient) |
| `LAB_MIN_SSO_MINUTES` | — | `30` | 02, 03, 04, 07, 08, 10 |
| `PORTAL_URL` / `PORTAL_USER` / `PORTAL_PASSWORD` | — | empty | 07 `--ui` |

`PORTAL_*` and `LAB_UI_EXPECT` are the exceptions without a `LAB_` prefix. `PORTAL_URL` / `PORTAL_USER` / `PORTAL_PASSWORD` reuse the names the existing portal E2E already uses. `LAB_UI_EXPECT` is the value 07 passes to the spec (`arn-missing` / `arn-present` / `revoked`); readers do not set it. The test-only time pin is referenced only inside `common.sh` and appears in neither this table nor `lab.env.example`.

## Scripts and Regions

The meaning of `--region` differs per script, as does the default when it is omitted.

| Script | Role | Regions read | Regions changed | `--region` omitted |
|---|---|---|---|---|
| 01 | prerequisite check (read only) | PRIMARY, SECOND | none | all configured Regions |
| 02 | file system, SVM, volume, standard vault, role (owner / recipient) | given | given | owner PRIMARY only, recipient all Regions |
| 03 | LAG vault and RAM share | given | given | PRIMARY then SECOND |
| 04 | backup and copy | PRIMARY and the destination LAG | backup to PRIMARY, copy to the destination | all destinations |
| 05 | accept the RAM invitation | recipient given | recipient invitation | all Regions |
| 06 | verify (read only); `--cost` reads actual cost | both accounts, given | none | all Regions |
| 07 | portal config and UI check | recipient home | `--deploy` only | `--print` all Regions, others home |
| 08 | restore | recipient given | the given restore target | PRIMARY only |
| 09 | revoke the RAM share | owner and recipient | owner's share | all Regions |
| 10 | teardown | PRIMARY, SECOND | PRIMARY, SECOND | takes no `--region`; all Regions |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | failure or abort |
| 2 | usage error (including an argument format violation) |
| 10 | plan only (no `--apply`) |
| 75 | missing tool |
| 78 | environment not ready (01 only) |

## Required permissions

The `service:operation` set the operator needs is kept in one place, [`scripts/lib/required-actions.json`](scripts/lib/required-actions.json), and the 01 permission simulation, this table and the stub call record all reference the same set. A test keeps the table's set equal to this JSON.

`iam simulate-principal-policy` is a check for finding a possible shortfall before any charge, not a guarantee of sufficiency. Whether SCP or RCP are in the evaluation is unconfirmed (E18). Among the CloudFormation resource permissions, the three FSx types have none in the schema and are transcribed from the documentation, so the enumeration is unverified (E23).

Owner-side operator (`operator-owner`, including `iam:PassRole` to the called role):

```
backup:DeleteRecoveryPoint
backup:DescribeBackupJob
backup:DescribeBackupVault
backup:DescribeCopyJob
backup:DescribeRecoveryPoint
backup:DescribeRegionSettings
backup:ListBackupJobs
backup:ListBackupVaults
backup:ListCopyJobs
backup:ListRecoveryPointsByBackupVault
backup:StartBackupJob
backup:StartCopyJob
cloudformation:CreateChangeSet
cloudformation:DeleteStack
cloudformation:DescribeChangeSet
cloudformation:DescribeStackEvents
cloudformation:DescribeStackResource
cloudformation:DescribeStacks
cloudformation:DescribeType
cloudformation:ExecuteChangeSet
ec2:DescribeSecurityGroups
ec2:DescribeSubnets
fsx:DeleteVolume
fsx:DescribeBackups
fsx:DescribeFileSystems
fsx:DescribeStorageVirtualMachines
fsx:DescribeVolumes
fsx:ListTagsForResource
iam:GetRole
iam:PassRole
iam:SimulatePrincipalPolicy
kms:DeleteAlias
kms:DescribeKey
kms:ScheduleKeyDeletion
ram:DeleteResourceShare
ram:GetResourceShares
```

Recipient-side operator (`operator-recipient`):

```
backup:DescribeRestoreJob
backup:GetRecoveryPointRestoreMetadata
backup:ListBackupVaults
backup:ListRecoveryPointsByBackupVault
backup:ListRestoreJobs
backup:StartRestoreJob
cloudformation:CreateChangeSet
cloudformation:DeleteStack
cloudformation:DescribeChangeSet
cloudformation:DescribeStackEvents
cloudformation:DescribeStacks
cloudformation:ExecuteChangeSet
ec2:DescribeSecurityGroups
ec2:DescribeSubnets
fsx:DeleteVolume
fsx:DescribeFileSystems
fsx:DescribeStorageVirtualMachines
fsx:DescribeVolumes
fsx:ListTagsForResource
fsx:TagResource
iam:GetRole
iam:GetRolePolicy
iam:PassRole
iam:SimulatePrincipalPolicy
ram:AcceptResourceShareInvitation
ram:GetResourceShareInvitations
```

The permissions CloudFormation needs when it creates resources with the caller's credentials are in the `cloudformation-provisioning-owner` group on the owner side and `cloudformation-provisioning-recipient` on the recipient side; the full sets are in [`scripts/lib/required-actions.json`](scripts/lib/required-actions.json). For reads that are not required for the main flow (`operator-optional`, such as `ce:GetCostAndUsage` and `pricing:GetProducts`), 01 emits a warning rather than a failure when they are not allowed.

## Resource types created

These are the CloudFormation types the templates create. The permissions for the three FSx types (`AWS::FSx::FileSystem` / `StorageVirtualMachine` / `Volume`) are not in the schema and are transcribed from the documentation; they are unverified (E23).

| Template | Types |
|---|---|
| owner-base | `AWS::KMS::Key`, `AWS::KMS::Alias`, `AWS::FSx::FileSystem`, `AWS::FSx::StorageVirtualMachine`, `AWS::FSx::Volume`, `AWS::Backup::BackupVault`, `AWS::IAM::Role` |
| owner-lag-share | `AWS::Backup::LogicallyAirGappedBackupVault`, `AWS::RAM::ResourceShare` |
| recipient-restore | `AWS::IAM::Role`, `AWS::FSx::StorageVirtualMachine`, `AWS::FSx::FileSystem` (only when `ExistingFileSystemId` is empty) |

## Direct deploy without the scripts

A reader using CloudFormation directly can copy an example file, fill in the values, and deploy in this form (owner-side example; `<…>` are the reader's values).

```
aws cloudformation deploy --template-file cloudformation/owner-base.yaml --stack-name <LAB_TAG>-owner-base --capabilities CAPABILITY_IAM --parameter-overrides file://cloudformation/parameters/owner-base.local.json --profile <PROFILE> --region <REGION>
```

A direct deploy is outside the scripts' guards (the token, the post-check, the account-match check). Verify the retention, the destination and the account yourself. The one defence left in the template is the `Rules` section of `owner-lag-share.yaml`, but whether `aws cloudformation deploy` really refuses a `Rules` mismatch is not confirmed (E1). Whether `--parameter-overrides file://…` accepts the example file format is also not confirmed (E22).

## Enabling organization sharing and the cost-allocation tag

The following two are organization-wide and payer-account settings; the lab scripts do not run them. 01 only reports their state as a read. Run them with the management-account credentials when needed, once the blast radius is understood.

```
aws ram enable-sharing-with-aws-organization --profile <management-account>
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=Project,Status=Active --profile <payer-account>
```

Neither is required on the default path (`LAB_ALLOW_EXTERNAL_PRINCIPALS=true`). The cost-allocation tag only affects the `Project` filtering of `06 --cost`.

## Checking cost

The current unit price is read from the price list and shown by `01_preflight.sh --estimate-cost`. The actual cost is read by `06_verify.sh --cost` via `ce get-cost-and-usage` filtered by the `Project` tag (read only).

**The Cost Explorer API is charged 0.01 USD per paginated request** ([the Cost Explorer user guide](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html), read in full on 2026-10-11; not re-checked). One run of `06 --cost` is 2 accounts x 2 (tag-filtered and total) = 4 requests, and pagination adds more. The charge for `ce list-cost-allocation-tags` (01 `--estimate-cost`) is not confirmed. A Cost Explorer value is not a bill, and it can be delayed and come back empty right after a run.

## Reading the status line

The status line at the top of each script and document is derived from the records in [`docs/verification-record.en.md`](docs/verification-record.en.md). There is an intermediate state until every item holds, written `recorded [V1][V4]; not recorded [E13]`, listing only the items that hold. Only when `recorded` is empty is the line `not yet done`. The full grammar is in the status section of the verification record.

## Related documents

- [Runbook](docs/procedure.en.md) (where to look in the console, sign-in, prerequisites not in code)
- [Verification record](docs/verification-record.en.md) (V / E definitions, the real-environment record, first manual observations)
- [FSx for ONTAP resource sharing with AWS RAM](../../docs/multi-account/ram-sharing.md)
- [Disaster recovery pattern](../../docs/multi-region/disaster-recovery.md)
- [Portal design guide](../../solutions/amplify-portal/docs/data-protection-recovery-design.en.md)
