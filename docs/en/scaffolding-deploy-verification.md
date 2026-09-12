# Deploying the scaffolded output, verifying it, and taking it down

> 🌐 **Language / 言語**: [日本語](../ja/scaffolding-deploy-verification.md) | English

Covers deploying the three scaffolded outputs compared in
[App foundation choices](scaffolding-and-backend-toolkit-choices.md) to AWS, verifying them
against real services, and removing them afterwards. The figures in the comparison were
measured up to a local synth; this document owns what comes after that.

**Why to read it first**: the generated defaults include deletion protection and `Retain`, so
resources survive a stack deletion. What and how many is in [Teardown](#teardown), placed
there on the assumption that it is read **before** the deploy.

**This is not a report of discoveries.** Every place we walked into has a matching upstream
source, and [Mapping to what is already known](#mapping-to-what-is-already-known) pairs them
off one by one. Writing them up as new claims would restate published primary sources on
weaker evidence.

## Verification categories

The same words as the portal's
[verification results](../../solutions/amplify-portal/docs/verification-results.en.md).
Sharing the vocabulary avoids the state where two documents say the same word and mean
different strengths of evidence.

| Category | Meaning |
|------|------|
| **Live E2E** | Deployed to AWS and the application's own function executed, with the expected result |
| **Live read** | Deployed, and reads or listings confirmed; writes and changes not confirmed |
| **Local only** | Confirmed against the local implementation (the mode needing no AWS account); not confirmed on AWS |
| **Synth only** | The template was generated and read. Nothing was deployed |

## Prerequisites

| Item | Required | How to check |
|---|---|---|
| CDK bootstrap (target region) | ✅ | `aws cloudformation describe-stacks --stack-name CDKToolkit` |
| CDK bootstrap (us-east-1) | Nx only | The Nx output puts the CloudFront web ACL in a **separate us-east-1 stack**, so this is needed in addition to the target region |
| Node.js 22 or later | ✅ | An AWS Blocks prerequisite ([Getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)) |
| npm 11 or later | Nx only | A Nx Plugin for AWS prerequisite. On npm 10 generation fails with `Cannot read properties of null (reading 'edgesOut')` (source: [awslabs/nx-plugin-for-aws PR #1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228)) |
| `npm_config_yes=true` in a non-interactive shell | Nx only | To answer `npm create`'s first-run install confirmation (P11) |

## Mapping to what is already known

**Whether an upstream primary source exists is recorded per item.** "Known" does not mean it
can be skipped; it means **this document does not need to supply new evidence for it**.

| # | Behaviour | Known? | Primary source |
|---|---|---|---|
| P1 | An express-mode deploy does not roll back on failure, and later operations are locked to the mode | **Documented + upstream issue** | [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) / [nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265) / [aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931) |
| P2 | `cdk destroy --express` carries the same property | **Documented** | [cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html) |
| P3 | DynamoDB deletion protection refuses everyone, owner included | **Documented** | [WorkingWithTables.Basics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html) |
| P4 | Cognito deletion protection answers with `InvalidParameterException` | **Documented** | [Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html) |
| P5 | KMS does not bill during the waiting period, and bills retroactively if cancelled | **Documented** | [KMS pricing](https://aws.amazon.com/kms/pricing/) |
| P6 | A web ACL answers `WAFAssociatedItemException` until associations are removed | **Documented** | [DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html) |
| P7 | Blocks sandbox and production have separate commands and teardown paths | **Documented** | [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) |
| P8 | `Retain` resources survive a stack deletion | **Documented** (the counts are this document's measurement) | [DeletionPolicy](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html) |
| P9 | Changing a Block ID destroys data in a stateful Block | **Documented** | [AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) |
| P10 | Log groups outside the template survive, with retention set to never expire | **Documented + two upstream issues** (the surviving count is this document's measurement) | [Lambda logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html) / [aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553) / [aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815) |
| P11 | `npm create` waits indefinitely in a non-interactive shell | **npm's default behaviour** (the isolation is this document's measurement; the similar upstream PR is a different cause) | [npm config `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) / [nx-plugin-for-aws #1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193) |
| P12 | Hotswap introduces drift into the stack | **Documented** | [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) (`--hotswap`) |

**No AWS Support case was opened.** None of the twelve is a gap in service behaviour: each is
either behaviour the public documentation states, or already has an open issue on the tooling
side (CDK CLI or the Nx plugin). Nothing remains unexplained as service behaviour, so there is
nothing to ask about.

## The pitfall register

**Every entry carries its source.** The purpose of this project is to close the places people
and AI walk into, not to accumulate plausible-sounding cautions, so nothing goes in without
one.

### P1. Express mode is not reversible, and the mode sticks to the stack

From the generated `packages/infra/project.json` — the primary source:

```json
"deploy-sandbox": { "command": "cdk deploy --require-approval=never \"<stack>/**\" --express" }
```

What the AWS CDK CLI reference says about `--express`:

> Express mode allows for faster deployments through CloudFormation by reporting stack
> operations as completed as soon as CloudFormation applies the resource configuration.
> However, CloudFormation reports success without waiting for resources to stabilize.
> Additionally, express mode does not perform rollback automatically and will leave stacks
> in a failed state if something goes wrong.

Source: [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)
(`--express`). The same page advises against it for production deployments and says `--rollback`
restores automatic rollback. **The generated target does not pass `--rollback`.**

**This is already registered upstream.**
[awslabs/nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265)
reports that a replacement-type update through the generated express target stops with
`Replacement type updates not supported on stack with disable-rollback`, and offers
**`--express --rollback` together** as the workaround. The CDK CLI side is
[aws/aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931).

**How it catches you**: `deploy-sandbox` returns success, that gets read as "the resources are
stable", and the verification immediately after fails intermittently. Or it fails partway and
leaves the stack in a failed state.

**Dropping `--express` is not the fix.** A stack last updated in express mode requires
subsequent operations to be express as well. Measured on 2026-09-12, both of these were
refused:

| Recovery attempt | What comes back |
|---|---|
| `cdk rollback` | `RollbackStack is not supported for stacks that were last updated using EXPRESS deployment mode` |
| `cdk deploy` (no express) | `Follow-up operations must use the same DeploymentConfig (mode=EXPRESS)` |

So **only another express deploy can recover a broken express stack.** The recommendation is
therefore to change the target to `--express --rollback`; the remedy of dropping `--express` and
switching to `deploy` does not apply to a stack that express has already updated.

### P2. `cdk destroy --express` carries the same property

`cdk destroy` also takes `--express`, with the same "does not wait for stabilization, does not
roll back automatically" property and the same statement that it is not recommended for
production stack teardown (source:
[cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html)).
The generated `destroy-sandbox` does not pass `--express`, so the teardown side is on the safe
default.

### P3. How strong DynamoDB deletion protection is

<!-- allow:not-a-claim: the next line quotes the AWS documentation verbatim; it is not this document's claim -->
> When deletion protection is enabled for a table, it cannot be deleted by anyone.

Source: [Basic operations on DynamoDB tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html).
Disable it with `UpdateTable`, then delete.

**Where it applies**: one table in Nx, four in AWS Blocks (production preset). All of them also
carry `DeletionPolicy: Retain`, so a stack deletion does not even reach them.

### P4. How misleading the Cognito deletion-protection error name is

> When you try to delete a protected user pool in a `DeleteUserPool` API request, Amazon
> Cognito returns an `InvalidParameterException` error. To delete a protected user pool,
> send a new `DeleteUserPool` request after you deactivate deletion protection in an
> `UpdateUserPool` API request.

Sources: [Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html)
and UpdateUserPool's
[deletionProtection](https://docs.aws.amazon.com/sdk-for-kotlin/api/latest/cognitoidentityprovider/aws.sdk.kotlin.services.cognitoidentityprovider.model/-update-user-pool-request/deletion-protection.html).

**Where it applies**: Nx creates one with `DeletionProtection: ACTIVE`. Because the error is
named `InvalidParameterException`, it **reads as a problem with how the parameters were
written**, which is the part that catches you.

### P5. KMS deletion waits a minimum of 7 days, but the waiting period is not billed

The window is 7 to 30 days, 30 by default, the state is `PendingDeletion`, and
`CancelKeyDeletion` reverses it (sources:
[Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html),
[schedule-key-deletion](https://docs.aws.amazon.com/cli/latest/reference/kms/schedule-key-deletion.html)).

On billing, the pricing page says:

> There is no charge for customer managed KMS keys that you manage and are scheduled for
> deletion. If you cancel the deletion during the waiting period, the customer managed KMS
> key will incur charges as though it was never scheduled for deletion.

Source: [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/).

**Two ways it catches you**: (1) estimating "7 days of charges" — billing stops the moment
deletion is scheduled. (2) cancelling during the window bills as though it was never scheduled.
**Deciding to keep the key brings the cost back too.**

**Where it applies**: four in Nx (all with automatic rotation on), one in AWS Blocks
(production preset).

### P6. The order WAF web ACL deletion requires

`DeleteWebACL` answers `WAFAssociatedItemException` while the resource is still in use by
something else (source:
[DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)).
Deletion also needs a `LockToken`, and a change after fetching it produces
`WAFOptimisticLockException`.

**Where it applies**: three in Nx (2 REGIONAL + 1 CLOUDFRONT). The CLOUDFRONT-scoped one
belongs to the us-east-1 stack. They are designed to go with the stack deletion, but removing
them by hand goes association first, then ACL.

### P7. What differs between the AWS Blocks sandbox and production commands

| Command | What it does | Teardown |
|---|---|---|
| `npm run dev` | Local implementation. No AWS account | Not needed |
| `npm run sandbox` | Short-lived deployment via Lambda hot-swap, isolated per developer | `npm run sandbox:destroy` |
| `npm run deploy` | Production-oriented deployment through CDK | `npm run destroy` |

Sources: [CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html),
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html).
The best-practices page lists **not using a sandbox for production traffic** and using a
separate account per environment (source:
[Best practices for AWS Blocks](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html)).

**How it catches you**: treating `sandbox` and `deploy` as the same thing and reaching for the
wrong teardown command. Either teardown leaves the other one's resources alone.

### P8. `DeletionPolicy: Retain` resources left after a stack deletion

`DeletionPolicy: Retain` keeps the resource and only detaches it from the stack (source:
[DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)).
The behaviour itself is documented; what **this document adds is the count per output**.

Counted from the synthesized templates — resources a stack deletion does not remove (measured
2026-09-07):

| Output | Count | Breakdown |
|---|---|---|
| AWS Blocks (sandbox preset) | **0** | — |
| AWS Blocks (production preset) | 9 | DynamoDB 4 (deletion protection + Retain), KMS 1, CDK bucket-deployment custom resources 4 (Retain) |
| Nx Plugin for AWS | 9 | Cognito user pool 1 (deletion protection + Retain), DynamoDB 1 (same), IAM roles 2 (Retain), KMS 4 (Retain), log group 1 (Retain) |

**Only the AWS Blocks sandbox preset is at 0**, which makes it the easiest one to try first.

### P9. Treating preview as preview

AWS Blocks is in preview, and the documentation states that changing a Block ID (the second
constructor argument) deletes and recreates the corresponding AWS resources, which for a
stateful Block such as `KVStore` / `DistributedTable` / `Database` / `FileBucket` means
**permanent data loss**. Treat a Block ID as immutable once deployed (source:
[AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html)).

### P10. Log groups outside the template, and their never-expire retention

**The table above counts the template, and measurement showed that is not enough.**

Measured 2026-09-12: AWS Blocks (sandbox preset) deployed to ap-northeast-1 and torn down with
`npm run sandbox:destroy`. The stack, four DynamoDB tables and the S3 bucket all went, while
**five log groups stayed**. All five had `retentionInDays` unset (never expire), and all belong
to the Lambda functions behind CDK / Blocks custom-resource providers
(`BlocksGsiProviderframework` ×2, `BlocksSecretProviderframework`,
`CustomCDKBucketDeployment`, `CustomS3AutoDeleteObjects`).

<!-- allow:not-a-claim: the following describes our own measurement, not an assertion about a vendor gap -->
The template declared four log groups (the application handler plus three internal to Blocks),
and those went with the stack deletion. The five that stayed do not appear in the template.

**Both halves are on record upstream.**

- **The never-expire part**: the Lambda documentation states that the log group is created on
  the function's first execution and that its retention is set to never expire (source:
  [Lambda logs in CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)).
- **The CDK custom-resource part**: [aws/aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553)
  is open as a request to make CustomResourceProvider log groups removable and configurable,
  and [aws/aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815) reports that the log
  group created by `s3.Bucket`'s `autoDeleteObjects` stays on Never expire. Of the five that
  stayed here, `CustomS3AutoDeleteObjects` is the same one as in #24815.

**How it catches you**: the assumption that reading the template tells you what will be left
breaks. **A synth-based inventory structurally cannot see resources created outside
CloudFormation.**

<!-- allow:not-a-claim: a summary of an existing record elsewhere in this repository, not a new assertion -->
The same shape is on record for this repository's own portal, where 92 of 101 log groups
(9.0 MB) remained without an accompanying Lambda function
([portal-sandbox-lifecycle](../agent/portal-sandbox-lifecycle.md)).

**What to do**: at the end of the teardown, sweep log groups by stack-name prefix.

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/<stack-name>" \
  --query "logGroups[].[logGroupName,retentionInDays]" --output text
```

`storedBytes` is 0 right after a deploy, so the cost is close to nothing, but the count grows
with every redeploy.

### P11. A stall caused by a confirmation prompt invisible in a non-interactive shell

`npm create @aws/nx-workspace` was observed producing no output and creating nothing for 25
minutes (2026-09-07). That was initially read as "npm cannot generate this", and the
measurements were taken through pnpm instead.

**Isolating it showed the cause was npm's first-run install confirmation** (2026-09-12).
Running it with stdout captured shows it waiting here:

```
Need to install the following packages:
@aws/create-nx-workspace@1.0.0
Ok to proceed? (y)
```

The same command with `npm_config_yes=true` **completed in 45 seconds**, and the generated
`package.json` was confirmed to contain `@aws/nx-plugin@1.0.0`. **pnpm is not a requirement.**

**How it catches you**: the prompt is not newline-terminated, so automation reading logs line by
line sees nothing at all. "Stalled with no output" was not "no progress" but "waiting for
input". The same shape was observed with `npx cdk` (confirming the CDK install) and `npx pnpm`
(confirming pnpm@12).

**A different, easily conflated delay exists upstream.**
[awslabs/nx-plugin-for-aws PR #1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193)
addresses generation waiting on a slow response from npm's bulk advisory endpoint
(`POST /-/npm/v1/security/advisories/bulk`), recording a drop from 26 seconds to 414
milliseconds with `npm_config_audit=false`. **That is not what happened here.** A run with only
`npm_config_audit=false` kept waiting at the same prompt, and `npm_config_yes=true` released it.
The npm 10 `Cannot read properties of null (reading 'edgesOut')` covered by
[PR #1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228) does not apply either, as
this environment is on npm 11.17.0.

**This entry corrects a premise of the first measurement.** The comparison document keeps the
figures as measured through pnpm and only fixes the stated reason, so that the command in the
document matches the command the numbers came from.

### P12. The drift hotswap introduces

The CDK CLI states that `--hotswap` updates resources directly rather than through
CloudFormation and therefore **deliberately introduces drift** into the stack, and says not to
use it on production stacks. `--hotswap` implies `--no-rollback`, and the next non-hotswap
deployment is advised to include `--revert-drift` (source:
[cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)).

**Where it applies**: AWS Blocks' `npm run sandbox` uses hot-swap (P7). An operating model that
later updates the same stack through the `npm run deploy` path starts from a drifted state.
**Sandbox and production are not meant to share a stack** (source:
[Best practices for AWS Blocks](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html)).

## Teardown

**The order matters.** Remove protection → delete the stack → delete what is left, one by one.

```bash
# 1. Delete the stack (Retain and deletion-protected resources stay)
#    Blocks sandbox:    npm run sandbox:destroy
#    Blocks production: npm run destroy
#    Nx:                nx run @<workspace>/infra:destroy
#    A stack updated in express mode needs its later operations to be express too (P1)

# 2. DynamoDB: disable deletion protection, then delete (P3)
aws dynamodb update-table --table-name <name> --no-deletion-protection-enabled
aws dynamodb delete-table --table-name <name>

# 3. Cognito: set deletion protection to Inactive, then delete (P4)
aws cognito-idp update-user-pool --user-pool-id <id> --deletion-protection INACTIVE
aws cognito-idp delete-user-pool --user-pool-id <id>

# 4. KMS: schedule with the 7-day minimum window (P5; billing stops when it is scheduled)
aws kms schedule-key-deletion --key-id <id> --pending-window-in-days 7

# 5. Delete the IAM roles, log groups and S3 buckets left behind
aws logs delete-log-group --log-group-name <name>
aws iam delete-role --role-name <name>          # delete inline policies first

# 6. Sweep the log groups outside the template (P10; step 1 does not remove them)
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/<stack-name>" \
  --query "logGroups[].[logGroupName,retentionInDays]" --output text
```

**Confirm a deletion by state, not by an API return value.** Re-check that it is gone from the
listing after a few tens of seconds.

## Cost estimate

Deploying and tearing down on the same day leaves mostly time-prorated line items.

| Item | Unit price | Same-day teardown |
|---|---|---|
| WAF web ACL + rules (Nx: 3 ACLs + 6 rules) | $21 / month (prorated hourly) | about $0.12 for 4 hours |
| KMS CMK (Nx 4 + Blocks 1) | $1 / month each | stops when scheduled for deletion (P5) |
| Cognito MAU | Plus $0.020 / MAU | as many test users as you create; effectively zero for 1-2 |
| Lambda / API Gateway / DynamoDB / CloudFront / S3 | usage-based | cents at verification scale |

The unit prices and retrieval date are in the
[fixed-cost section of the comparison](scaffolding-and-backend-toolkit-choices.md#the-fixed-cost-difference)
(AWS Price List API, ap-northeast-1, retrieved 2026-09-07). **A same-day teardown should total
under $1**; $45 a month is the figure for leaving it running.

## Measured results

> Categories follow [Verification categories](#verification-categories) above, and **what was
> not done is stated rather than left blank**.

Environment: ap-northeast-1, a verification account (shared with the FSx for ONTAP test
environment), Node.js v26.4.0, npm 11.17.0.

| Output | Category | Deploy | Operations confirmed | Teardown | Date |
|---|---|---|---|---|---|
| AWS Blocks (sandbox preset) | **Live E2E** | `npm run sandbox`. **83 resources** (matching the 83 measured at synth) | Over JSON-RPC: `authApi.setAuthState` (signUp / signIn), `api.createTodo` (write), `api.listTodos` (read). Persistence to DynamoDB confirmed from the response | `npm run sandbox:destroy`, 86 seconds. The stack, four DynamoDB tables and S3 went; **five log groups stayed** (P10). Removed by hand and confirmed at 0 | 2026-09-12 |
| AWS Blocks (production preset) | — | Not done | — | — | — |
| Nx Plugin for AWS | — | Not done | — | — | — |

## Sources

- [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html) / [cdk destroy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-destroy.html) — the properties of `--express`, `--rollback` and `--hotswap`
- [CloudFormation express mode](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-express-mode.html) / [DeletionPolicy attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html)
- [AWS Blocks CLI reference](https://docs.aws.amazon.com/blocks/latest/devguide/cli-reference.html) / [concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) / [best practices](https://docs.aws.amazon.com/blocks/latest/devguide/best-practices.html) / [getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html)
- [DynamoDB: Using deletion protection](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithTables.Basics.html)
- [Cognito: Deletion protection](https://docs.aws.amazon.com/help-panel/cognito/latest/console/hp-deletion-protection.html)
- [KMS: Deleting keys](https://docs.aws.amazon.com/kms/latest/cryptographic-details/key-deletion.html) / [KMS pricing](https://aws.amazon.com/kms/pricing/)
- [WAF: DeleteWebACL](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteWebACL.html)
- [Lambda logs in CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [npm config: `yes`](https://docs.npmjs.com/cli/v11/using-npm/config#yes) — auto-answering `npm create`'s confirmation prompt
- Upstream issues / PRs: [nx-plugin-for-aws #1265](https://github.com/awslabs/nx-plugin-for-aws/issues/1265) (the express target), [#1193](https://github.com/awslabs/nx-plugin-for-aws/pull/1193) (advisory-fetch latency), [#1228](https://github.com/awslabs/nx-plugin-for-aws/pull/1228) (npm 11 prerequisite), [aws-cdk-cli #1931](https://github.com/aws/aws-cdk-cli/issues/1931), [aws-cdk #26553](https://github.com/aws/aws-cdk/issues/26553), [aws-cdk #24815](https://github.com/aws/aws-cdk/issues/24815)
- The generated output itself: `packages/infra/project.json` (Nx target definitions), `aws-blocks/index.cdk.ts` and `package.json` (Blocks commands and presets)

> Content is summarized and restructured for readability.

## Related documents

- [App foundation choices](scaffolding-and-backend-toolkit-choices.md) — how the three compare, the measurements up to synth, and fixed costs
- [Portal verification results](../../solutions/amplify-portal/docs/verification-results.en.md) — the record the verification categories come from
