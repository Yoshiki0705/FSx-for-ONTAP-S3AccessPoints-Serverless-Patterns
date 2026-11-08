# OPS7: ONTAP Command and REST API Snapshot

🌐 **Language / 言語**: [日本語](README.md) | English

A Lambda that records, per ONTAP version, which CLI commands and REST endpoints the ONTAP administrator in a secret can use. Take it as often as you check the ONTAP version, and a version change shows up as a diff against the previous run.

The pattern originates in [`solutions/ontap-catalog-snapshot/` of FSx-for-ONTAP-Cyber-Resilience-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/tree/main/solutions/ontap-catalog-snapshot). It is placed here with the `operations/` conventions applied (Python 3.13, arm64, tags, registration points).

---

## Credentials: an Exception to D28

This version **uses the `fsxadmin` (ONTAP administrator) credential.** D28 in [`docs/harvest-metrics-decisions.md`](../../docs/harvest-metrics-decisions.md) decides that `fsxadmin` is not shared and that each cluster gets an `fsxadmin-readonly` user. This version does **not** follow that decision, for two reasons.

- Whether a read-only user can read the four commands this Lambda uses (`security login role show`, `show-user-capability`, `show-rest`, `show-ontapi`) is **not confirmed**. Confirming it needs a user to be created (a write to ONTAP), which will be done separately with its own approval.
- It runs once a week and stops at the first refused credential (below). The risk of a lockout is smaller than for monitoring that polls continuously. It is not zero.

What matches D28: one secret per file system (the `FileSystemId` tag check) and stopping at the first failed authentication. What does not: using `fsxadmin`, and stopping across runs.

With a read-only user, items it cannot read are left in `unavailable` of `manifest.json` with the HTTP code, and the run continues (what could be read is recorded). A refused credential is different: it stops the whole run.

---

## What It Records

