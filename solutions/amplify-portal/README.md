# FSx for ONTAP File Portal — Amplify Gen2

Web-based file portal for browsing, processing, and viewing results on FSx for ONTAP volumes via S3 Access Points.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Amplify Gen2                                           │
│  ┌──────────┐  ┌─────────────────────────────────────┐  │
│  │ Cognito  │  │ AppSync GraphQL API                 │  │
│  │ Auth     │  │  startProcessing → Step Functions   │  │
│  │ +MFA     │  │  getJobStatus → Step Functions      │  │
│  │ +SAML    │  │  listFiles → Lambda → S3 AP         │  │
│  └──────────┘  └──────────────┬──────────────────────┘  │
│                               │                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ CDK (in data stack)                                 │ │
│  │  - HTTP Data Source → states.<region>.amazonaws.com │ │
│  │  - Lambda Data Source → ListFiles (Python 3.12)     │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌─────────────────────────┐
│ Step Functions   │          │ FSx for ONTAP           │
│ (UC pattern or   │          │ S3 Access Point         │
│  test workflow)  │          │ (Internet-origin)       │
└──────────────────┘          └─────────────────────────┘
```

---

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| Node.js | 18.17+ (required by Amplify Gen2) |
| AWS CLI | v2 configured with credentials |
| AWS account | Permissions for Amplify, Cognito, AppSync, Lambda, Step Functions |
| (Optional) FSx for ONTAP | With **Internet-origin** S3 AP attached (VPC-origin NOT supported by this portal) |
| (Optional) Deployed UC pattern | For Step Functions integration |

> ⚠️ **Sandbox resources persist until explicitly deleted.** After testing, always run `make sandbox-delete` to avoid leaving orphaned AWS resources (Cognito User Pool, AppSync API, Lambda). See [Cleanup](#cleanup).

---

## Quick Start (5 minutes)

> **Timing**: First-time setup takes ~8 minutes total (npm install ~2min + sandbox deploy ~5min). Subsequent iterations are much faster (~30s for sandbox updates).

```bash
# 1. Install dependencies
make install

# 2. Create your configuration
cp amplify/portal-config.example.ts amplify/portal-config.ts
# Edit portal-config.ts — at minimum set your region

# 3. Deploy backend to personal sandbox (~3-5 min first time, ~30s incremental)
make sandbox

# 4. In another terminal, start the dev server
make dev

# 5. Open http://localhost:5173 in your browser
#    Sign up with email → verify code (or use CLI: see below) → log in
```

### First-Time User Verification (CLI shortcut)

Cognito sends a verification email, but for test accounts you can confirm via CLI:

```bash
# Replace with your User Pool ID from amplify_outputs.json
aws cognito-idp admin-confirm-sign-up \
  --user-pool-id <USER_POOL_ID> \
  --username "your-email@example.com" \
  --region ap-northeast-1
```

---

## Configuration

All environment-specific parameters are in `amplify/portal-config.ts`.

### Setup

```bash
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

Edit `portal-config.ts`:

| Parameter | Required | Example | Description |
|---|---|---|---|
| `region` | Yes | `"ap-northeast-1"` | AWS Region for Step Functions and S3 AP |
| `s3ApAlias` | No | `"myap-abc123-s3alias"` | S3 AP alias or bucket name. Empty = "No files" |
| `stateMachineArn` | No | `"arn:aws:states:..."` | Step Functions ARN for processing |
| `stateMachineResourceScope` | No | `"*"` | IAM scope (use specific ARN in production) |
| `s3ApResourceArns` | No | `["arn:aws:s3:..."]` | IAM scope for S3 AP (restrict in production) |

### Environment Variable Override

Instead of editing the file, you can set environment variables:

```bash
export AMPLIFY_PORTAL_REGION=ap-northeast-1
export AMPLIFY_PORTAL_S3AP_ALIAS=myap-abc123-s3alias
export AMPLIFY_PORTAL_SFN_ARN=arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc1-workflow
```

---

## Deployment Guide

### Quick Demo Path (Fastest)

```bash
make install
cp amplify/portal-config.example.ts amplify/portal-config.ts
make sfn-test-create   # Creates test SFn — note the ARN in the output
# Edit portal-config.ts: paste the ARN into stateMachineArn
# Edit amplify/data/resolvers/start-processing.js: paste the ARN (line 6)
make sandbox
make dev
```

