# Portal Authorization Design — Role-Based Access Control

> 🌐 Language: **English** | [日本語](../ja/portal-authorization-design.md)

This document defines the authorization model for the FSx for ONTAP File Portal, covering how user roles map to portal capabilities across file operations, AI processing, and data protection management.

---

## Design Principles

1. **Least privilege by default**: New users get Viewer access. Admin capabilities require explicit group membership.
2. **Separation of data access and infrastructure management**: File browsing (S3 AP) is separate from storage administration (ONTAP REST API).
3. **Defense in depth**: Authorization is enforced at 3 layers — Cognito group, AppSync resolver, and backend Lambda IAM.
4. **Auditable**: All admin operations are logged (CloudTrail + DynamoDB audit).

---

## Role Definitions

| Role | Cognito Group | Capabilities | Use Case |
|------|--------------|-------------|----------|
| **Viewer** | (default — no group) | Browse files, preview, download, AI Q&A, search | End users, analysts |
| **Contributor** | `contributor` | Viewer + upload, tag, favorite, comment | Team members, content creators |
| **Storage Admin** | `storage-admin` | Contributor + snapshot management, lock configuration, ARP control | Storage engineers, platform team |
| **Audit** | `auditor` | Viewer + audit trail access, compliance reports | Compliance officers, security team |

---

## Authorization Matrix

### Browse & File Operations

| Operation | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| List/browse files | ✅ | ✅ | ✅ | ✅ |
| Preview file (Presigned URL) | ✅ | ✅ | ✅ | ✅ |
| Download file | ✅ | ✅ | ✅ | ✅ |
| Generate share link | ✅ | ✅ | ✅ | ❌ |
| Upload file | ❌ | ✅ | ✅ | ❌ |
| Delete file (move to trash) | ❌ | ✅ | ✅ | ❌ |
| Rename file | ❌ | ✅ | ✅ | ❌ |
| Restore from trash | ❌ | ✅ | ✅ | ❌ |

### AI & Processing

| Operation | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| AI Q&A (Bedrock) | ✅ | ✅ | ✅ | ❌ |
| Semantic search | ✅ | ✅ | ✅ | ✅ |
| Trigger processing job | ❌ | ✅ | ✅ | ❌ |
| View job results/history | ✅ | ✅ | ✅ | ✅ |
| Analytics (Athena SQL) | ❌ | ✅ | ✅ | ✅ |

### Data Protection (Read)

| Operation | Viewer | Contributor | Storage Admin | Auditor |
|-----------|:---:|:---:|:---:|:---:|
| View snapshot list | ✅ | ✅ | ✅ | ✅ |
| View ARP/AI status | ❌ | ❌ | ✅ | ✅ |
| View SnapLock config | ❌ | ❌ | ✅ | ✅ |
| View S3 Object Lock status | ❌ | ❌ | ✅ | ✅ |
| View audit trail | ❌ | ❌ | ✅ | ✅ |

### Data Protection (Write) — Storage Admin Only

| Operation | API | Backend |
|-----------|-----|---------|
| Create manual snapshot | ONTAP REST: `POST /storage/volumes/{uuid}/snapshots` | VPC Lambda |
| Delete snapshot | ONTAP REST: `DELETE /storage/volumes/{uuid}/snapshots/{uuid}` | VPC Lambda |
| Update snapshot policy | ONTAP REST: `PATCH /storage/snapshot-policies/{uuid}` | VPC Lambda |
| Enable/disable ARP | ONTAP REST: `PATCH /storage/volumes/{uuid}` (anti_ransomware.state) | VPC Lambda |
| Acknowledge ARP suspect | ONTAP REST: `DELETE /security/anti-ransomware/suspects/{uuid}` | VPC Lambda |
| Update SnapLock retention | ONTAP REST: `PATCH /storage/volumes/{uuid}` (snaplock.retention) | VPC Lambda |
| Put S3 Object Lock config | AWS S3: `PutObjectLockConfiguration` | Standard Lambda |
| Put Object Retention | AWS S3: `PutObjectRetention` | Standard Lambda |
| Put Legal Hold | AWS S3: `PutObjectLegalHold` | Standard Lambda |