| Record | Source (ONTAP) | Narrowed by permission |
|---|---|---|
| CLI commands the user can run | `security login role show-user-capability` | Yes (the running user's) |
| Every REST endpoint | `security login role show-rest` | No |
| Role definitions | `security login role show` | No |
| Old API to CLI map | `security login role show-ontapi` | No |
| Whether a REST GET works | One GET to each path without a path parameter | Yes |

- Only **HTTP codes and error codes** are recorded. Response bodies (settings, licences) are not stored.
- Only **GET** is sent. POST, PATCH and DELETE are never sent.
- What a record means **depends on the running user**. `ran_as` in `manifest.json` holds the user name.

For the result of taking the same data by hand on a real file system and how to read it, see [the ONTAP command and REST API snapshot](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/blob/main/docs/ontap-native/ontap-command-api-snapshot.md) in the Cyber Resilience Spoke.

---

## Architecture

```
EventBridge (rate) ──→ Lambda: snapshot (in VPC) ──→ ONTAP management endpoint (GET only)
                              ├──→ Secrets Manager (the one secret you name)
                              └──→ S3 (snapshot and diff) ──→ SNS (optional, counts only)
```

The other six patterns under `operations/` use Step Functions (collect, analyze, report). This one is a **single Lambda**: a Step Functions retry of `States.TaskFailed` can re-run with a credential that was already refused. It also does not use `shared/ontap_client.py`, which embeds `urllib3.Retry(total=3)` and raises on a 401 without telling its causes apart, so it has no stop at the first refused credential. The handler uses only the standard library and boto3.

The function needs a route from the VPC to S3 and Secrets Manager (existing VPC endpoints or a NAT gateway). The template creates none.

---

## Output

```
s3://<bucket>/<OutputPrefix>/<FileSystemId>/
  latest.json                          # pointer to the newest run
  <ONTAP version>/<yyyymmddThhmmssZ>/
    manifest.json                      # version, counts, ran_as, unavailable items
    diff.json                          # diff against the previous run
    cli-user-capability.json           # CLI commands the user can run
    rest-endpoints.json                # every REST endpoint with its GET result
    roles.json                         # role entries
    show-ontapi.json                   # ONTAPI to CLI map
```

[`examples/manifest.example.json`](examples/manifest.example.json) and [`examples/diff.example.json`](examples/diff.example.json) show the structure (the content of `diff.example.json` is illustrative). The bucket keeps object versions and survives stack deletion.

`diff.json` shows, against the previous run, the following. When `changed` is `true`, an optional SNS topic receives counts only.

- CLI commands added or removed
- REST endpoints added or removed
- Endpoints whose GET HTTP code changed

---

## Deploy

### Prerequisites

1. A subnet in the VPC that can reach the management endpoint (it is reachable only from inside the VPC). The template can create the security group.
2. A route from that subnet to Secrets Manager and S3 (VPC endpoints or a NAT gateway). `scripts/discover-network.sh` looks the values up (see below).
3. A secret with the ONTAP administrator credential (JSON with `username` and `password`). Use **the secret that belongs to this file system**.
4. The DNS name of the management endpoint (`OntapConfiguration.Endpoints.Management.DNSName` from `aws fsx describe-file-systems`).
5. Room in the account's Lambda concurrency limit. The function reserves a concurrency of 1.

> **Keep one secret per file system.** Every FSx for ONTAP file system uses the user name `fsxadmin`. A secret from another file system fails to authenticate, and repeating that locks the account. Choose the secret by its `FileSystemId` tag, not by its name. When the tag differs from the `FileSystemId` parameter, the Lambda stops without sending anything to ONTAP. A missing tag only logs a warning.

### Security group

The function needs **outbound HTTPS (443) only**, and nothing inbound. It must reach three places on 443.

| Destination | Why | What the other side needs |
|---|---|---|
| The FSx for ONTAP management endpoint | Reads the ONTAP REST API | The security group on the file system network interfaces allows 443 from the function |
| Secrets Manager | Reads the credential | The VPC endpoint's security group allows 443 from the function (not needed through a NAT gateway) |
| S3 | Writes the snapshot | Outbound 443 to the gateway endpoint's prefix list (not needed through a NAT gateway) |

With `CreateSecurityGroup=true` (the default) the template builds this.

- It creates a security group for the function: outbound 443 to the three places above, no inbound.
- It adds **an inbound rule allowing 443 from the function's group** to the existing file system and Secrets Manager endpoint groups. The rules are removed with the stack. Whoever deploys needs `ec2:AuthorizeSecurityGroupIngress`.
- A missing value stops the deployment itself (`Rules`). You do not build a group that cannot reach anything and find out at the first run 15 minutes later.

A read-only script looks the values up. It creates nothing and never reads a secret value.

```bash
scripts/discover-network.sh fs-0123456789abcdef0 ap-northeast-1
```

Copy `FsxSecurityGroupId`, `SecretsEndpointSecurityGroupId`, `S3PrefixListId` and `VpcId` from its output into `samconfig.toml`. Without VPC endpoints, using a NAT gateway, the script points to `AllowOutboundHttpsToInternet=true` (it allows one outbound 443 rule to `0.0.0.0/0`). To use your own group, set `CreateSecurityGroup=false` and pass `VpcSecurityGroupIds`; you then provide the allowances in the table yourself.

### Steps

```bash
cd operations/ontap-catalog-snapshot
cp samconfig.toml.example samconfig.toml     # replace the placeholders
sam build
sam deploy
```

The handler does not import `shared/`, so no `build.sh` is needed.

```bash
aws lambda invoke --function-name fsxn-ontap-catalog-snapshot-snapshot --payload '{}' --cli-binary-format raw-in-base64-out /tmp/out.json
cat /tmp/out.json
```

---

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `FileSystemId` | required | Names the output and is checked against the secret's tag |
| `ManagementEndpoint` | required | DNS name or IP of the management endpoint |
| `OntapSecretArn` | required | Secret with the administrator credential |
| `SecretKmsKeyArn` | empty | Only when the secret uses a customer managed KMS key |
| `VpcSubnetIds` | required | Subnets for the function |
| `CreateSecurityGroup` | `true` | `true` creates the function's security group and the inbound 443 rules on the existing groups. `false` uses `VpcSecurityGroupIds` as given and creates no rule |
| `VpcId` | empty | VPC of the subnets. Required when `CreateSecurityGroup=true` |
| `FsxSecurityGroupId` | empty | Security group of the file system network interfaces. Required when `CreateSecurityGroup=true` |
| `SecretsEndpointSecurityGroupId` | empty | Security group of the Secrets Manager VPC endpoint. Empty through a NAT gateway |
| `S3PrefixListId` | empty | Prefix list of the S3 gateway endpoint. Empty through a NAT gateway |
| `AllowOutboundHttpsToInternet` | `false` | `true` allows outbound 443 to `0.0.0.0/0` (Secrets Manager and S3 through a NAT gateway) |
| `VpcSecurityGroupIds` | empty | Your own groups, used only when `CreateSecurityGroup=false` |
| `ExistingOutputBucketName` | empty | Empty creates a versioned, encrypted bucket |
| `OutputPrefix` | `ontap-catalog` | Key prefix inside the bucket |
| `ScheduleState` | `ENABLED` | `DISABLED` creates no schedule and the function runs only when invoked. **Use this, not an empty string**: `sam deploy` ignores an empty value and uses the default |
| `ScheduleExpression` | `rate(7 days)` | EventBridge expression, used when `ScheduleState` is `ENABLED` |
| `ProbeRestGet` | `true` | Whether to measure GET |
| `ProbeMaxEndpoints` | `400` | Upper bound on measured GETs |
| `VerifySsl` | `false` | Whether to verify the management endpoint certificate. The default certificate is not signed by a public CA |
| `NotificationTopicArn` | empty | SNS topic notified when something changed (counts only) |
| `LogRetentionInDays` | `90` | Log retention |

The common `operations/` parameters (`FileSystemIds`, `AutomationLevel`, `DemoMode` and so on) do not exist here: the pattern is one file system, one stack, read only.

---

## Protecting the Administrator Account

One run uses the same administrator credential hundreds of times. **Repeating failed authentication can lock the ONTAP administrator**, so the following is in place.

| Mechanism | Implementation | Checked by |
|---|---|---|
| Stop the whole run at the first failed authentication | ONTAP code `6691623`, or a 401 without a code, raises `AuthenticationAbort` | Unit test: only one request is sent after the failure |
| Do not stop on a role-based 401 | A 401 with a different ONTAP code is only recorded | Unit test: later endpoints are still measured |
| No automatic retry | `EventInvokeConfig.MaximumRetryAttempts: 0` and an EventBridge `RetryPolicy` of 0 | Template test |
| One run at a time | `ReservedConcurrentExecutions: 1` | Template test |
| Never use another file system's secret | `FileSystemId` tag check; nothing is sent to ONTAP on a mismatch | Unit test |
| Never log the password | SDK loggers pinned to WARNING (even with `LOG_LEVEL=DEBUG`) | Unit test |
| Do not store response bodies | Only HTTP codes and error codes | Unit test |
| Validate REST paths | Only paths matching `^/[A-Za-z0-9/_.-]+$` returned by ONTAP are used | Unit test |

---

## Limits and What Is Not Established

### No Stop Across Runs

The stop works **only within one run**. After a refused credential, if the schedule is enabled, **the function uses the same credential again the next week.**

While the refusal continues, one failed authentication accumulates every week and the administrator can be locked. This Lambda does not tell a lockout from a wrong password, and whether ONTAP offers a way to tell them apart was not checked. The recovery used here is resetting the password (`FsxAdminPassword` of `aws fsx update-file-system`) and updating the secret.

**What the operator does:** when a run stops on a failed authentication (the Lambda fails), do not run it again until the cause is fixed. Disable the EventBridge rule if needed.

```bash
aws events disable-rule --name <rule-name>
```

A design that disables the schedule automatically on failure is not included. It would require granting `events:DisableRule` to the function, which widens the IAM scope, so it is left as a separate decision.

### Other

- **Behaviour with a read-only user is not confirmed.** Items it cannot read stay in `unavailable` of `manifest.json` with the HTTP code.
- Only GETs without a path parameter are measured (219 of 570 on ONTAP 9.18.1P6 in the Cyber Resilience Spoke's real run). The rest need a value such as `{uuid}` that the Lambda does not know.
- POST, PATCH and DELETE are never tried, because they have side effects.
- This is not a list of "every CLI command": only commands mapped to an API and commands the running user can use.
- When less than 90 seconds of the run remain, the GET measurement stops and `probe_truncated` is `true`.
- Multi-AZ and other ONTAP versions are not confirmed.

---

## Verification Status

| Item | Status |
|---|---|
| Unit tests (Python 3.13, ONTAP replaced by a fake) | Pass |
| cfn-lint | Pass |
| Real run in the Cyber Resilience Spoke | ONTAP 9.18.1P6, Single-AZ, `fsxadmin`, Python 3.12: succeeded 3 times (18–19 s); output matched data taken by hand |
| Run on Lambda with this Spoke's template (Python 3.13, arm64) | Succeeded once (19 s, 102 MB peak). ONTAP 9.18.1P6, Single-AZ, `fsxadmin`, `ap-northeast-1`. 1,744 CLI commands, 570 REST endpoints, 1,045 ONTAPI mappings, 219 measured GETs: the same counts as the Cyber Resilience Spoke's real run. No password in the artifacts, logs or response |
| The security group this template creates | Used in that run (outbound 443 only, two allow rules on existing groups). A second run, Multi-AZ and other versions are not confirmed |
| Stop on a failed authentication | Unit test only; not triggered on a real system, to avoid a lockout |
| Diff when the ONTAP version changes | Unit test only |

It ran once. As the first run, `diff.json` says "first snapshot", so a diff against a previous run is not confirmed on Lambda (unit tests only). Run-time variation is not confirmed.

---

## Cleanup

```bash
aws cloudformation delete-stack --stack-name fsxn-ontap-catalog-snapshot
aws cloudformation wait stack-delete-complete --stack-name fsxn-ontap-catalog-snapshot
```

- **Time:** about 20 minutes when measured (one observation). About 19.5 minutes of that is deleting the function that sits in the VPC; the rest is under 15 seconds. The wait is the network interface being released, and no step shortens it. Use `wait`.
- **Order:** the two allow rules added to the existing file system and Secrets Manager endpoint groups go first, then the function, then the function's security group. The security group was never blocked as "in use" in the measurement. Rules of other clients are untouched.
- **What stays:** the output bucket only. The snapshots are the record, so it is `Retain`. Logs, the security group and the IAM role go with the stack.
- **Removing the bucket:** versioning is on, so emptying it leaves old versions and delete markers behind and the bucket cannot be deleted. The script handles only a bucket carrying this pattern's tag, removes every version, then the bucket. Without `--yes` it only lists and changes nothing. **It cannot be undone.** Do not run it if you want to keep the record.

```bash
scripts/delete-output-bucket.sh <bucket> ap-northeast-1          # list only
scripts/delete-output-bucket.sh <bucket> ap-northeast-1 --yes    # remove
```

---

## Related

- [Origin (Cyber Resilience Spoke)](https://github.com/Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns/tree/main/solutions/ontap-catalog-snapshot)
- [D28: the ONTAP credential decision](../../docs/harvest-metrics-decisions.md)
- [operations/ overview](../README.md)

---

<!-- playbook-reading:start -->
## Read before going to production

How the constraints that surface after deploying translate into design decisions is covered in the [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). The same content in two places means the copy that stops being updated outlives the one that was corrected.

- [Operate](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/05-operate) — where the decisions concentrate for this pattern
- [Performance](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/performance) — read next
- [Build](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — run through before production (every pattern)
<!-- playbook-reading:end -->
