# The order that takes a first run from checking prerequisites to tearing it down

🌐 **Language / 言語**: [日本語](../ja/start-here.md) | English

This repository holds more than 50 patterns and more than 40 documents, each deployable on its own. What it does not settle is which to read first. That is all this page does. **It carries no content of its own** — each step points at what to read and what to run. It does not replace the existing guides.

Budget roughly **45 minutes** in demo mode, or **2–3 hours** against an existing FSx for ONTAP file system, including the wait for VPC endpoints.

## If FSx for ONTAP is not settled yet

Do not start here. This repository covers the implementation **after** the storage decision. The decision itself lives elsewhere.

| Where you are | Go to |
|---|---|
| The storage choice is still open | [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/README.md). Its file-storage-selection decision tree has seven endpoints and **four of them are not FSx for ONTAP** (the tree itself is Japanese today: [file-storage-selection.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/decision-trees/file-storage-selection.md)) |
| Choosing a migration method | [Playbook — migration-method decision tree](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/decision-trees/migration-method.md) (Japanese) |
| Coming from a SaaS, an on-premises file server, or another cloud | [Migration and data integration from SaaS and cloud storage](saas-to-fsx-ontap-migration.md) |
| Comparing against approaches other than S3 Access Points | [Alternative architectures — S3 AP / EFS / NFS / DataSync](../comparison-alternatives.md) |

If it is settled, carry on.

## Step 1 — Check the prerequisites

**Decide whether the environment is ready before starting a deployment, not during one.**

```bash
make preflight                                                  # credentials, region, tools, Bedrock
make preflight PROFILE=production VPC=vpc-0123456789abcdef0     # plus endpoint conflicts, ONTAP S3, secrets
```

Four profiles: `quick-start`, `production`, `demo`, `fpolicy`. Exit **75 means a tool is missing and 78 that the environment is not ready**, both distinct from 1 — "install something" and "fix a configuration" are different jobs, so they are reported differently.

Without an FSx for ONTAP file system, skip this step and use the [demo mode guide](../demo-mode-guide.en.md), which substitutes a regular S3 bucket.

