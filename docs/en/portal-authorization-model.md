# Portal Authorization Model

🌐 **Language / 言語**: [日本語](../ja/portal-authorization-model.md) | English

> How Cognito groups control access to portal features. All operations are enforced at the AppSync authorization layer — the frontend renders UI based on group membership, but the backend rejects unauthorized calls regardless of UI state.

## Overview

The portal uses **Amazon Cognito User Pool Groups** to implement role-based access control. AppSync schema-level authorization (`allow.groups(["storage-admin"])`) ensures that only designated administrators can execute write operations on ONTAP infrastructure.

| | Authenticated (all users) | storage-admin group |
|---|---|---|
| **Role** | All signed-in users | Storage administrators |
| **Access** | Read + AI processing | Full read + write + ONTAP config |
| **CAN** | Browse/download/upload files | All left-column operations PLUS: |
| | View Snapshots, ARP/AI status | Volume create/resize/delete |
| | Start AI processing jobs | Quota rule management |
| | Athena SQL, Bedrock Q&A | Export Policy/SMB share CRUD |
| | Rekognition, Quick MCP | QoS policy management |
| | Presigned URL generation | SnapLock retention config |
| | Recent files, Favorites, Tags | Qtree management |
| | FlexClone restore | ARP/AI state changes + bulk enable |
| | View protection summary | Snapshot create/delete/lock |
| | | Tamperproof snapshot config |
| | | Threat containment (block/unblock) |
| | | CIFS share management |
| | | Storage efficiency viewing |
| **CANNOT** | Modify ONTAP config | |
| | Block/unblock users | |
| | Change ARP state | |
| | Delete volumes | |
| | Manage quotas/policies | |
| **Enforcement** | AppSync: `allow.authenticated()` | AppSync: `allow.groups(["storage-admin"])` |

## Two Axes: Role and Scope

The table above describes the state with `enforceRoles` set to **`false`**. The default is
**`true`**, so the write dispatchers `fileMutation` and `folderMutation` require
`contributor` or above. This section covers the two axes.

**A user holding no role can read, preview, download and search, and cannot write.** That
is the intended state, and it is the state five administrative endpoints have always been
in -- they require `storage-admin` regardless of this setting -- so the portal has never
been fully usable until somebody granted a group. The order for a new deployment is under
"The first user" below.

The groups are split along two axes because **they are enforced in different places**. A
single combined axis would have to be enforced in both.

| Axis | Decides | Enforced at |
|---|---|---|
| **role** | Which operations a caller may invoke | AppSync authorization (`allow.groups`) |
| **scope** | Which data a caller reaches | S3 Access Point + path boundary (Lambda) |

A caller holds one role and one scope. The six product groups are not created because
`cognito:groups` is an array, so holding one of each is the natural encoding.

### Roles (four)

| Role | Capability |
|---|---|
| `viewer` | Read and download only |
| `contributor` | Adds writes: upload, rename, move, trash, folder creation |
| `storage-admin` | Adds ONTAP configuration and the analytics console (pre-existing; the name is unchanged) |
| `auditor` | Reads the audit trail |

`auditor` is **orthogonal** to the read/write ladder rather than a rung above `viewer`. It
exists so somebody can see who did what without being able to change it. That is why
`queryAuditLog` names `auditor` and `storage-admin` and does not name `viewer`.

### Scopes (two)

| Scope | Meaning |
|---|---|
| `internal` | Inside the organisation; holds a Windows or UNIX account on the file system |
| `external` | Outside the organisation; no ONTAP identity, identified only by an email address |

### Where `external` takes effect

| Target | Behaviour | How to change |
|---|---|---|
| Path boundary | Confined to `groupPathPrefixes`; the `storage-admin` bypass no longer applies | `groupPathPrefixes` |
| The six AI endpoints | Denied by default (file content reaches a model, and calls are billed per token) | `externalDefaults.aiEnabled` |
| Share links | Allowed per role; every role denied by default | `externalDefaults.shareLinksByRole` |

**The `storage-admin` bypass is revoked by the *absence* of `external`**, not by the
presence of `internal`. Every administrator in a deployed pool predates the scope axis and
holds neither scope, so requiring `internal` would confine all of them the moment it
shipped — a change that arrives as an outage. The condition falls on the default side.

### Share links are capped, not refused

