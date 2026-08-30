# S3 Access Points for FSx for ONTAP — Dual-Layer Authorization Model

🌐 **Language / 言語**: [日本語](s3ap-authorization-model.md) | English

## Overview

Amazon FSx for NetApp ONTAP S3 Access Points use a **dual-layer authorization model**. For a request made through the S3 API to reach data, it must pass **both** the AWS-side authorization (Layer 1) and the file-system-side authorization (Layer 2).

**The two layers are independent. There is no subtraction across them.** An operation allowed at Layer 1 can be denied at Layer 2, and the reverse also happens.

> **Design Principle**: The S3 API does not strip file system semantics. Even when accessed through an S3 Access Point, file access permissions on the volume continue to apply.

**Each layer narrows access by a different mechanism.** Confusing the two produces a design that looks restricted but is not.

| Layer | What it evaluates | What narrows access at this layer |
|---|---|---|
| **Layer 1: AWS-side IAM authorization** | The calling principal and the `s3:` action | **An explicit deny** (`Deny`) |
| **Layer 2: File-system-side permissions** | The file permissions held by the single identity pinned to the access point (UNIX / Windows user) | **mode bits / ACLs** |

> **Evidence**: every measured value in this document comes from `ap-northeast-1` / ONTAP `9.18.1P3D1`, with a same-session control for each finding.
> - **2026-08-17 / 08-18**: Layer 1 evaluation order, condition keys, `NotPrincipal`, policy size, the Layer 2 paired measurement, and the audit subject. Procedure and full results in [S3 Access Point permission design — evaluation order and the two layers that narrow access](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/domains/security-governance/notes/access-point-authorization-layers.md).
> - **2026-08-18 / 08-19 (measured in this repository)**: Layer 1 evaluation on an NTFS volume, the 20 actions an access point policy accepts or rejects, the cause of the SLAG denial, the audit subject on an AD-joined SVM, and applying an IAM principal to a UNIX-identity access point.

## Authorization Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    S3 API Request                            │
│            (GetObject / PutObject / ListObjectsV2)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AWS-side Authorization                            │
│                                                             │
│  Evaluated in order; stops as soon as the outcome is fixed:  │
│  1. Default is an implicit deny                             │
│  2. Any explicit deny settles it → THIS is where you narrow  │
│  3. Organizations RCP / SCP                                 │
│  4. identity-based policy and the access point policy       │
│     - Same account:  COMBINED (either one allowing suffices) │
│     - Cross-account: BOTH must allow                        │
│  5. VPC endpoint policy (when going through a VPC endpoint)  │
└─────────────────────────┬───────────────────────────────────┘
                          │ (passed)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: File-system-side Authorization                    │
│                                                             │
│  Authorized as the single file system identity pinned to    │
│  the access point:                                          │
│  • UNIX identity    → UNIX security style volumes           │
│    - Controlled by mode bits or NFSv4 ACLs                  │
│  • Windows identity → NTFS security style volumes           │
│    - Controlled by Windows ACLs                             │
│                                                             │
│  → Who the caller was is NOT distinguished at this layer    │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: AWS-side Authorization

### Evaluated Policies

| Policy Type | Description | Configuration Location |
|-------------|-------------|----------------------|
| IAM identity-based policy | Permissions of the caller (e.g., Lambda Role) | IAM Console |
| S3 Access Point resource policy | Resource policy on the AP itself. **Not a bucket policy** — there is no S3 bucket underneath, so `put-bucket-policy` has no target | `s3control put-access-point-policy` |
| VPC endpoint policy | Endpoint policy for VPC-restricted APs | VPC Console |
| Service Control Policies | Organization-level controls | AWS Organizations |

**This evaluation does not depend on the volume's security style.** The same twelve trials were run on a UNIX-style and an NTFS-style volume and produced no difference (the NTFS side used a WINDOWS-identity access point on a non-AD SVM).

### Writing a narrow `Allow` does not narrow access

**Within a single account, the identity-based policy and the access point policy are combined. Either one allowing is enough.** The access point policy is a place to grant additional access, not a ceiling.