- What is required: [deployment guide — prerequisites](deployment-guide.md#prerequisites)
- How to check what you have: [same — parameter mapping](deployment-guide.md#parameter-mapping)

## Step 2 — Put your own values into the parameters

**This is where a first run spends most of its time.** Read the values out of AWS rather than guessing them.

```bash
make discover-s3ap                       # every S3 Access Point in the account, from the FSx API
make discover-s3ap REGIONS=us-east-1     # another region
```

`make discover-s3ap` derives the list from the FSx API rather than a hand-kept file, so a deleted or `MISCONFIGURED` access point cannot keep looking correct in a config.

| What you need | Where it is |
|---|---|
| Per-pattern configuration | copy each pattern's `samconfig.toml.example` and fill it in |
| Parameter sets by scenario | [`cfn-params/`](../../cfn-params/) — five scenarios plus a README |
| Parameters by environment | [`params/`](../../params/) |
| Portal configuration | [`portal-config.example.ts`](../../solutions/amplify-portal/amplify/portal-config.example.ts) — **every entry carries the CLI command that finds its value and the matching `AMPLIFY_PORTAL_*` variable** |
| Whether a VPC endpoint collides with an existing stack | [deployment guide — VPC endpoint conflict matrix](deployment-guide.md#vpc-endpoint-conflict-matrix) |
| Which parameter an existing configuration's value belongs in | [migration guide](saas-to-fsx-ontap-migration.md) |

> **Note on S3 Access Point IAM**: a policy naming the access point only in the bucket form (`arn:aws:s3:::<alias>/*`) **deploys, reports `CREATE_COMPLETE`, and then refuses list, get and put alike**. The access-point form is required: `arn:aws:s3:<region>:<account-id>:accesspoint/<name>` and `…/object/*`. The templates here carry both, and `make drift` checks all 80 of them.

## Step 3 — Deploy

```bash
make build-uc1 && make deploy-uc1        # substitute the pattern number
```

- The steps in detail: [deployment guide](deployment-guide.md). A shorter step-by-step walkthrough exists as a [Japanese version](../guides/deployment-guide.md)
- Which pattern to pick: [pattern selection guide](../pattern-selection-guide.en.md)
- Verified paths and how long each took: [deployment guide — verified deploy paths](deployment-guide.md#verified-deployment-paths)
- Cost: [cost calculator](../cost-calculator.md). FSx for ONTAP, NAT gateways and interface VPC endpoints dominate

## Step 4 — Confirm it works

**`CREATE_COMPLETE` means it deployed, not that it works.**

```bash
make smoke STACK=fsxn-s3ap-legal-compliance
make smoke STACK=... ARGS='--list-prefix reports/ --read-only'
```

It resolves the access point from the stack, then lists, reads, writes, **reads back**, **confirms a listing shows it**, and deletes. The last two are separate because **a write returning 200 and the next reader being able to see it are different claims**, and the second is what a portal user experiences.

That separation comes from a measurement. The local suite passed its upload round-trip against a mock that starts empty, on a build whose IAM policy could not reach the access point at all. **A green local suite says nothing about reachability.**

- Running the workflow and reading the result: [deployment guide — day 2 operations](deployment-guide.md#day-2-operations)
- Before handing the portal to anyone: `make portal-preflight` (**that a page opens is not evidence anyone can sign in**)

## Step 5 — Tear it down

**Do not leave a verification environment standing.** NAT gateways and interface VPC endpoints bill whether or not anything uses them.

```bash
make propose-cleanup                                              # what is standing and what it costs (deletes nothing)
aws cloudformation delete-stack --stack-name <stack-name>
make cleanup-stacks                                               # repair a DELETE_FAILED stack
make cleanup-retained ARGS='--stack-prefix fsxn-s3ap-uc1'         # what the deletion left behind (report only)
make cleanup-retained ARGS='--stack-prefix fsxn-s3ap-uc1 --apply' # remove it
```

A successful stack deletion still leaves **log groups** (the functions create them on first invocation, so they are not in the template), **tables held by deletion protection**, and **user pools on `Retain`**. `make cleanup-retained` reports why each survived and what removing it costs, and changes nothing by default. `--apply` is refused while a stack matching the prefix still exists.

**Never touched**: FSx for ONTAP volumes, SVMs and file systems; SnapLock and WORM data; S3 buckets and Object Lock; Secrets Manager. A retention lock is not a leftover — it is behaving as configured, and its period cannot be shortened afterwards.

- The whole procedure: [portal cleanup guide](../../solutions/amplify-portal/docs/cleanup-guide.en.md)
- What cannot be deleted, and why: [deployment guide](deployment-guide.md), "Rollback and cleanup"

> **Note on irreversible operations**: creating a SnapLock volume, creating a SnapLock audit-log volume, locking a snapshot, and S3 Object Lock in `COMPLIANCE` mode cannot be undone. An audit-log volume **blocks deletion of its parent file system for at least six months, and the AWS API has no field for that retention period**. A verification account is the worst place to put one.

## Before taking it to production

| Concern | Where |
|---|---|
| Moving from PoC to production | [PoC to production](portal-poc-to-production.md) |
| Deployment profiles | [deployment profiles](../deployment-profiles.en.md) |
| Audit and compliance | [compliance guide](portal-compliance-guide.md) |
| Data classification and human-review thresholds | [data classification](../guides/data-classification.md) |
| What happens when something fails | [incident response](../incident-response-playbook.md) |
| Design considerations | [design considerations](../design-considerations.md) |

## Related documents

- [Documentation index](../index.md) — everything, listed
- [Quick start](../quick-start.md) — the shortest path only
- [Demo mode guide](../demo-mode-guide.en.md) — trying it without FSx for ONTAP
- [FSx for ONTAP management interfaces](fsx-ontap-management-interfaces.md) — which management paths are reachable
