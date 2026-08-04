# Portal Authorization Model

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

## Feature-Level Authorization Matrix

### Browse Section (All authenticated users)

| Feature | Auth Level | AppSync Operation |
|---------|-----------|-------------------|
| File listing | authenticated | `listFiles` query |
| File download (Presigned URL) | authenticated | `getPresignedUrl` query |
| File upload (Storage Browser) | authenticated | Cognito Identity Pool S3 policy |
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
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) — Generic Dispatch authorization schema
- [Compliance Guide](./portal-compliance-guide.md) — Auditor procedures for verifying access controls
