# File Portal Deployment Runbook

> 🌐 **Language / 言語**: [日本語](../ja/portal-deployment-runbook.md) | English

Step-by-step operational guide for deploying, updating, and tearing down the FSx for ONTAP File Portal. Based on verified deployment procedures (2026-07-20).

---

## Prerequisites Checklist

| Requirement | How to verify | Notes |
|---|---|---|
| AWS CLI v2 | `aws --version` | Must be configured with credentials |
| Node.js 18.17+ | `node --version` | Required by Amplify Gen2 CDK |
| AWS Account | `aws sts get-caller-identity` | Note your Account ID |
| FSx for ONTAP | `aws fsx describe-file-systems` | ONTAP 9.14.1+ recommended |
| S3 AP (Internet-origin) | See Step 1 below | Or use DemoMode (regular S3 bucket) |

---

## Step 1: Create S3 Access Point (if not already done)

```bash
# Find your volume ID
aws fsx describe-volumes \
  --query 'Volumes[?OntapConfiguration.JunctionPath!=`null`].{Name:Name,Id:VolumeId,Path:OntapConfiguration.JunctionPath,SVM:OntapConfiguration.StorageVirtualMachineId}' \
  --output table

# Create S3 AP (Internet-origin, UNIX root identity for demo)
cat > /tmp/create-s3ap.json << 'EOF'
{
  "Name": "portal-demo",
  "Type": "ONTAP",
  "OntapConfiguration": {
    "VolumeId": "<YOUR_VOLUME_ID>",
    "FileSystemIdentity": {
      "Type": "UNIX",
      "UnixUser": { "Name": "root" }
    }
  }
}
EOF

aws fsx create-and-attach-s3-access-point \
  --cli-input-json file:///tmp/create-s3ap.json \
  --region ap-northeast-1

# Wait for AVAILABLE status
aws fsx describe-s3-access-point-attachments \
  --query 'S3AccessPointAttachments[?Name==`portal-demo`].{Status:Lifecycle,Alias:S3AccessPoint.Alias}' \
  --output table
```

> **Learned**: The `create-and-attach-s3-access-point` API requires `Name`, `Type`, and `OntapConfiguration.VolumeId` (not FileSystemId or JunctionPath). The alias is auto-generated and returned in the response.

> **Timing**: S3 AP creation takes 1-3 minutes to reach AVAILABLE.

---

## Step 2: Configure the Portal

```bash
cd solutions/amplify-portal

# Install dependencies (one-time)
make install

# Create config from template
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

Edit `amplify/portal-config.ts`:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",                              // Your FSx region
  s3ApAlias: "portal-demo-xxx-ext-s3alias",             // From Step 1
  stateMachineArn: "arn:aws:states:...:placeholder",    // Or real UC pattern ARN
  stateMachineResourceScope: "*",                        // Restrict in production
  s3ApResourceArns: [
    "arn:aws:s3:*:*:accesspoint/*",
    "arn:aws:s3:*:*:accesspoint/*/object/*",
  ],
  groupApMapping: {},                                    // Empty = all users share same AP
  bedrockKbId: "",                                       // Empty = search disabled
};
```

`src/portal-settings.ts` holds UI feature switches only:

```typescript
export const portalSettings = {
  processingEnabled: false,       // Set true after configuring SFn ARN
  aiAgentEnabled: false,          // Bedrock KB bills continuously, so default off
};
```

> **Learned**: The S3 AP alias belongs in exactly one file, `amplify/portal-config.ts`. It used to be needed in `src/portal-settings.ts` as well, and because that file is committed it shipped with a placeholder — so the Upload tab uploaded to an access point that does not exist and failed every file. `amplify/backend.ts` now publishes the alias through `backend.addOutput({ custom: ... })` into `amplify_outputs.json`, which the browser reads.

---

## Step 3: Deploy Sandbox

```bash
make sandbox
```

**First-time**: ~5 minutes (CDK bootstrap + full stack creation)
**Subsequent**: ~30-90 seconds (incremental update)

**What gets created**:
- Cognito User Pool + Identity Pool
- AppSync GraphQL API (20+ resolvers)
- 10+ Lambda functions (Python 3.12, ARM64)
- 3 DynamoDB tables (JobExecution, FileNotification, Favorite, FileTag, FolderWatch, RecentFile)
- IAM roles (least-privilege per Lambda)

> **Learned**: All resources are in the same CDK stack. Cross-stack references cause resolver binding failures.

---

## Step 4: Create Test User

```bash
# Get User Pool ID from outputs
USER_POOL_ID=$(python3 -c "import json; print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

# Create user
aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "demo@example.com" \
  --temporary-password "TempPass1!" \
  --user-attributes Name=email,Value=demo@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region ap-northeast-1

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username "demo@example.com" \
  --password "Demo1234!" \
  --permanent \
  --region ap-northeast-1
```

> **Learned**: `--message-action SUPPRESS` prevents Cognito from trying to send verification email (which fails for fake addresses). `admin-set-user-password --permanent` avoids the "force change password" flow on first login.

---

## Step 5: Start Development Server

```bash
make dev
# → http://localhost:5173
```

Or for production preview:
```bash
npx vite build && npx vite preview --port 4173
# → http://localhost:4173
```

---

## Step 6: Deploy to Production (Amplify Hosting)

```bash
# Build
npx vite build

# Create Amplify app (one-time)
aws amplify create-app --name "your-portal-name" --region ap-northeast-1
# Note the appId

# Create branch
aws amplify create-branch --app-id <APP_ID> --branch-name main

# Create deployment job
aws amplify create-deployment --app-id <APP_ID> --branch-name main
# Note the jobId and zipUploadUrl

# Upload dist/
cd dist && zip -r /tmp/deploy.zip .
curl -T /tmp/deploy.zip "<zipUploadUrl>"

# Start deployment
aws amplify start-deployment --app-id <APP_ID> --branch-name main --job-id <JOB_ID>

# URL: https://main.<APP_ID>.amplifyapp.com
```