One AppSync query, `getPresignedUrl`, backs the preview, the download button and the share
dialog. The request does not distinguish them: the share dialog's shortest TTL of 300
seconds is the preview's value. A `purpose` flag would not help either, since the caller
chooses what to send.

So the **lifetime** is capped instead. An external caller whose role does not allow share
links keeps preview (300s) and download (60s), and any longer TTL is clamped to 300
seconds.

> **Security note**: this **shortens the exposure window**; it does not prevent
> forwarding. A presigned URL is redeemable by anyone holding it, without AWS
> credentials, until it expires. What changes is for how long.

Endpoints that exist **only** to hand a link to somebody else are refused rather than
capped: the QR code (`generateQrCode`) and the upload link for an unauthenticated party
(`createUploadLink`, a write credential valid for up to 24 hours). There is no in-session
use to preserve by clamping them.

### The Upload tab does not go through AppSync

**This is the one place AppSync does not decide.** The Upload tab
(`@aws-amplify/ui-react-storage`) calls S3 from the browser with the identity pool's
credentials, so neither `enforceRoles` nor the path prefixes apply — both are enforced in
the Lambda handlers. **Whatever the selected IAM role grants is the whole of what that tab
can do.**

Amplify Gen2 creates an IAM role for every group declared in `defineAuth`, sets it as the
group's `RoleArn`, and attaches the identity pool with `Type: Token`. Cognito then returns
`cognito:preferred_role`: **the role of the member group with the lowest precedence value**
([CreateGroup: Precedence](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_CreateGroup.html)).

Measured on a deployed pool (2026-08-27, ap-northeast-1):

| Account | Role assumed | S3 result |
|---|---|---|
| `contributor` + `external` | the contributor **group** role | `AccessDenied` on ListBucket |
| in no group | the authenticated role | PutObject **succeeded** into a prefix no prefix setting grants |

So before this: **an account that had been given a role could not use the Upload tab, and
only an account with no role could write — anywhere.** Neither was the intent.

The grant now sits on the group roles, with precedence stated explicitly:

| Group | Precedence | Direct S3 |
|---|---|---|
| `external` | 0 | **none** |
| `storage-admin` | 1 | read + write |
| `contributor` | 2 | read + write |
| `viewer` | 3 | read only |
| `auditor` | 4 | read only |
| `internal` | 5 | read only |
| (no group) | — | read only, via the authenticated role |

**Putting `external` first is the load-bearing choice.** Exactly one role is selected, so a
single ordering can honour only one of the two axes, and for an external member the scope
has to win: their reach is defined by path prefixes, and **a policy on a role shared by
every external member cannot express them** (there is no `cognito:groups` condition key for
identity pool sessions). Granting that role nothing closes the direct path and leaves the
AppSync path, where the prefixes are enforced, as the only way in. `internal` is last for
the mirror-image reason: if it out-ranked a role, every internal member would be selected
onto the same role and the role axis would stop deciding anything.

Precedence cannot be left to Amplify's default — the index in `ALL_PORTAL_GROUPS` — because
that order puts `viewer` ahead of `contributor`. An account holding both would fall to
read-only, the opposite of the AppSync rule, where **holding several roles grants the most
permissive**.

> **Security note**: if two groups share a precedence, `cognito:preferred_role` is **not
> set**, and the identity pool falls back to `AmbiguousRoleResolution` — the authenticated
> role. Every member of both groups would silently get the read-only default instead of
> their own grant. `directS3Problems()` stops this at synth.

The way for an external member to send you a file is the **upload link**
(`createUploadLink`), not the Upload tab. That one goes through AppSync, so the prefixes
apply.

### How accounts are created, and MFA

Both were fixed values before. **A fixed value reads as a decision somebody made for this
deployment, when in fact it was a default nobody chose.**

| Setting | Default | Meaning |
|---|---|---|
| `signIn.selfSignUpEnabled` | `false` | Accounts are created by an administrator; `admin-create-user` is the only way in |
| `signIn.mfa` | `"OPTIONAL"` | Each user decides whether to use MFA |

These two were `true` and `false`, which together meant **anyone who could reach the
sign-in page could register, and a registered user could upload and delete**. That was for
backward compatibility, and nobody had forked this repository -- so there was no
compatibility to keep. Both defaults are now the restrictive ones.

