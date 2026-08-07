# Multi-Tenant Design Patterns

> 🌐 Language: **English** | [日本語](../ja/multi-tenant-design.md)

## Overview

For ISVs or managed service providers who want to offer this portal as a service to multiple tenants (organizations/teams), this document describes data isolation patterns.

## Isolation Levels

| Level | Mechanism | Use Case |
|-------|-----------|----------|
| **Group-based** | `groupApMapping` in portal-config.ts | Teams within one organization |
| **Cognito Group** | Separate Cognito groups per tenant | Small number of tenants (<20) |
| **DynamoDB Partition** | Tenant ID as partition key | SaaS with many tenants |
| **Separate Stacks** | One Amplify stack per tenant | Full isolation (enterprise) |

## Pattern 1: groupApMapping (Recommended for Teams)

Each team gets a different S3 Access Point with a different File System Identity (UNIX UID/GID). Users in that Cognito group only see files accessible to their UID.

```typescript
// portal-config.ts
groupApMapping: {
  "engineering": "ap-eng-uid1001-xxx-s3alias",   // UID 1001
  "legal":       "ap-legal-uid1002-xxx-s3alias", // UID 1002
  "finance":     "ap-fin-uid1003-xxx-s3alias",   // UID 1003
}
```

**Data isolation**: ONTAP UNIX permissions enforce visibility. UID 1001 cannot read files owned by UID 1002.

## Pattern 2: DynamoDB Tenant Isolation

For DynamoDB models (JobExecution, Favorite, RecentFile, etc.), add a `tenantId` field as the partition key:

```typescript
// amplify/data/resource.ts
const schema = a.schema({
  JobExecution: a.model({
    tenantId: a.string().required(),  // Partition key
    jobId: a.string(),
    // ...
  }).authorization(allow => [
    allow.owner(),
    allow.groups(["storage-admin"]),
  ]),
});
```

**Query pattern**: All queries include `tenantId` filter. AppSync resolvers inject tenant ID from Cognito token claims.

## Pattern 3: Separate Amplify Stacks (Full Isolation)

For enterprise tenants requiring complete infrastructure separation:

```bash
# Deploy per-tenant stack with unique identifier
npx ampx sandbox --identifier tenant-acme
npx ampx sandbox --identifier tenant-globex
```

Each gets its own: Cognito User Pool, AppSync API, Lambda functions, DynamoDB tables.

## Security Considerations

- **Row-level security**: DynamoDB Condition expressions prevent cross-tenant data access
- **S3 AP isolation**: Each tenant's S3 AP uses a different File System Identity — ONTAP enforces access at the file system level
- **IAM boundaries**: Use Permission Boundaries to limit what tenant-specific roles can do
- **Audit**: CloudTrail logs include Cognito user identity — traceable to tenant

## References

- [Amplify Gen2: Multi-tenancy](https://docs.amplify.aws/gen2/build-a-backend/auth/concepts/multi-tenancy/)
- [DynamoDB tenant isolation](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/dynamodb-isolation.html)