| Policy | Caller | Operation | Result |
|---|---|---|---|
| None | IAM user | `GetObject` / `ListObjectsV2` | Succeeds (the identity-based policy alone establishes the allow) |
| `Allow` for a role only | IAM user (**not listed in the AP policy**) | `GetObject` | **Succeeds** |
| Same as above | The role | `PutObject` (**`Action` not listed**) | **Succeeds** — `Action` is also decided by the combination |

**Not having an access point policy is not a cause of `AccessDenied`.** That same-account access works without one is separately measured in this repository ([AD-joined SVM S3 AP prerequisites](en/ad-joined-svm-s3ap-prerequisites.md#when-ap-resource-policy-is-required)).

> **On the conflicting sources**: AWS's [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html) reads as though the caller's identity-based policy must grant the permission **and** the access point resource policy must also permit the action. The next paragraph on that page says only that all relevant policies are evaluated, and the [IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-basics.html) states that same-account requests are judged on the **combination** of identity-based and resource-based policies. **The measurements agree with the combination.**

### Narrowing at Layer 1 — the explicit deny

Narrowing happens at evaluation step 2. An explicit deny is evaluated first and ends the evaluation when it matches.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPipelineRoleReadOnly",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"},
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ]
    },
    {
      "Sid": "DenyAnyPrincipalOutsideTheAllowList",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:PrincipalArn": "arn:aws:iam::123456789012:role/ProcessingLambdaRole"
        }
      }
    }
  ]
}
```

**The `Deny` half is the substance.** Keep only the top half and, per the table above, other principals still get through. Measured: the named role succeeded; an IAM user with administrator permissions that was not named got `AccessDenied`.

> **Security note**: writing `s3:*` in the `Deny` action with the access point ARN as the resource also covers `s3:PutAccessPointPolicy` and `s3:DeleteAccessPointPolicy`, so it **can deny the policy management operations and lock you out.** The example above is limited to data operations. **This lockout was not measured** — recovery may require recreating the access point, so it was deliberately not attempted.

### Do not build exceptions with `NotPrincipal`

**`Deny` plus `NotPrincipal` denied even the principals listed as exceptions.** What had to be enumerated for the exception to hold:

| Listed in `NotPrincipal` | IAM user | Assumed role |
|---|---|---|
| The principal ARN only | **Denied** | Denied |
| The principal ARN + the **account ARN** | Succeeds | Denied |
| Role ARN + account ARN | Denied | **Denied** |
| Role ARN + session ARN + account ARN | Denied | Succeeds |

Two things follow. **The account ARN (`arn:aws:iam::<account>:root`) must be listed alongside**, and **for a role both the role ARN and the assumed-role session ARN are required.** The session name is chosen at `AssumeRole` time, and **`NotPrincipal` does not accept wildcards** — so "any session of this role" cannot be expressed.

**`NotPrincipal` is therefore unusable when the target is a role.** Use `Condition` with `StringNotEquals` on `aws:PrincipalArn` instead. For an assumed-role session `aws:PrincipalArn` resolves to the role ARN, so it does not depend on the session name (confirmed with three different session names).

### Measured condition keys

| Condition key | What it narrows | Measured |
|---|---|---|
| `aws:PrincipalArn` | The caller's ARN; independent of session name | Allow and Deny sides both confirmed |
| `aws:SourceVpce` | The VPC endpoint traversed | Allow and Deny sides both confirmed |
| `aws:PrincipalOrgID` | Organization membership | Allow and Deny sides both confirmed (measured with a principal from a different organization) |
| `s3:prefix` | The scope of `ListBucket`; applies to `ListBucket` only | Allow and Deny sides both confirmed |
| `aws:SecureTransport` | Transport encryption | **The Deny branch was never reached** (below) |

**Do not cite `aws:SecureTransport` as the reason plaintext traffic is blocked.** Unsigned and signed HTTP requests were both redirected to HTTPS with HTTP 307, so **the path changes before authorization is evaluated.** AWS documentation likewise states that access points accept HTTPS only and return a redirect for HTTP. Keeping the statement as defence in depth is harmless, but no path exists on this access point where the key evaluates to `false`.

### The policy size limit is judged after normalization

| Policy applied (unformatted JSON) | Result |
|---|---|
| 24,620 bytes | Succeeded |
| 24,861 bytes | `MalformedPolicy: Normalized policy document exceeds the maximum allowed size` |

**The documented limit is 20 KB, but the check runs against the normalized document.** The byte count of your local JSON cannot be used as the budget, and the boundary moves with how the policy is written. It also does not match the 200,000 characters that the `S3AccessPoint.Policy` field of `CreateAndAttachS3AccessPoint` accepts. **Avoid designs that approach the limit; split the access point instead.**

### Actions that cannot be used in an access point policy

**Twenty actions were applied one at a time to determine this.**

| Verdict | Actions |
|---|---|
| **Rejected** | `s3:GetBucketLocation` / `s3:PutBucketPolicy` / `s3:DeleteBucketPolicy` / `s3:GetBucketVersioning` / `s3:PutBucketVersioning` / `s3:PutBucketNotification` / `s3:PutAccessPointPolicy` |
| Accepted | `s3:ListBucket` / `s3:GetBucketPolicy` / `s3:ListBucketVersions` / `s3:GetBucketNotification` / `s3:ListBucketMultipartUploads` / `s3:AbortMultipartUpload` / `s3:ListMultipartUploadParts` / `s3:GetObjectVersion` / `s3:GetObject` / `s3:DeleteObject` / `s3:PutObjectTagging` / `s3:GetObjectTagging` / `s3:GetObjectAttributes` / `s3:*` |

**The error does not name the offending action.** All you get back is `Policy has invalid action`. **When several actions are in one policy and it is rejected, the message does not tell you which one is at fault.** Apply them one at a time to find out.

> **A correction to this repository's earlier text.** This section previously said the two rejected
> actions were `s3:GetBucketLocation` and `s3:ListBucketMultipartUploads`. **`s3:ListBucketMultipartUploads`
> is accepted** (3/3 when applied alone). The
> [measurement record](../solutions/edge/media-ivs-vod-publishing/direct-recording-experiment.md) the
> earlier text drew on had both in a single policy, and because the message names neither action, the
> rejection was attributed to both. `s3:PutBucketPolicy` was rejected 3/3.

`s3:GetBucketLocation` **is usable in an identity-based policy** — many templates in this repository use it. The restriction is specific to the access point resource policy.

**`s3:ListObjectsV2` and `s3:HeadBucket` are also rejected, for a different reason.** Neither is an IAM action name (the IAM action behind both `ListObjectsV2` and `HeadBucket` is `s3:ListBucket`). **It does not mean those operations are unsupported.**

### IAM Policy ARN Format

S3 Access Points for FSx for ONTAP use a different ARN format from regular S3 bucket ARNs:

```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap"
},
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-fsxn-ap/object/*"
}
```

> **Note**: using the S3 AP alias (`xxx-ext-s3alias`) in the `arn:aws:s3:::` format will not be recognized by IAM. Always use the `arn:aws:s3:{region}:{account}:accesspoint/{name}` format. AWS's [Troubleshooting access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html) likewise says to change the policy to the access point ARN when the bucket ARN format is in use.

### Cross-account data access does work

**"Same-account ownership is required" constrains creating the access point, not using it.**

| Question | Reality |
|---|---|
| Create an access point on a volume in another account | Not possible — the file system and the access point must be owned by the same account |
| **A principal in another account (another organization) reading data through the access point** | **Possible.** Allowing it in the access point policy is sufficient (measured) |

**Confusing these drops a design option.** Teams tend to reach for a copy in order to share data with another account, but allowing the other account in the access point policy removes the need for one. Inverted, **an unintended share also takes only one access point policy.** To keep data inside the organization, a `Deny` on `aws:PrincipalOrgID` is the stop that was confirmed by measurement. Design patterns are in [Cross-account S3 AP](multi-account/cross-account-s3ap.md).

## Layer 2: File-system-side Authorization

### Role of the File System ID

The file system ID specified when creating the S3 Access Point is used for authorization of all S3 API requests:

- **Read-only user** associated → Only read requests are authorized; writes are blocked
- **Read-write user** associated → Both read and write requests are authorized

**Allow and deny flip at Layer 2 alone, with the access point policy untouched.** A paired measurement with the same caller, the same access point and no access point policy, changing only the owner and mode bits of the volume root:

| Volume root `uid` / `gid` / mode bits | UNIX user pinned to the AP | `PutObject` |
|---|---|---|
| `0` / `0` / `755` | The user with uid 7101 | **`AccessDenied`** |
| `7101` / `7100` / `755` | The same user | **Succeeds** |

**This `AccessDenied` comes from Layer 2, not Layer 1.** Looking only at Layer 1 means searching for the cause inside a policy that does not contain it.

**A Layer 2 `AccessDenied` carries a bare `Access Denied` body.** Matching an explicit deny at Layer 1 appends `with an explicit deny in a resource-based policy`, so the body itself distinguishes the layers.

### The pinned identity must be resolvable by the SVM

**It is not something you create on the AWS side.** It has to be a user the ONTAP SVM can resolve.

| Identity type | What is required | Measured |
|---|---|---|
| `UNIX` | A UNIX user the SVM can resolve | **Neither LDAP nor NIS is required.** On an SVM with `nsswitch` set to `files` only, `ldap.enabled=false` and `nis.enabled=false`, a local UNIX user brought the access point to `AVAILABLE` and reads and writes worked |
| `WINDOWS` | A Windows user the SVM can resolve | **An Active Directory join is not required.** A local Windows user on a CIFS server in workgroup mode carried reads and writes |

AWS's [Troubleshooting access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html) states for `UnixUser` that the ns-switch `files` source is sufficient. For `WindowsUser` it describes only the joined Active Directory domain case, so **the workgroup-mode measurement above is a broader result than the documentation.**

> **Design note**: it is not the case that LDAP or AD must be in place before S3 access points can be used. On the other hand, **local users are per-SVM.** Reusing the same identity across several SVMs, or an identity inventory requirement, is a separate reason to move to a directory service.

Do **not** put an AD domain prefix in `WindowsUser.Name` (`Admin` is correct, `DOMAIN\Admin` is not; a **CIFS server name** prefix such as `CIFSSRV\Admin` was measured working). With an AD domain prefix the access point is created and reaches `AVAILABLE`, but every data operation returns **503 ServiceUnavailable**, `HeadBucket` included — not `AccessDenied`. See [AD-joined SVM S3 AP prerequisites](en/ad-joined-svm-s3ap-prerequisites.md).

### Security Style Mapping

| Volume Security Style | ID Type Used | Permission Control Method |
|-----------------------|--------------|--------------------------|
| UNIX | UNIX identity (user name) | mode-bits / NFSv4 ACLs |
| NTFS | Windows identity (user name only, no domain prefix) | Windows ACLs |

### `FileSystemIdentity` cannot be changed after creation

**There is no update API.** Amazon FSx exposes three operations for this attachment — `CreateAndAttachS3AccessPoint`, `DescribeS3AccessPointAttachments` and `DetachAndDeleteS3AccessPoint`. None of them updates it.

| Parameter | Changeable after creation |
|---|---|
| `FileSystemIdentity.Type` (`UNIX` / `WINDOWS`) | **No** |
| `UnixUser.Name` / `WindowsUser.Name` | **No** |
| `OntapConfiguration.VolumeId` | **No** — it cannot be pointed at a different volume |
| `S3AccessPoint.VpcConfiguration` (`NetworkOrigin`) | **No** |
| `S3AccessPoint.Policy` | Yes, through the S3 API |

**Recreation is scoped to the one access point** and does not touch the volume or its data. **The alias changes, however** (`<name>-<random>-ext-s3alias`). Any consumer with the alias embedded in its configuration has to be updated too.

**This shapes permission design.** Because you cannot swap in a read-only identity later, **splitting access points by purpose** is what this turns into operationally.

### Important Behavioral Characteristics

1. **No impact on NFS/SMB access**: attaching an S3 Access Point does not change existing NFS/SMB access in any way. AP policy restrictions apply only to requests via the AP.

2. **Block Public Access**: S3 APs attached to FSx for ONTAP always have Block Public Access enabled, and this cannot be changed.

3. **MISCONFIGURED state**: reached for two reasons. Amazon FSx periodically checks and automatically returns the AP to `AVAILABLE` when the issue is resolved.
   - The file system identity can no longer be resolved (the user was removed from the name service, or the name service is unreachable)
   - **The attached volume went offline or was unmounted (lost its junction path)**

## Least-Privilege Design Guidelines

To apply least privilege, access must be restricted at **both layers** — and **each layer can guarantee different things.**

| What you want to guarantee | Mechanism | Why |
|---|---|---|
| Only specific principals can use it | Layer 1 **explicit deny** + `Condition aws:PrincipalArn` | A narrow `Allow` still combines with identity-based policies and lets callers through |
| Only specific network paths can use it | Layer 1 explicit deny + `aws:SourceVpce` / `aws:PrincipalOrgID` | Same as above |
| Only a specific prefix is reachable | Layer 1 explicit deny + `NotResource` (objects) + `s3:prefix` (listing) | `s3:prefix` applies to `ListBucket` only |
| **Writes are impossible** | Layer 2 — **pin an identity with no write permission** | Avoids a state where one policy line restores write access |

**"We created a read-only access point" does not hold on its own.** Restricting the access point policy's `Allow` to `s3:GetObject` still lets a principal with administrator permissions write through the same access point. To guarantee read-only, either **write an explicit deny** or **pin an identity that has no write permission.** The latter has to be decided **before the access point is created**, because `FileSystemIdentity` cannot be changed.

### Layer 2 Restriction Example

- Create a dedicated user with read permissions only on the target directories
- Avoid using root (UID 0) — it grants access to all files
- In NTFS environments, use a service account with minimal group membership

## Who Gets Recorded in the Audit Log

**Access through an S3 access point is recorded in the ONTAP file access audit, but the subject recorded is the identity pinned to the access point, not the calling IAM principal.** The separation of subjects between Layer 1 and Layer 2 is exactly what limits the audit.

| Question | Reality |
|---|---|
| The calling IAM principal | **Not available.** What remains is the SID of the pinned identity; `SubjectUserName` and `SubjectDomainName` are `Not Present` (unresolved). **Identifying the caller requires correlation with AWS CloudTrail** |
| **Does an AD-joined SVM resolve the name** | **No.** Even with a reachable DC and a **real domain account** pinned to the access point, both stayed `Not Present` (below) |
| Tracing the source through `SubjectIP` | **Not possible.** It is an AWS service-side address, and **six requests produced five distinct values** (two consecutive requests for the same object differed). **An audit requirement based on caller IP cannot be met over this path** |
| Does splitting authorization by group split the audit by subject | No. **Everything is recorded as the single identity bound to the access point** |
| Does enabling auditing on the SVM record every volume | **A volume with an effective UNIX style and mode bits only produced 0 records** (the same-session NTFS control produced 2). Mode bits carry no audit information; recording requires a SACL |
| Can `SubjectUserIsLocal` tell you whether the user is local | **`false` was recorded for a local user.** But `false` for a domain user is correct (below) |

### `SubjectUserName` is not resolved on an AD-joined SVM either

**Measured on an AD-joined SVM (`ms_dc` state `ok`) with a real domain account pinned to a WINDOWS-type access point.** An audit ACE was placed on an NTFS volume and `PutObject` / `GetObject` were issued through the access point.

| Field | Recorded value |
|---|---|
| `Source` | `HTTP` (most) / `S3` (one) |
| `EventID` | `4656` (Create Object) / `4663` (Read Object) |
| `SubjectUserSid` | A domain SID (`S-1-5-21-…-1112`) |
| `SubjectUserName` | **`Not Present`** |
| `SubjectDomainName` | **`Not Present`** |
| `SubjectUserIsLocal` | `false` — **correct**, the user is a domain user |
| `SubjectIP` | Five distinct AWS public addresses |
| `SubjectUnix Uid` / `Gid` | `65535` / `65535` |

**An AD join is not the condition for name resolution.** The `Not Present` observed with a workgroup-mode local user generalizes to AD-joined environments. The conclusion that **identifying the caller requires correlation with CloudTrail** is unchanged.

**`SubjectUserIsLocal` is not "always wrong".** `false` for a local user is wrong, but `false` for a domain user matches reality. **Do not use this field to decide whether a user is local** is the accurate statement.

> **Management operations do keep their subject.** In the same log, `EventID 4719` (audit policy change) alone carried the real administrative user name in `SubjectUserName` and the real client's private IP in `SubjectIP`. **It is data-operation auditing that loses the subject.**

> **Governance note**: **a design with one shared access point instead of one per purpose records every caller as the same subject in the file access audit, even when the access point policy distinguishes them.** Where per-subject tracking of file-level operations is a requirement, **splitting access points is what sets the audit granularity.** This is why the portal in this repository separates access points per team.

### A SLAG on a UNIX volume makes unix→win mapping mandatory

SLAG (storage-level access guard) is the route for attaching audit ACEs to a UNIX volume, but **access is denied as soon as one is applied.** Five states were measured (probe: NFSv3; the same denial was also observed over the S3 access point path).

| # | SLAG | CIFS server | DC reachable | unix→win mapping | Permissive ACE | Result |
|---|---|---|---|---|---|---|
| A | none | none | — | none | — | Succeeds |
| B | audit only | none | — | none | none | **Denied** |
| B' | audit only | present | **yes** | none | none | **Denied** |
| C | audit + allow | present | yes | none | `Everyone` / `full_control` | **Denied** |
| D | audit + allow | present | yes | **`root` → `<NetBIOS>\Admin`** | yes | **Restored** |

**The cause is the unix→win name mapping.** A SLAG is a Windows security descriptor, so evaluating it requires a Windows credential for the accessing UNIX identity. When that mapping fails, **the request is denied regardless of what the SLAG's ACEs say.** ONTAP names the reason in EMS `secd.nfsAuth.noNameMap` — `Successfully authenticated with DC` immediately followed by `Could not find Windows name 'root'` and `No default Windows user defined`.

Three consequences for design:

- **It is not specific to the S3 access point. NFS is denied at the same time.** The whole volume stops
- **DC reachability alone is not enough** (B'). A matching Windows account has to exist
- **Adding a permissive ACE does not resolve it** (C). "The DACL is empty" does not explain it

**Providing the mapping restores access with the SLAG left in place** (D). That introduces its own cost, though: maintaining the mapping across SVMs, and carrying an identity correspondence in the design. **Where file-level auditing is a requirement, deciding the volume security style at design time is simpler.**

> **Scope**: the restoration (D) was **confirmed over NFS.** The denial was observed over both the S3 access point and NFS, but restoration over the S3 access point path was not measured — the SVM used as the control runs a native ONTAP S3 server, which [blocks access point creation](#by-product-a-native-ontap-s3-server-blocks-access-point-creation).

## Application in This Project

The patterns in this repository adopt the following design:

| Component | Layer 1 Design | Layer 2 Design |
|-----------|---------------|---------------|
| Discovery Lambda | The dedicated role's identity-based policy limited to ListBucket + GetObject | UNIX user with read permissions on target volumes |
| Processing Lambda | Likewise GetObject only (input reading) | Same as above |
| Output Lambda (FSXN_S3AP mode) | PutObject added | User with write permissions on the output directory |

**The Layer 1 column describes the permissions given to that role.** Because each Lambda has a dedicated role, that role's path is constrained. **It does not constrain the access point itself.** To stop other principals, write an explicit deny.

## Troubleshooting

**Identify the failing layer first.** The same `AccessDenied` comes from both layers, so investigating without fixing the layer means searching where the cause is not.

| Signal | Failing layer | What to look at first |
|---|---|---|
| The error body contains `with an explicit deny in a resource-based policy` | Layer 1 (explicit deny) | The `Deny` statement in the access point policy and its `Condition` |
| A principal you thought you excluded gets through | Layer 1 (combination) | **That only `Allow` is written.** Add an explicit deny |
| `AccessDenied` from another account | Layer 1 (cross-account) | The access point policy **and the other side's identity-based policy** |
| Everyone inside the organization gets `AccessDenied` | Layer 1 (RCP / SCP) | RCP / SCP. Fixing the access point policy changes nothing |
| `HeadBucket` succeeds but data operations fail | **Layer 2** | File permissions of the pinned identity. On an AD-joined SVM, domain controller reachability |
| IAM allows it but it still fails | **Layer 2** | Same as above |

| Symptom | Possible Cause | Verification Point |
|---------|---------------|-------------------|
| AccessDenied despite IAM permission | Insufficient file system ID permissions | Check UNIX/Windows ID file/directory permissions associated with the S3 AP |
| ListBucket succeeds but GetObject returns AccessDenied | File ACL / export policy / security style mismatch | Check effective permissions with `ls -la` (UNIX) or `icacls` (NTFS) |
| PutObject fails | Insufficient directory write permissions | Check write permissions on the parent directory. If the file system ID is read-only, writes are not possible |
| `AccessDenied` on ListObjectsV2 / GetObject | The IAM policy Resource ARN is in bucket form | Confirm the `arn:aws:s3:{region}:{account}:accesspoint/{name}` format |
| Timeout from VPC Lambda | Accessing Internet Origin AP via S3 Gateway EP | Place Lambda outside VPC, or route via NAT Gateway |
| MISCONFIGURED state | File system ID unresolvable, or the volume is offline / unmounted | Check that the ID resolves on the SVM, and check the volume's junction path |
| AccessDenied on specific directories only | ONTAP export policy restrictions | Check SVM export policy rules (NFS export and S3 AP are different paths but share the same volume permissions) |
| `Policy has invalid action` on put-access-point-policy | An action the access point policy does not accept ([list](#actions-that-cannot-be-used-in-an-access-point-policy)). **The message does not name which one** | Apply them one at a time to isolate it. Move bucket-configuration and access-point-management actions to the identity-based policy |
| A policy change does not take effect | Propagation takes seconds | Six seconds after applying, the previous decision was still returned; it settled after 10–12 seconds. **Looking only at the first attempt leads to the wrong conclusion** |

### Verification Command Examples

> **Note**: All commands below are read-only for troubleshooting purposes. They do not make any changes to the environment.

```bash
# === AWS CLI ===

# 1. Check the S3 AP resource policy
#    NoSuchAccessPointPolicy is returned when there is none - which is a valid state
aws s3control get-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME>

# 2. Verify permissions with IAM Policy Simulator
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE> \
  --action-names s3:GetObject s3:ListBucket \
  --resource-arns "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"

# 3. Check AccessDenied events in CloudTrail (this is where the caller is identified)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)]'

# 4. Check the filesystem identity pinned to the S3 AP
aws fsx describe-s3-access-point-attachments \
  --query 'S3AccessPointAttachments[*].{Name:Name,Identity:OntapConfiguration.FileSystemIdentity}'

# === ONTAP CLI ===

# 5. ONTAP side: check ACL / permissions on the target path (UNIX)
# Via SSH or ONTAP CLI
vserver security file-directory show -vserver <SVM_NAME> -path <PATH>

# 6. ONTAP side: check that the pinned identity resolves
vserver services access-check authentication show-creds \
  -vserver <SVM_NAME> -unix-user-name <USER> -show-partial-unix-creds true

# 7. ONTAP side: check for a native S3 service (its presence blocks AP creation)
#    REST: GET /api/protocols/s3/services?svm.name=<SVM_NAME>
vserver object-store-server show -vserver <SVM_NAME>

# === VPC / Network ===

# 8. Check VPC Endpoint policy
aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.<REGION>.s3 \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,Policy:PolicyDocument}'
```

## Common Misconceptions

| Misconception | Reality |
|---|---|
| You set a bucket policy on an FSx for ONTAP S3 AP | There is no bucket underneath, so you cannot. It is an access point policy |
| Only what the AP policy's `Allow` lists gets through | Same-account requests are evaluated as a combination. Narrowing needs an explicit deny |
| An operation absent from `Allow`'s `Action` is impossible | It is possible. `Action` is also decided by the combination |
| Without an AP policy nobody can access it | They can, if the caller's identity-based policy allows it |
| Same-account ownership is required, so another account cannot read | **It can.** The constraint is on creating the access point |
| You can build exceptions with `NotPrincipal` | The account ARN must be listed too, and roles also need the session ARN. Unusable where the session name cannot be fixed |
| `aws:SecureTransport` is blocking plaintext | That branch is never reached. HTTP is redirected before authorization is evaluated |
| If the local JSON is under 20 KB it will be accepted | The check is post-normalization. **24,861 bytes was rejected in measurement** |
| You can swap the AP's file system identity later | There is no update API. It becomes a recreation, and **the alias changes** |
| With no `s3:` action in the AP policy, files are unreachable | They are reachable. **The two layers are independent** |
| UNIX identities need LDAP and Windows identities need an AD join | Neither is required. Measured with a local UNIX user and with a workgroup-mode local Windows user |
| The audit log tells you the calling IAM principal | It does not. Only the SID of the pinned identity remains. **Correlation with CloudTrail is required** |
| `SubjectIP` in the audit log traces the caller | It does not. It is an AWS service-side address; six requests produced five distinct values |
| Enabling auditing on the SVM records every volume | A UNIX-style volume with mode bits only produced **0 records**. An audit ACE is required |
| An AD-joined SVM puts the subject's name in the audit log | It does not. **Even a real domain account stays `Not Present`** |
| Adding a SLAG to a UNIX volume lets you audit it | Access is denied. **It makes unix→win mapping mandatory** |
| Layer 1 evaluation changes with the volume's security style | It does not. UNIX and NTFS produced the same results |
| An access point can be created on an SVM running native ONTAP S3 | It cannot. Creation ends in `FAILED` |

## By-product: a native ONTAP S3 server blocks access point creation

**If an SVM runs a native ONTAP S3 service, you cannot create an S3 access point on that SVM's volumes.** The access point reaches `FAILED` and states the reason:

```
Amazon FSx is unable to create an S3 access point because of an existing
ONTAP object storage server on SVM svm-0123456789abcdef0
```

ONTAP S3 buckets surface as FlexGroup volumes named `fg_oss_*`, so **check the target SVM for those and for `/protocols/s3/services` before creating an access point.** The workaround is a different SVM.

## Limits of This Description

- **The lockout from writing `s3:*` in a `Deny` was not measured.** Recovery may require recreating the access point, so it was deliberately not attempted.
- **Restoration after removing the SLAG condition was confirmed over NFS.** Restoration over the S3 access point path was not measured (reason in that section).
- **The cross-account measurement was one run between one pair of accounts.**
- **The audit measurement on an AD-joined SVM used one domain account** (the directory's administrative account). Ordinary domain users were not measured.
- The audit measurement used one configuration: `file_operations` events, XML format. Other event types and log formats populate different fields.
- Measurements come from one Region (`ap-northeast-1`), ONTAP `9.18.1P3D1`, and one file system.

## References

- [S3 Access Point permission design — evaluation order and the two layers that narrow access](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/domains/security-governance/notes/access-point-authorization-layers.md) — **the source of the measurements here, with six policy examples and the full results**
- [How a request through an S3 access point is evaluated](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/decision-trees/access-point-authorization.md) — evaluation order, and working back from a symptom to the failing step
- [AD-joined SVM S3 AP prerequisites](en/ad-joined-svm-s3ap-prerequisites.md) — AD DC reachability, and why `HeadBucket` is a false positive
- [Cross-account S3 AP](multi-account/cross-account-s3ap.md) — cross-account access design patterns
- [Managing access point access — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [Troubleshooting access points — Amazon FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html)
- [AWS: How AWS enforcement code logic evaluates requests](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-denyallow.html)
- [AWS: Policy evaluation for requests within a single account](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-basics.html)
- [Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