> **Learned**: Amplify Hosting manual deploy flow: create-deployment → upload zip to presigned URL → start-deployment. The `create-deployment` response includes `zipUploadUrl` (valid for 3 hours).

---

## Teardown (Complete Cleanup)

Execute in this order (dependency chain):

```bash
# 1. Amplify Hosting (if deployed)
aws amplify delete-app --app-id <APP_ID> --region ap-northeast-1

# 2. Amplify Sandbox (all backend resources)
make sandbox-delete
# This removes: Cognito, AppSync, Lambda, DynamoDB, IAM roles

# 3. S3 Access Point
aws fsx detach-and-delete-s3-access-point \
  --name portal-demo \
  --region ap-northeast-1

# 4. Verify no orphaned resources
aws cloudformation describe-stacks \
  --query 'Stacks[?contains(StackName, `amplify-fsxn`)].StackName' \
  --output text
# Expected: empty
```

> **Learned**: `sandbox-delete` is complete — removes ALL resources. No partial cleanup. Takes ~2 minutes.

> **Learned**: S3 AP deletion requires the AP to not be referenced by any active CloudFormation stack. Delete sandbox first, then AP.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Files tab: "No files" | `s3ApAlias` empty in portal-config.ts | Set alias, re-run `make sandbox` |
| **Files tab: "No files" (DemoMode)** | **`s3ApResourceArns` only has S3 AP ARNs, not bucket ARNs** | **Add `arn:aws:s3:::your-bucket` + `arn:aws:s3:::your-bucket/*` to `s3ApResourceArns`** |
| Upload tab: "not configured" | `s3ApAlias` empty in portal-config.ts, or sandbox not run | Set the alias, run `npx ampx sandbox`, reload |
| Upload or create folder: 501 NotImplemented | The S3 AP does not implement `if-none-match` (conditional write), which Storage Browser's default handlers send | Use the replacement handlers in `src/lib/storageBrowserWriteHandlers.ts` (on by default) |
| Upload tab: "ListCallerAccessGrants" | Old code using `createManagedAuthAdapter` | Update StorageBrowserTab.tsx to direct auth mode |
| Process tab: red banner | Step Functions ARN is placeholder | `make sfn-test-create` or deploy UC pattern |
| Login fails | User not created or password not set | Run Step 4 commands |
| `make sandbox` fails: "Cannot find module ./portal-config" | portal-config.ts not created | `cp portal-config.example.ts portal-config.ts` |
| AppSync resolver: "Data source not found" | Data source in wrong CDK stack | All data sources must be in same stack as API |
| **sandbox deploy takes 2+ minutes** | **IAM policy / env var changed (not hot-swappable)** | **Expected behavior. Lambda code-only changes deploy in ~7s** |
| **cdk-nag blocks sandbox deploy** | Only if cdk-nag is made always-on (off by default, so normally cannot occur) | Deploy without `CDK_NAG=1`. Inspect nag separately with `CDK_NAG=1 npx ampx generate outputs` |

> **DemoMode IAM lesson**: S3 AP ARNs (`arn:aws:s3:*:*:accesspoint/*`) and regular S3 bucket ARNs (`arn:aws:s3:::bucket-name`) have **different formats**. When using DemoMode with a regular S3 bucket, you must add both the bucket ARN and the object-level ARN to `s3ApResourceArns` in `portal-config.ts`.

---

## Costs

| Resource | Sandbox (idle) | Production (100 users) |
|----------|:---:|:---:|
| Cognito | $0 | $0 (< 50K MAU free) |
| AppSync | $0 | ~$4/month |
| Lambda (10 functions) | $0 | ~$3/month |
| DynamoDB (6 tables) | $0 | ~$1/month |
| Amplify Hosting | N/A | ~$5/month |
| **Total portal cost** | **$0** | **~$13/month** |

> FSx for ONTAP infrastructure cost (~$194/month minimum) is separate and shared with NFS/SMB workloads.

---

## Configuration Reference

| Parameter | File | Purpose |
|-----------|------|---------|
| `s3ApAlias` | portal-config.ts | Backend Lambda file access, and the Upload tab via `amplify_outputs.json` |
| `region` | portal-config.ts | Must match FSx for ONTAP region |

### Read the alias from the API

Copying `s3ApAlias` by hand lets a deleted or `MISCONFIGURED` access point keep looking correct in
a config file. Derive the inventory from the FSx API instead.

```bash
make discover-s3ap ARGS="--lifecycle AVAILABLE --format table"   # usable access points
make discover-s3ap ARGS="--require-alias <alias>"                # non-zero when absent
REGIONS="ap-northeast-1 us-east-1" make discover-s3ap            # several regions
make discover-s3ap ARGS="--accounts 111111111111 222222222222 --role-name <role>"
```

`--require-alias` works as a pre-deployment gate: it fails unless the alias is `AVAILABLE`.
| `stateMachineArn` | portal-config.ts + start-processing.js | Process tab workflow trigger |
| `groupApMapping` | portal-config.ts | Per-team file isolation (My Files) |
| `bedrockKbId` | portal-config.ts | Full-text semantic search |
| `ONTAP_MGMT_IP` | Lambda env var | Version History (Snapshot listing) |
| `CLASSIFICATION_TABLE_NAME` | Lambda env var | CONFIDENTIAL guardrail |
| `AI_METADATA_TABLE_NAME` | Lambda env var | AI result inline badges |
