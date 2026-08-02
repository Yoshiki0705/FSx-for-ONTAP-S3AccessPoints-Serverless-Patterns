# AppSync Authorization Troubleshooting (Amplify Gen2)

## Issue: "User is not authorized" on Custom Query/Mutation

### Symptom

- Custom `adminQuery` (list operations) works fine
- Custom `adminMutation` (create/delete operations) returns `"User is not authorized."`
- User is confirmed signed-in (Cognito User Pools)
- `data/resource.ts` has `.authorization((allow) => [allow.authenticated()])`
- Sandbox deployment shows success

### Root Cause

In Amplify Gen2 with multiple auth providers configured (Cognito User Pools + IAM), `generateClient<Schema>()` without an explicit `authMode` parameter may **not send the Cognito ID Token** to AppSync. Instead, it may use IAM or another default mode, causing AppSync to reject the request.

This is documented behavior:
- [Amplify Docs: AI Generation example](https://docs.amplify.aws/react/ai/generation/) shows `generateClient<Schema>({ authMode: "userPool" })`
- [openillumi.com: How to Fix AWS Amplify GraphQL Unauthorized Errors](https://openillumi.com/en/en-amplify-graphql-unauthorized-fix-authmode/) — explicitly specifying `authMode` is the definitive fix

Content was rephrased for compliance with licensing restrictions.

### Solution

Always specify `authMode: "userPool"` when creating the Amplify data client:

```typescript
// BEFORE (broken): authMode not specified
const client = generateClient<Schema>();

// AFTER (fixed): explicit authMode
const client = generateClient<Schema>({ authMode: "userPool" });
```

### Why List Worked But Create Failed

The list operation (`adminQuery` with `action: "listFlexCaches"`) uses a **Query** type in GraphQL. AppSync may have a cached/default behavior that allows Query types through with the available credentials. However, **Mutation** types (`adminMutation` with `action: "createFlexCache"`) undergo stricter authorization checks that require the explicit Cognito token.

### Additional Issue: CloudFormation "Group Already Exists"

When adding `groups: ["storage-admin"]` to `amplify/auth/resource.ts` and the group was previously created manually in the Cognito User Pool console, CloudFormation fails with:

```
Group storage-admin already exists in UserPool ap-northeast-1_XXXXX
```

**Solution**: Do not declare `groups` in `defineAuth` if the group already exists. Manage group membership via CLI/console instead:

```bash
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <pool-id> \
  --username <user-id> \
  --group-name storage-admin
```

### Affected Components

| Component | File | Fix Applied |
|-----------|------|-------------|
| FlexCacheManager | `src/components/admin/FlexCacheManager.tsx` | `authMode: "userPool"` |
| SnapMirrorStatus | `src/components/admin/SnapMirrorStatus.tsx` | `authMode: "userPool"` |
| VolumeManager | `src/components/admin/VolumeManager.tsx` | Should also add `authMode: "userPool"` |

### Verification

1. Ensure sandbox is deployed (`amplify_outputs.json` updated)
2. Sign out and sign back in (refresh Cognito token)
3. Navigate to Resource Management > FlexCache
4. Click "+ FlexCache Create" > fill form > Submit
5. Should see success message (or ONTAP error, not auth error)

### References

- [Amplify Gen2 Docs: Customize Authorization](https://docs.amplify.aws/react/build-a-backend/data/customize-authz/)
- [AWS re:Post: Schema difference between Mutation and Query](https://repost.aws/questions/QUBa3YlvqRQsuex_K4YVS9RA)
- [openillumi.com: Fix unauthorized errors using authMode](https://openillumi.com/en/en-amplify-graphql-unauthorized-fix-authmode/)

---

## Issue: "User is not authorized" from ONTAP REST API (Lambda-Level)

> **Canonical reference**: 詳細な接続アーキテクチャ、パスワード管理、ロックアウト復旧手順は [ONTAP-CONNECTION-GUIDE.md](./ONTAP-CONNECTION-GUIDE.md) を参照してください。

### 要約

- ONTAP REST API が 401 を返す主要原因: **パスワード不一致** または **アカウントロックアウト**
- 復旧: `aws fsx update-file-system` でパスワードリセット → Secrets Manager 同期
- 詳細な手順とアーキテクチャ図: [ONTAP-CONNECTION-GUIDE.md](./ONTAP-CONNECTION-GUIDE.md)

---

## Issue: Lambda Timeout on FlexCache POST (Root Cause Found)

### Symptom

- `listFlexCaches` (GET) completes in 4-5 seconds ✅
- `createFlexCache` (POST) causes Lambda to timeout at 60 seconds ❌
- CloudWatch logs show `Duration: 60000.00 ms  Status: timeout`
- Error displayed as "User is not authorized" (misleading — actual cause is timeout)

### Root Cause

ONTAP REST API `POST /storage/flexcache/flexcaches` is a **synchronous long-running operation** by default. Without `return_timeout=0`, ONTAP holds the HTTP connection open until the FlexCache is fully created (which can take 30-120+ seconds depending on volume size). This exceeds Lambda's timeout.

The GET endpoint (`/storage/flexcache/flexcaches`) returns immediately with existing cache metadata — no long-running operation involved.

### Fix Applied

1. **Added `return_timeout=0`** to the POST URL: `/storage/flexcache/flexcaches?return_timeout=0`
   - This tells ONTAP to return immediately with a `202 Accepted` + job UUID
   - The actual FlexCache creation proceeds asynchronously

2. **Increased Lambda timeout** from 60s to 120s in `amplify/backend.ts`
   - Safety margin for other operations that may take longer

3. **Added detailed logging** to `_create_flexcache` and `_ontap_request`
   - HTTP status code and error messages now logged to CloudWatch

### ONTAP REST API: Synchronous vs Asynchronous

| Parameter | Behavior |
|-----------|----------|
| (default) | ONTAP holds connection until operation completes (can exceed Lambda timeout) |
| `return_timeout=0` | ONTAP returns immediately with 202 + job UUID |
| `return_timeout=N` | ONTAP waits up to N seconds, then returns job UUID if not complete |

### How "User is not authorized" Appears from a Timeout

When Lambda times out (60s), AppSync receives no response and may synthesize a generic error. The Amplify client interprets certain AppSync error patterns as "User is not authorized." This is a misleading error message caused by the timeout, not by actual authorization failure.

---

## CONFIRMED: ONTAP REST API `/storage/flexcache/flexcaches` Returns 401 for `fsxadmin`

**UPDATE: This was WRONG.** The 401 was caused by fsxadmin password mismatch/lockout, NOT by an API restriction. See corrected analysis below.

### Corrected Root Cause: Password Mismatch / Account Lockout

The `fsxadmin` user has FULL access to all ONTAP REST API endpoints including:
- `/storage/flexcache/flexcaches` (GET, POST, DELETE)
- `/snapmirror/relationships` (GET, POST, PATCH, DELETE)
- All other cluster-scope APIs

The 401 error was caused by:
1. **Password mismatch**: The password in Secrets Manager did not match the actual `fsxadmin` password on the FSx for ONTAP filesystem
2. **Account lockout**: Multiple failed authentication attempts (from earlier timeout debugging) triggered ONTAP's account lockout mechanism

### Resolution

```bash
# 1. Reset fsxadmin password via AWS FSx API
aws fsx update-file-system \
  --file-system-id fs-XXXXX \
  --ontap-configuration '{"FsxAdminPassword":"NewSecurePassword"}' \
  --region ap-northeast-1

# 2. Update Secrets Manager to match
aws secretsmanager put-secret-value \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"NewSecurePassword"}' \
  --region ap-northeast-1
```

### Evidence: Working after password reset
- FlexCache list: ✅ `1 FlexCache volumes` (cachevol01 displayed)
- FlexCache create: ✅ `fc_e2e_test` accepted (202 + job UUID)
- SnapMirror list: ✅ `1 レプリケーション関係` (svm_shift:ds_migtoaws → fsxsvm01:ds_migtoaws_bk)

### Lesson Learned

Never assume an API endpoint is "restricted" when getting 401. Always verify:
1. Is the password correct? (check Secrets Manager vs actual)
2. Is the account locked? (ONTAP locks after N failed attempts)
3. Are you connecting to the right endpoint? (filesystem mgmt IP vs SVM mgmt LIF)

---

## UI Improvements Identified During Debugging

### 1. Error Message Clarity
**Problem**: ONTAP 401 errors display as generic "User is not authorized" — same wording as AppSync auth failures, causing confusion.
**Fix**: Prefix ONTAP errors with the HTTP status and endpoint: `"ONTAP 401: /storage/flexcache/... — check fsxadmin credentials"`

### 2. FlexCache Job Status Tracking
**Problem**: After successful creation (202 Accepted), the UI says "building in background" but provides no way to check job progress.
**Fix**: Store the job UUID and add a "Check Status" button that polls `/cluster/jobs/{uuid}`

### 3. Auto-Refresh After Mutation
**Problem**: After create/delete, user must manually navigate away and back to see updated list.
**Fix**: Automatically refresh the list 5-10 seconds after successful creation

### 4. Connection Health Indicator
**Problem**: When ONTAP credentials are wrong, ALL operations fail silently or with confusing errors.
**Fix**: Add a connection health check on panel load (hit `/api/cluster` endpoint, show green/red indicator)

### 5. Destructive Action Safeguards
**Problem**: Delete button uses `window.confirm()` — no visual distinction from other actions.
**Fix**: Use an inline confirmation UI with red styling, require typing the volume name for deletion

### 6. SnapMirror State Display
**Problem**: State `broken_off` shown as raw string — users don't know what it means.
**Fix**: Map states to human-readable labels with color indicators (green=snapmirrored, yellow=transferring, red=broken_off)
