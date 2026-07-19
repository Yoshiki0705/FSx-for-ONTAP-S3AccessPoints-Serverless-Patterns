# Production Amplify Hosting Deployment Guide

Deploy the FSx for ONTAP File Portal as a production web application using AWS Amplify Hosting with branch-based CI/CD, custom domain, and enterprise authentication.

---

## Prerequisites

| Item | Requirement |
|---|---|
| Amplify portal | `solutions/amplify-portal/` working locally (`npm run dev`) |
| GitHub repository | Fork or clone with push access |
| FSx for ONTAP S3 AP | AVAILABLE, Internet origin |
| Custom domain (optional) | Route53 hosted zone or external DNS |
| Cognito User Pool | Created by Amplify sandbox or manually |

---

## Deployment Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Amplify Hosting (Branch-based CI/CD)                             │
│ ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│ │ main branch              │  │ dev branch                   │  │
│ │ → Production environment │  │ → Preview environment        │  │
│ │ → Custom domain          │  │ → amplify-generated URL      │  │
│ └──────────────────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ Amplify Gen2 Backend (per-branch)                                │
│ - Cognito User Pool (auth)                                       │
│ - AppSync API (data)                                             │
│ - Lambda: ListFiles, GetPresignedUrl                             │
│ - DynamoDB: JobExecution                                         │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ FSx for ONTAP                                                    │
│ - S3 Access Point (Internet origin)                              │
│ - Volume: /your-data (NFS/SMB/S3 concurrent access)              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Configure Environment Variables

Create `amplify/portal-config.ts` from the example:

```bash
cp solutions/amplify-portal/amplify/portal-config.example.ts \
   solutions/amplify-portal/amplify/portal-config.ts
```

Edit the values:

```typescript
export const config: PortalConfig = {
  // Find with: aws fsx describe-s3-access-point-attachments --query '...Alias'
  region: "ap-northeast-1",
  s3ApAlias: "your-ap-alias-ext-s3alias",

  // Find with: aws stepfunctions list-state-machines --query '...stateMachineArn'
  stateMachineArn: "arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc1-workflow",
  stateMachineResourceScope: "arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc*",

  // Production: scope to specific S3 AP ARN
  s3ApResourceArns: [
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name",
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/your-ap-name/object/*",
  ],
};
```

Enable frontend features in `src/portal-settings.ts`:

```typescript
export const portalSettings = {
  processingEnabled: true,  // Enable after stateMachineArn is configured
  fileListingEnabled: true, // Enable after S3 AP alias is configured
};
```

---

## Step 2: Connect Repository to Amplify Hosting

### Option A: AWS Console

