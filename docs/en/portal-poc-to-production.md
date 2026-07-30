# File Portal — PoC to Production Migration Guide

> Moving from DemoMode evaluation to production FSx for ONTAP connectivity.

## Overview

This guide covers the steps to migrate from DemoMode (regular S3 bucket) to a production deployment connected to FSx for ONTAP. DemoMode is designed for UI and workflow evaluation; production mode unlocks ONTAP management features, file-level access control, and data protection capabilities.

---

## Prerequisites

| Component | Version | Check |
|-----------|---------|-------|
| Node.js | 20.x+ | `node --version` |
| npm | 10.x+ | `npm --version` |
| AWS CLI | 2.x | `aws --version` |
| Amplify CLI | Latest | `npx ampx --version` |
| FSx for ONTAP | File system running | Console or `aws fsx describe-file-systems` |
| SVM | At least 1 SVM with management LIF | `aws fsx describe-storage-virtual-machines` |
| S3 Access Point | Attached to a volume | `aws fsx describe-data-repository-associations` |

---

## Migration Checklist

### 1. Network Configuration

| Item | Action | Verification |
|------|--------|-------------|
| VPC ID | Copy from FSx console → Network & security | `portal-config.ts` → `vpcId` |
| Subnet IDs | Same subnet(s) as FSx ENIs | `portal-config.ts` → `vpcSubnetIds` |
| Security Group | FSx's SG (allows all-traffic egress by default) | `portal-config.ts` → `vpcSecurityGroupIds` |
| Connectivity test | Lambda in VPC can reach ONTAP management LIF (443) | Deploy → check admin panel |

```typescript
// portal-config.ts — production values
export const portalConfig = {
  region: "ap-northeast-1",
  vpcId: "vpc-0xxxxxxxxxxxxxxxxx",           // ← Your VPC
  vpcSubnetIds: ["subnet-0xxxxxxxxxxxxxxxxx"], // ← Same subnet as FSx ENIs
  vpcSecurityGroupIds: ["sg-0xxxxxxxxxxxxxxxxx"], // ← FSx's own SG
  // ...
};
```

> **Why same subnet?** The VPC Lambda needs network path to the ONTAP management LIF. Placing it in the same subnet as FSx ENIs ensures this. Cross-subnet is also fine if routing and SG rules permit TCP 443.

### 2. S3 Access Point

| Item | Action | Verification |
|------|--------|-------------|
| S3 AP Alias | Copy the Internet-origin S3 AP alias | `portal-config.ts` → `s3ApAlias` |
| Network Origin | Must be `Internet` (not `VPC`) | `aws fsx describe-data-repository-associations` |
| File System Identity | UNIX user/group for portal access | Check UID/GID permissions on volume |

```typescript
  s3ApAlias: "your-ap-alias-xxxxxxxx-s3alias", // ← Internet-origin S3 AP
```

> **Internet-origin vs VPC**: The file-browsing Lambda runs OUTSIDE VPC (for fast cold starts). It accesses S3 AP via the public S3 endpoint. VPC-origin APs would require the Lambda to be inside VPC with NAT Gateway — adding cost and latency.

### 3. ONTAP Credentials

| Item | Action |
|------|--------|
| Create Secret | `aws secretsmanager create-secret --name portal/ontap-credentials --secret-string '{"username":"fsxadmin","password":"...","managementIp":"..."}'` |
| Set ARN | `portal-config.ts` → `ontapSecretArn` |
| IAM | Lambda execution role needs `secretsmanager:GetSecretValue` on this ARN |

```typescript
  ontapSecretArn: "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:portal/ontap-credentials-XXXXXX",
```

> **Security note**: Never put credentials in `portal-config.ts` directly. Always use Secrets Manager. The file is committed to Git; secrets must not be.

### 4. Authentication

| Item | Action |
|------|--------|
| MFA | Enable TOTP in Cognito User Pool settings |
| Admin group | Create `storage-admin` group, add admin users |
| (Optional) SSO | Configure SAML/OIDC federation for enterprise IdP |

After deploying with `npx ampx sandbox` or `git push`:
1. Sign up a user in Cognito console
2. Add user to `storage-admin` group
3. Sign in to portal → Admin panels now visible

### 5. Audit Trail

| Item | Action |
|------|--------|
| CloudTrail | Create Trail with S3 data events for the S3 AP ARN |
| Glue Crawler | Create crawler pointing to CloudTrail S3 bucket |
| Athena | Verify table is queryable |
| Lambda env vars | Set `ATHENA_AUDIT_DATABASE`, `ATHENA_AUDIT_TABLE`, `ATHENA_AUDIT_OUTPUT` |

### 6. Cost Verification

Estimate monthly costs before production:

| Resource | Estimate | Notes |
|----------|----------|-------|
| FSx for ONTAP | ~$194+/month | 128 MBps minimum |
| VPC Lambda (admin) | ~$5/month | Low invocation frequency |
| CloudTrail S3 data events | ~$10–50/month | Proportional to file access volume |
| Athena queries | $5/TB scanned | Audit queries are typically small |
| Secrets Manager | $0.40/secret/month | 1 secret for ONTAP credentials |
| Cognito | Free tier (50K MAU) | Typically no cost for internal teams |

---

## Deployment

```bash
# After configuring portal-config.ts with production values:
npx ampx sandbox  # Test in sandbox first

# When verified:
git add amplify/portal-config.ts
git commit -m "feat: connect portal to production FSx for ONTAP"
git push origin main  # Amplify Hosting auto-deploys
```

---

## Verification

After deployment, verify each layer:

| Check | How | Expected |
|-------|-----|----------|
| File browsing | Navigate to All Files | Volume contents visible |
| Admin panels | Click Resources in sidebar | Cards show volume/ARP/snapshot data |
| EMS Events | Open Events panel | Recent ONTAP events displayed |
| Audit Log | Run a query in Audit tab | CloudTrail events returned |
| AI Processing | Select file → Run AI | Step Functions workflow completes |

---

## Rollback

| Situation | Rollback Method |
|-----------|----------------|
| Frontend UI issue | Amplify Hosting console → redeploy previous build |
| Lambda function issue | `git revert` + `git push` (auto-deploys) |
| ONTAP config issue | ONTAP REST API to restore (export-policy, name-mapping) |
| Cognito config issue | Manual restoration (CDK stack rollback not supported) |

> **Important**: Some ONTAP operations (SnapLock enable) are irreversible. Always verify in DemoMode or non-production volume first.

---

## Related Documents

- [Getting Started Guide](../../solutions/amplify-portal/docs/GETTING-STARTED.md)
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md)
- [Security Review](../../solutions/amplify-portal/docs/SECURITY-REVIEW.md)
- [Scaling Guide](./portal-scaling-guide.md)
- [DemoMode Guide](../demo-mode-guide.md)