> **Security note**: the environment variables only lift a restriction when the word that
> lifts it is spelled correctly (`AMPLIFY_PORTAL_SELF_SIGN_UP=true`,
> `AMPLIFY_PORTAL_ENFORCE_ROLES=false`). Previously a typo such as `ENFORCE_ROLES=treu`
> read as "not true" and **silently removed the authorization rules**. The polarity was
> reversed so that a misspelling lands on the restrictive side.

`"OPTIONAL"` needs reading precisely. It means **each user decides**, so it is `"OFF"` for
everyone who does not go looking for it. Use `"REQUIRED"` when MFA has to be true of every
session.

Self sign-up is off by default, so an invitation is already the only way in. Raise MFA as
well if it has to hold for every session — the default, `"OPTIONAL"`, leaves it to each user.

```ts
// portal-config.ts — selfSignUpEnabled is the default here; only MFA differs from it
signIn: {
  selfSignUpEnabled: false,
  mfa: "REQUIRED",
},
```

```bash
# Create the account by invitation
aws cognito-idp admin-create-user --user-pool-id <pool> \
  --username partner@example.net \
  --user-attributes Name=email,Value=partner@example.net Name=email_verified,Value=true
```

An invitation then becomes the only way in, which also changes what the audit trail is
worth: **every account traces back to whoever issued it.**

> **Implementation note**: `defineAuth` has no field for self sign-up, and
> `@aws-amplify/auth-construct` defaults `ALLOW_SELF_SIGN_UP` to `true`. So `backend.ts`
> overrides the L1 property `AdminCreateUserConfig.AllowAdminCreateUserOnly` with
> `addPropertyOverride`. It does not assign the object wholesale, because the construct
> may set an invitation message template in the same object and replacing it would drop
> that with no error.

### The first user, and everybody after

`enforceRoles` is on by default, so **granting a role is the first thing to do after
deploying**. Self sign-up is closed by default too, which means the person creating the
account and the person granting the role are the same operator.

```bash
# 1. Create your account (self sign-up is closed)
aws cognito-idp admin-create-user --user-pool-id <pool> \
  --username you@example.com \
  --user-attributes Name=email,Value=you@example.com Name=email_verified,Value=true

# 2. Grant a role and a scope (idempotent; dry run unless --apply)
make portal-grant-roles ARGS='--apply --assign you@example.com=storage-admin,internal'

# 3. Sign in
```

The order is the same for everybody after. **A user who is already signed in has to sign
out and in again**: groups travel in the ID token, so a token issued before the grant does
not carry it. Nearly every report of "I granted the role and nothing changed" is this.

`make portal-grant-roles` reports three outcomes per assignment: granted, already held,
refused.

`make portal-grant-roles` reports three outcomes per assignment: granted, already held,
refused. Refusals cover naming two roles, naming both scopes, naming no scope, and a group
the pool does not yet have. **It does not create groups** — a group outside `defineAuth`'s
ownership would remain, and the next deployment's drift check would find it with no record
of why it exists.

### Settings that are present but inert fail at synth