---

## Implementation Architecture

```
                     Cognito User Pool
                    ┌─────────────────┐
                    │ Groups:         │
                    │ - contributor   │
                    │ - storage-admin │
                    │ - auditor       │
                    └────────┬────────┘
                             │ JWT (cognito:groups claim)
                             ▼
                    ┌─────────────────┐
                    │ AppSync API     │
                    │                 │
                    │ Query (viewer)  │──→ allow.authenticated()
                    │ Mutation (write)│──→ allow.groups(["storage-admin"])
                    │ Audit queries   │──→ allow.groups(["storage-admin","auditor"])
                    └────────┬────────┘
                             │
               ┌─────────────┴──────────────┐
               ▼                             ▼
    ┌──────────────────┐          ┌──────────────────┐
    │ VPC Lambda        │          │ Standard Lambda   │
    │ (ONTAP REST API)  │          │ (AWS S3 API)      │
    │                   │          │                   │
    │ IAM Role:         │          │ IAM Role:         │
    │ - SecretsManager  │          │ - s3:Put*Lock*    │
    │ - VPC access      │          │ - s3:Put*Retention│
    └──────────────────┘          └──────────────────┘
```

---

## AppSync Authorization Patterns

### Read operations (all authenticated users)

```typescript
listSnapshots: a.query()
  .authorization((allow) => [allow.authenticated()])
```

### Write operations (storage-admin only)

```typescript
createSnapshot: a.mutation()
  .authorization((allow) => [allow.groups(["storage-admin"])])

updateArpState: a.mutation()
  .authorization((allow) => [allow.groups(["storage-admin"])])
```

### Audit operations (storage-admin + auditor)

```typescript
queryAuditLog: a.query()
  .authorization((allow) => [
    allow.groups(["storage-admin", "auditor"]),
  ])
```

---

## Cognito Group Setup

```bash
USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

# Create groups
aws cognito-idp create-group --group-name storage-admin --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name contributor --user-pool-id $USER_POOL_ID
aws cognito-idp create-group --group-name auditor --user-pool-id $USER_POOL_ID

# Add user to group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id $USER_POOL_ID \
  --username "admin@example.com" \
  --group-name storage-admin
```

---

## UI Behavior by Role

| Element | Viewer | Contributor | Storage Admin |
|---------|--------|-------------|---------------|
| Sidebar: Browse section | ✅ All items | ✅ All items | ✅ All items |
| Sidebar: Upload | Hidden | ✅ Visible | ✅ Visible |
| Sidebar: AI Processing | View results only | ✅ Trigger + view | ✅ Full access |
| Sidebar: Data Protection | Snapshots (read) | Snapshots (read) | ✅ Full read/write |
| Sidebar: Admin | Hidden | Hidden | ✅ Visible |
| File: Upload/Delete/Rename | Disabled | ✅ Enabled | ✅ Enabled |
| Data Protection: "Create Snapshot" button | Hidden | Hidden | ✅ Visible |
| Data Protection: "Enable ARP" toggle | Hidden | Hidden | ✅ Visible |
| Lock: "Update Retention" form | Hidden | Hidden | ✅ Visible |

---

## Security Considerations

- **Storage Admin is high-privilege**: Can modify ARP (disable protection), delete snapshots (data loss), change retention (compliance risk). Assign carefully.
- **SnapLock Compliance mode changes are irreversible**: Once set, retention periods cannot be shortened. The UI should show a confirmation dialog with explicit warning.
- **ARP disable has a cooling period**: ONTAP pauses ARP for learning before fully disabling. UI should show the state transition clearly.
- **Audit all admin actions**: Every Data Protection mutation should log to the audit trail (who, what, when) — enforced in the Lambda handler.

---

## Related Documents

- [S3 AP Authorization Model](../s3ap-authorization-model.en.md) — S3 AP File System Identity + IAM dual-layer
- [CONFIDENTIAL Guardrail (F-2)](../../solutions/amplify-portal/README.md) — Data classification-based AI blocking
- [Cognito Group → S3 AP Routing (A-1)](../../solutions/amplify-portal/README.md) — Per-team file isolation
