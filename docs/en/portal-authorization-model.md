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
7. **No automatic expiry**: a block stays until someone removes it. The portal has no TTL and no scheduled unblock, so the Active Blocks tab is the only thing standing between a false positive and an indefinite lockout. See the [containment boundary](../../solutions/amplify-portal/docs/resource-management-demo-guide.en.md) for what this means operationally.

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