A prefix in `groupPathPrefixes` with no trailing `/` (`teams/a` also matches `teams/ab/`);
a `shareLinksByRole` key that is not a role (`{"external": true}` reads as "external users
may share" but is matched against roles, so it grants nobody); a blank alias in
`groupApMapping`; an empty prefix list (reads as "restricted to nothing" and means
"unrestricted"). Each deploys successfully and raises no runtime error. `backend.ts` stops
them at synth.

## Two audit sources

The audit tab reads two sources, as **separate sections**. Neither substitutes for the
other.

| Source | Records | Who acted | What an empty result means |
|---|---|---|---|
| CloudTrail (S3 data events) | Everything that reached S3 | **Not available** — the caller is the access point's IAM role, the same principal for every portal user | No object access in that period |
| Portal activity | Requests to the portal | The Cognito user | **No portal action** — access that did not go through the portal is not here |

They are not merged into one table because the `user` column would mean something
different from one row to the next.

### What the portal activity ledger records

| action | Written when |
|---|---|
| `SHARE_LINK` | `getPresignedUrl` mints a URL. The preview, the download button and the share dialog all use that one query, so they **cannot be told apart** |
| `DOWNLOAD` | A folder was retrieved as a ZIP. The files were read at that point whether or not anybody follows the URL |
| `UPLOAD_LINK` | `createUploadLink` mints an upload URL |
| `DELETE` | Moved to trash (`reversible: true`) and deleted permanently (`reversible: false`) |

Each row also records the **groups held at the time**. Membership changes, so a row naming
only the user cannot later show what they held when they acted.

Rows are kept for 90 days (`ttl`). The table is marked `RETAIN` in code, but **that has no effect in a sandbox** (measured 2026-08-27: a sandbox overrides removal policies to `Delete`). Whether a branch deployment honours it is unverified.

> **What this used to be**: the ledger took its table name from the `URL_AUDIT_TABLE_NAME`
> environment variable, which **defaulted to an empty string**. The handler skips the write
> when the name is empty, so **on every deployment that did not set that variable by hand,
> the ledger did not exist and nothing said so.** The stack now creates the table, and the
> IAM grant was narrowed from `*` to that table's ARN.

> **On retention**: the previous inline writer deleted each row **a day after the URL
> expired**, so the record of who was given access disappeared a few days after the access
> did. A record shorter-lived than its subject cannot answer a question asked later — and
> audit questions are asked later.

### Authorization

`queryAuditLog` is limited to `auditor` and `storage-admin`. `enforceRoles` is on by
default; setting it to false opens the audit trail to every signed-in user as well.
`viewer` is deliberately absent: being able to read files does not imply being able to read
**everybody else's activity**. The read grant is `dynamodb:Scan` only, with no write
permission — the audit path must not be able to amend the record it reports.

## Feature-Level Authorization Matrix

### Browse Section (All authenticated users)

| Feature | Auth Level | AppSync Operation |
|---------|-----------|-------------------|
| File listing | authenticated | `listFiles` query |
| File download (Presigned URL) | authenticated | `getPresignedUrl` query |
| File upload (Storage Browser) | `contributor` / `storage-admin`, and not `external` | IAM policy on the group role ([not AppSync](#the-upload-tab-does-not-go-through-appsync)) |
| Image/PDF/DOCX preview | authenticated | `getPresignedUrl` query |
| Sharing link generation | authenticated | `getPresignedUrl` mutation |
| Recent files | authenticated (owner-scoped) | `RecentFile` model (owner auth) |
| Favorites | authenticated (owner-scoped) | `Favorite` model (owner auth) |
| File tags | authenticated (owner-scoped) | `FileTag` model (owner auth) |

### AI & Processing Section (All authenticated users)

| Feature | Auth Level | AppSync Operation |
|---------|-----------|-------------------|
| Start processing job | authenticated | `startProcessing` mutation |
| View job status | authenticated | `getJobStatus` query |
| Job execution history | authenticated (owner-scoped) | `JobExecution` model |
| Bedrock Q&A | authenticated | `askBedrock` mutation |
| Rekognition analysis | authenticated | `detectObjects` mutation |
| Athena SQL query | authenticated | `runAthenaQuery` mutation |
| FlexClone restore | authenticated | `startProcessing` (FC7 pattern) |

### Data Protection Section (Mixed)

| Feature | Auth Level | AppSync Operation |
|---------|-----------|-------------------|
| View Snapshot list | authenticated | `getSnapshotsWithLockStatus` query |
| View ARP/AI status | authenticated | `getArpStatus` query |
| View SnapLock status | authenticated | `getSnaplockStatus` query |
| View protection summary | authenticated | `getProtectionSummary` query |
| **Block SMB user** | **storage-admin** | `blockSmbUser` mutation |
| **Block NFS IP** | **storage-admin** | `blockNfsIp` mutation |
| **Contain threat** | **storage-admin** | `containThreat` mutation |
| **Unblock user/IP** | **storage-admin** | `unblockSmbUser`/`unblockNfsIp` |
| **Disconnect sessions** | **storage-admin** | `disconnectSessions` mutation |
| View active blocks | authenticated | `listActiveBlocks` query |

### Admin Section (storage-admin only)

| Feature | Auth Level | AppSync Operation |
|---------|-----------|-------------------|
| **Resource Management** | | |
| Volume CRUD | storage-admin | `listVolumes`/`createVolume`/`resizeVolume`/`deleteVolume` |
| Quota management | storage-admin | `listQuotaRules`/`createQuotaRule`/`deleteQuotaRule`/`getQuotaReport` |
| Export Policy rules | storage-admin | `listExportPolicies`/`createExportPolicyRule`/`deleteExportPolicyRule` |
| CIFS/SMB shares | storage-admin | `listCifsShares`/`createCifsShare`/`deleteCifsShare` |
| Qtree management | storage-admin | `listQtrees`/`createQtree`/`deleteQtree` |
| QoS policies | storage-admin | `listQosPolicies`/`createQosPolicy`/`deleteQosPolicy`/`assignQosToVolume` |
| SnapLock config | storage-admin | `getSnaplockConfigAdmin`/`updateSnaplockRetention` |
| Storage efficiency | storage-admin | `getEfficiencyStats` |
| **ARP/AI Management** | | |
| List all volumes' ARP state | storage-admin | `listArpVolumes` |
| Change ARP state | storage-admin | `updateArpStateAdmin` |
| Bulk enable ARP | storage-admin | `enableArpBulk` |
| View/clear suspects | storage-admin | `getArpSuspectsAdmin`/`clearArpSuspects` |
| Tune surge parameters | storage-admin | `updateArpSurgeParams` |
| **Snapshot Management** | | |
| Create snapshot | storage-admin | `createSnapshot` |
| Delete snapshot | storage-admin | `deleteSnapshot` |
| Lock snapshot (tamperproof) | storage-admin | `lockSnapshot` |
| Update ARP state | storage-admin | `updateArpState` |
| Update retention policy | storage-admin | `updateRetentionPolicy` |
| Snapshot policy management | storage-admin | `listSnapshotPolicies`/`createSnapshotPolicy` |
| Enable tamperproof locking | storage-admin | `enableSnapshotLocking` |

## How to Add a User to storage-admin

```bash
# Via AWS CLI
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <user-pool-id> \
  --username <user-email> \
  --group-name storage-admin

# Via AWS Console
# Cognito → User Pools → <pool> → Groups → storage-admin → Add users
```

## How to Create the storage-admin Group

The group is auto-created by the Amplify backend (defined in `amplify/auth/resource.ts`). If manually creating:

```bash
aws cognito-idp create-group \
  --user-pool-id <user-pool-id> \
  --group-name storage-admin \
  --description "Storage administrators with ONTAP management access"
```

## Security Design Principles

1. **Defense in depth**: AppSync rejects unauthorized calls even if frontend UI is bypassed
2. **Least privilege**: Read operations are broadly available; write operations require explicit group membership
3. **Owner scoping**: Personal data (favorites, history, tags) uses Amplify's `allow.owner()` — users see only their own
4. **Audit trail**: All admin actions include `userId` in the Lambda payload → logged in CloudTrail
5. **Protected accounts**: Even storage-admins cannot block `fsxadmin`/`administrator` (safety valve in `ontap_response.py`)
6. **Confirmation gates**: Destructive operations require explicit `confirm: true` in the Lambda payload, not only a dialog in the browser. This covers `deleteVolume`, `deleteExportPolicy`, `deleteCifsShare`, the SnapMirror `break`/`resync`/`delete` paths, the Vscan and FPolicy policy deletes, cluster-peer delete, and every ARP containment action (`blockSmbUser`, `blockNfsIp`, `containThreat`, `disconnectSessions`). Unblocking is deliberately **not** gated — it restores access, and a confirmation step on the way out of a mistaken block only delays recovery.
7. **Input is validated for both SQL and request paths**: the values that reach the audit-log Athena query (`fileKeyPrefix`, `startDate`, `endDate`, `eventType`, `maxResults`) are pattern-checked and then rendered as literals with single quotes doubled. LIKE metacharacters (`%`, `_`) are escaped as well, so a prefix is not interpreted as a wildcard. ONTAP request paths percent-encode caller-supplied names, and `_ontap_request` refuses any path containing a `..` segment or a control character. That check lives in the one function all 110-plus actions pass through rather than in each action.
8. **Expiry and the sweep**: a block carries an expiry, 24 hours by default, and a scheduled sweep lifts blocks whose expiry has passed. The operator can choose 1 hour to 7 days, or indefinite, at the point of blocking. Over the API the ceiling is 30 days by default (`maxBlockTtlHours`; 0 removes it), which is a point where the instrument should change rather than a number that is safe — a deny rule covers one SVM, so a principal that must stay locked out for longer should be disabled in the directory instead. Exceeding the ceiling is refused, never clamped. ONTAP name-mapping and export-policy rules carry no timestamp, so expiry is tracked in a portal-side ledger (DynamoDB) and the sweep only considers rows in that ledger — a block placed outside the portal is reported as "Not portal-managed" and never lifted automatically. See the [containment boundary](../../solutions/amplify-portal/docs/resource-management-demo-guide.en.md) for what this means operationally.

## What Happens When the Lambda Is Invoked Directly

The audit subject (`createdBy` / `createdVia`) is decided by whether the call arrived through AppSync. The `arp-dispatch.js` resolver injects `userId` from the Cognito identity along with `invokedVia: "appsync"`, and the Lambda attributes the action to a user only when both are present. Anything else is recorded as `unattributed` / `direct-invoke`.

**A principal holding `lambda:InvokeFunction` can supply both fields itself and be attributed as whoever it names.** There is no way to tell from inside the function.

### Why the stack cannot prevent this

Within a single account, a call succeeds if **either** an identity-based policy **or** a resource-based policy allows it. And the Lambda permission API (`AddPermission`) can only write Allow statements. So adding a resource policy to this stack cannot take `lambda:InvokeFunction` away from a principal that already has it — it can only hand it to more principals.

The two layers that do prevent it are both outside this stack:

1. **Identity-based policies** — who is granted `lambda:InvokeFunction` in the first place
2. **An SCP or permissions boundary** — an organization-level rule forbidding invocation from anywhere but the intended paths

### Example SCP

Denies invocation of the portal's ARP function by anything other than the AppSync data-source role and the containment sweep's EventBridge rule. Replace the `aws:PrincipalArn` values with the ones from your own deployment.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDirectInvokeOfPortalContainment",
      "Effect": "Deny",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:<region>:<account-id>:function:*ArpResponseFunction*",
      "Condition": {
        "ArnNotLike": {
          "aws:PrincipalArn": [
            "arn:aws:iam::<account-id>:role/*AppSync*DataSource*",
            "arn:aws:iam::<account-id>:role/*ContainmentBlockSweep*"
          ]
        }
      }
    }
  ]
}
```

> **Operational note**: applying this also stops the live-verification probes in `scripts/portal-probes/` from working. Where you use the probes, add the role they run as to the `ArnNotLike` exclusion list.

### What the stack does instead

Since it cannot prevent this, it makes sure it **cannot happen quietly**. When a state-changing containment action arrives without an AppSync identity, the function emits the EMF metric `UnattributedContainmentActions`, and a CloudWatch alarm (`<stack>-containment-unattributed-action`) fires on the first occurrence. The point is to notice while the containment is still in force.

The ledger row already recorded `direct-invoke`, but only somebody reading that row afterwards would ever have seen it.

Running `scripts/portal-probes/` trips this alarm on purpose. The probes really do change state from outside the portal, so exempting them would leave a hole shaped exactly like the thing being watched for.

## Frontend Behavior

The UI does not hide admin features from non-admin users — instead, it shows them grayed out with a "storage-admin required" badge. This makes the capability visible (users know what's possible) while preventing unauthorized execution (AppSync rejects the call if attempted).

The `ArpResponseActions` component in Data Protection always renders its containment form — an operator may need to block a user that ARP has not flagged. What changes with the threat level is a warning banner above the form, not the availability of the actions. Each action then asks for confirmation, and the Lambda refuses the call unless `confirm: true` arrives with it.


---

## Related Documents

- [PoC → Production Guide](./portal-poc-to-production.md) — Authentication setup (MFA, groups, SAML federation) for production
- [Scaling Guide](./portal-scaling-guide.md) — How auth scales (Cognito 1M users, rate limits)
- [Accessibility Statement](./portal-accessibility.md) — How ARIA roles interact with authorization states
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.en.md) — Generic Dispatch authorization schema
- [Compliance Guide](./portal-compliance-guide.md) — Auditor procedures for verifying access controls
- [Identity Verification Results](./portal-identity-verification-results.md) — Measured Layer 2 strength, the identity a presigned URL executes as, and the permissions created through an S3 Access Point