1. Open [Amplify Console](https://console.aws.amazon.com/amplify/)
2. **Create new app** → **Host a web app**
3. Select **GitHub** → Authorize → Choose your repository
4. Branch: `main`
5. Build settings are auto-detected from `amplify/` directory
6. **Save and deploy**

### Option B: CLI

```bash
cd solutions/amplify-portal

# Initialize Amplify Hosting (first time)
npx ampx pipeline-deploy --branch main --app-id <YOUR_APP_ID>
```

---

## Step 3: Environment Variables in Amplify Console

For production, override `portal-config.ts` defaults via Amplify environment variables:

| Variable | Value | Notes |
|---|---|---|
| `AMPLIFY_PORTAL_REGION` | `ap-northeast-1` | Must match FSx for ONTAP region |
| `AMPLIFY_PORTAL_S3AP_ALIAS` | `your-ap-alias-ext-s3alias` | From `aws fsx describe-s3-access-point-attachments` |
| `AMPLIFY_PORTAL_SFN_ARN` | `arn:aws:states:...` | Step Functions state machine ARN |
| `AMPLIFY_PORTAL_SFN_SCOPE` | `arn:aws:states:...:stateMachine:uc*` | IAM scope for SFn permissions |

Set these in: Amplify Console → App settings → Environment variables.

---

## Step 4: Custom Domain (Optional)

### With Route53

1. Amplify Console → Domain management → Add domain
2. Select your Route53 hosted zone
3. Configure subdomains:
   - `portal.example.com` → `main` branch
   - `dev-portal.example.com` → `dev` branch
4. SSL certificate is provisioned automatically

### With External DNS

1. Amplify Console → Domain management → Add domain
2. Enter your domain name
3. Amplify provides CNAME records to add to your DNS provider
4. Verify ownership and wait for certificate provisioning

---

## Step 5: Enterprise Authentication (Cognito)

### SAML Federation (Okta, Azure AD, etc.)

Add to `amplify/auth/resource.ts`:

```typescript
import { defineAuth } from "@aws-amplify/backend";

export const auth = defineAuth({
  loginWith: {
    email: true,
    externalProviders: {
      saml: {
        name: "CorporateSSO",
        metadata: {
          metadataContent: "https://your-idp.example.com/metadata.xml",
          // or metadataType: "FILE" with inline XML
        },
        attributeMapping: {
          email: { attributeName: "email" },
          fullname: { attributeName: "displayName" },
        },
      },
      callbackUrls: ["https://portal.example.com/"],
      logoutUrls: ["https://portal.example.com/"],
    },
  },
});
```

### OIDC Federation (Google Workspace, etc.)

```typescript
externalProviders: {
  oidc: [{
    name: "GoogleWorkspace",
    clientId: "xxx.apps.googleusercontent.com",
    clientSecret: "your-secret", // Use Secrets Manager reference
    issuerUrl: "https://accounts.google.com",
    attributeMapping: {
      email: { attributeName: "email" },
    },
  }],
  callbackUrls: ["https://portal.example.com/"],
  logoutUrls: ["https://portal.example.com/"],
},
```

---

## Step 6: Production Checklist

| Item | Action | Verify |
|---|---|---|
| IAM least-privilege | Scope `s3ApResourceArns` to specific AP ARN | `portal-config.ts` |
| SFn scope | Scope `stateMachineResourceScope` to specific pattern | `portal-config.ts` |
| Cognito MFA | Enable MFA in Cognito User Pool (optional but recommended) | Amplify Console → Auth |
| Custom domain | Configure HTTPS with Route53 or external DNS | Amplify → Domain management |
| WAF (optional) | Attach AWS WAF to CloudFront distribution | CloudFormation or Console |
| Monitoring | Enable CloudWatch alarms for Lambda errors | CloudWatch Console |
| Budget alert | Set cost alert for Amplify + Lambda + DynamoDB | AWS Budgets |
| CORS | Verify S3 AP allows requests from your domain | S3 AP policy |

---

## Cost Estimate (Production)

| Resource | Monthly Cost (100 users, moderate usage) |
|---|---|
| Amplify Hosting | ~$5 (build minutes + hosting) |
| Cognito | Free tier (50K MAU free) |
| AppSync | ~$4 (queries) |
| Lambda (ListFiles + GetPresignedUrl) | ~$2 |
| DynamoDB (JobExecution) | ~$1 |
| **Total** | **~$12/month** |

> FSx for ONTAP costs are separate (existing infrastructure). The portal adds minimal cost on top.

---

## Branch-Based Environments

Amplify Gen2 creates isolated backend environments per branch:

```
main   → production backend (Cognito, AppSync, Lambda, DynamoDB)
dev    → development backend (separate Cognito pool, separate DynamoDB)
feat/* → preview environments (auto-deployed on PR)
```

Each environment has its own Cognito User Pool, so production users and dev test users are completely isolated.

---

## Rollback

If a deployment introduces issues:

```bash
# Amplify Console → Deployments → Select previous successful build → Redeploy
# Or via CLI:
npx ampx pipeline-deploy --branch main --app-id <APP_ID> --commit-id <PREVIOUS_COMMIT>
```

---

## Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| Build fails with "Cannot find module" | Missing `portal-config.ts` | Copy from `.example.ts` and configure |
| "AccessDenied" on ListFiles | S3 AP alias not set or IAM insufficient | Check `AMPLIFY_PORTAL_S3AP_ALIAS` env var |
| Presigned URL returns error | Lambda missing S3:GetObject permission | Verify `s3ApResourceArns` includes AP ARN + `/object/*` |
| Cognito "redirect_mismatch" | Callback URL doesn't match Amplify domain | Update `callbackUrls` in auth config |
| Slow initial load | Lambda cold start | Normal (~2s first request). Consider Provisioned Concurrency for enterprise |

---

## Related

- [Local development setup](../../solutions/amplify-portal/README.md)
- [Storage Browser demo guide](./storage-browser-demo-guide.md)
- [S3 AP compatibility notes](../s3ap-compatibility-notes.en.md)