> **Two-place ARN sync**: The state machine ARN must be set in both `portal-config.ts` (for IAM scoping) and `start-processing.js` (for runtime invocation). This is a known limitation of APPSYNC_JS resolvers which cannot read CDK parameters at runtime. See [Known Pitfalls #6](#6-two-place-arn-configuration).

### DemoMode (No FSx for ONTAP)

For development without FSx for ONTAP:

1. Leave `s3ApAlias` empty (Files tab shows "No files") or set a regular S3 bucket name
2. Create a test Step Functions state machine: `make sfn-test-create`
3. Paste the returned ARN into `portal-config.ts`
4. Redeploy: `make sandbox`

### Connecting to FSx for ONTAP S3 Access Point

1. Create an S3 AP attached to your FSx for ONTAP volume (Internet-origin recommended)
2. Note the AP alias from AWS Console → FSx → S3 Access Points
3. Set `s3ApAlias` in `portal-config.ts`
4. Redeploy: `make sandbox`

> **Note**: The ListFiles Lambda runs VPC-external (no VpcConfig). This is intentional — Internet-origin S3 APs are accessible without VPC placement. If using a VPC-origin AP, you must add VPC configuration to the Lambda.

> **Throughput note**: S3 AP operations share FSx for ONTAP throughput capacity with NFS/SMB workloads. For concurrent user planning, see [Throughput and Capacity Planning](../../docs/file-portal-amplify-gen2.md#スループットと容量計画).

> **Performance note**: The ListFiles Lambda typically responds in 100-300ms for directories with < 100 objects. For directories with 1000 objects (max single page), expect 300-800ms. The Lambda has a 30-second timeout as a safety net, but normal operation is well under 1 second.

### Connecting to a Deployed UC Pattern

After deploying a UC pattern (e.g., `make deploy-uc1` from the repo root):

1. Note the State Machine ARN from the CloudFormation outputs
2. Set `stateMachineArn` in `portal-config.ts`
3. Update `start-processing.js` resolver with the ARN
4. Redeploy: `make sandbox`

---

## Known Pitfalls (Lessons Learned)

Issues discovered during verification that save you debugging time:

### 1. APPSYNC_JS Resolver Limitations

AppSync JavaScript resolvers (APPSYNC_JS runtime) have significant restrictions:

| ❌ Not Allowed | ✅ Use Instead |
|---|---|
| `new Date()` | `util.time.nowISO8601()` or return epoch, parse on frontend |
| Template literals (`` `${x}` ``) | String concatenation (`"a" + b + "c"`) |
| `async/await` | Synchronous only |
| Global constructors (`String()`, `Number()`) | Direct values |

### 2. Cross-Stack Data Source Binding

Data sources (HTTP, Lambda) **must** be added to the same CDK stack as the AppSync API. If you use `backend.createStack()` for data sources, resolvers will fail with "Data source not found" because they reference a different CloudFormation stack.

**Solution**: Use `Stack.of(api)` to get the data stack, and add all data sources there.

### 3. Step Functions Epoch Seconds

`DescribeExecution` returns `startDate` and `stopDate` as Unix epoch **seconds** (not milliseconds, not ISO 8601). The resolver returns them as strings; the frontend multiplies by 1000 for JavaScript `Date`.

### 4. IAM Permission for S3 Buckets vs S3 Access Points

The Lambda IAM policy uses `arn:aws:s3:*:*:accesspoint/*` which covers S3 Access Points. If you use a **regular S3 bucket** for DemoMode testing, you need to add bucket-format ARN permissions:

```bash
# Temporary: add via CLI for testing
aws iam put-role-policy --role-name <LAMBDA_ROLE_NAME> \
  --policy-name S3BucketTestAccess \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket","s3:GetObject"],"Resource":["arn:aws:s3:::<BUCKET>","arn:aws:s3:::<BUCKET>/*"]}]}'
```

Or update `s3ApResourceArns` in `portal-config.ts` to include the bucket ARN.

### 5. Cognito Verification Email

Test accounts using non-existent email addresses won't receive verification codes. Use the CLI shortcut:

```bash
aws cognito-idp admin-confirm-sign-up \
  --user-pool-id <USER_POOL_ID> \
  --username "test@example.com" \
  --region <REGION>
```

### 6. Two-Place ARN Configuration

The Step Functions state machine ARN must be set in **two places**:

1. `amplify/portal-config.ts` → `stateMachineArn` (used for IAM policy scoping in CDK)
2. `amplify/data/resolvers/start-processing.js` → `const stateMachineArn = "..."` (used at runtime by the AppSync resolver)

This duplication exists because APPSYNC_JS resolvers cannot read CDK parameters or environment variables at runtime. They are static JavaScript evaluated by AppSync's built-in runtime.

**Forgetting to update one of the two** is the most common deployment issue.

### 7. State Machine ARN in Resolver Is Not a Secret

The ARN hardcoded in `start-processing.js` is visible in the source code. This is acceptable because:
- ARNs are not secrets — they identify resources but don't grant access
- IAM policies (not ARNs) control who can invoke a state machine
- The AppSync API requires Cognito authentication before any resolver executes

However, the ARN is **environment-specific** — always update it when switching between dev/staging/prod.

---

## Development Commands

| Command | Description |
|---|---|
| `make install` | Install npm dependencies |
| `make dev` | Start Vite dev server (frontend only) |
| `make sandbox` | Deploy/update Amplify backend (personal sandbox) |
| `make sandbox-delete` | Delete all sandbox resources |
| `make sandbox-status` | Show CloudFormation stack status |
| `make sfn-test-create` | Create a test Step Functions state machine |
| `make sfn-test-delete` | Delete the test state machine + IAM role |
| `make test` | Run vitest (single execution) |
| `make typecheck` | TypeScript type validation |
| `make lint` | ESLint check |
| `make build` | Production build |
| `make clean` | Remove node_modules, dist, .amplify |
| `make cleanup-all` | Delete sandbox + test SFn + test S3 data |

---

## Project Structure

```
amplify-portal/
├── amplify/
│   ├── backend.ts                  # Entry point — imports config, creates data sources
│   ├── portal-config.ts            # YOUR configuration (git-ignored)
│   ├── portal-config.example.ts    # Template — copy and customize
│   ├── auth/resource.ts            # Cognito (email + MFA + SAML/OIDC placeholders)
│   ├── data/
│   │   ├── resource.ts             # AppSync schema (queries, mutations, types)
│   │   └── resolvers/
│   │       ├── start-processing.js # HTTP → StepFunctions.StartExecution
│   │       ├── get-job-status.js   # HTTP → StepFunctions.DescribeExecution
│   │       └── list-files.js       # Lambda invoke → S3 AP ListObjectsV2
│   └── custom/
│       └── step-functions.ts       # (Reference — data sources moved to backend.ts)
├── src/
│   ├── main.tsx                    # Amplify configure + Authenticator
│   ├── App.tsx                     # 3-tab shell (Files / Process / Results)
│   └── components/
│       ├── FileExplorer.tsx        # Directory browsing with pagination
│       ├── JobSubmitForm.tsx       # Pattern selection + job submission
│       └── ResultsViewer.tsx       # Status polling + data classification display
├── amplify_outputs.json            # Auto-generated by sandbox (git-ignored)
├── package.json
├── Makefile                        # All workflow commands
└── README.md
```

---

## Cleanup

> ⚠️ **Important**: Sandbox resources are NOT automatically deleted. They persist in your AWS account until you explicitly remove them.

### Delete Sandbox (Development Resources)

```bash
make sandbox-delete
# Or manually:
npx ampx sandbox delete
```

This removes: Cognito User Pool, AppSync API, Lambda function, IAM roles.

### Delete Test Resources

```bash
make sfn-test-delete    # Remove test Step Functions state machine
make cleanup-all        # Full cleanup (sandbox + SFn + test S3 data)
```

### Estimated Costs (Sandbox)

| Resource | Monthly Cost (idle) |
|---|---|
| Cognito User Pool | $0 (< 50K MAU free) |
| AppSync | $0 (< 250K requests free) |
| Lambda | $0 (< 1M requests free) |
| **Total (sandbox idle)** | **~$0** |

---

## Production Considerations

For deploying beyond sandbox:

### Authentication

Uncomment the SAML or OIDC section in `amplify/auth/resource.ts` for enterprise SSO.

### IAM Least Privilege

> ⚠️ **Security Warning**: The default `stateMachineResourceScope: "*"` grants the AppSync data source permission to invoke **any** state machine in the account. This is acceptable for personal sandbox only. For any shared or production environment, restrict to a specific ARN pattern.

In `portal-config.ts`, restrict:
- `stateMachineResourceScope` → specific state machine ARN or pattern (e.g., `"arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc*"`)
- `s3ApResourceArns` → specific AP ARN

### Audit Trail (CloudTrail)

When the portal triggers Step Functions, CloudTrail records the **AppSync service role** as the caller — not the end user. For audit traceability, the `userId` field is embedded in the Step Functions execution input by the `start-processing.js` resolver. Query the execution history to map actions back to users.

### Hosting

Deploy frontend via Amplify Hosting (CI/CD from Git) or build and host on CloudFront + S3:

```bash
make build
# Upload dist/ to S3 + CloudFront, or connect Git repo to Amplify Hosting
```

### Access Control

The current skeleton allows any authenticated user to query any execution ARN. For production, implement owner-based authorization (store execution → userId mapping in DynamoDB).

---

## Relationship to Core Patterns

This portal is an **optional frontend layer**. It does not modify the core patterns:

- Backend Lambda functions (Python) remain in `solutions/industry/*/`
- Step Functions ASL workflows are referenced by ARN, not copied
- `shared/` Python modules are unaffected
- All existing `make test-uc*` commands work independently

---

## Related Documentation

- [File Portal UI Options (Amplify / Nextcloud / Custom)](../../docs/file-portal-amplify-gen2.md)
- [Nextcloud External Storage Setup](../../docs/nextcloud-external-storage-s3ap.md)
- [S3AP Compatibility Notes](../../docs/s3ap-compatibility-notes.md)
- [Demo Mode Guide](../../docs/demo-mode-guide.md)
