# ONTAP REST API Connection Guide — File Portal

🌐 **Language / 言語**: [日本語](ONTAP-CONNECTION-GUIDE.md) | [English](ONTAP-CONNECTION-GUIDE.en.md)

> The connection architecture between the file portal and Amazon FSx for NetApp ONTAP (hereafter FSx for ONTAP), how to troubleshoot it, and the points that matter at deployment time.

## Connection architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Amplify Gen2 Backend (CDK)                                        │
│                                                                    │
│  AppSync → Lambda (VPC 内) → ONTAP REST API (HTTPS/443)          │
│                 │                    │                              │
│                 │                    ├── https://<mgmt-ip>/api/...  │
│                 │                    │   (Basic Auth: fsxadmin)     │
│                 │                    │                              │
│                 ├── Secrets Manager ─┘                              │
│                 │   (fsxadmin credentials)                         │
│                 │                                                    │
│                 └── VPC Endpoint (Secrets Manager)                  │
│                     VPC Endpoint (S3 Gateway)                      │
└──────────────────────────────────────────────────────────────────┘
```

### Which endpoint to connect to (file system vs SVM)

| Endpoint | Scope | User | Purpose |
|-------------|--------|---------|------|
| **File system management IP** | Cluster scope | `fsxadmin` | FlexCache, SnapMirror, Volume, QoS, Export Policy, Snapshot Policy |
| SVM management LIF | SVM scope | `vsadmin` | Operations inside the SVM only (limited) |

**Important**: this portal uses the **file system management IP**. FlexCache and SnapMirror are cluster-scope operations and are not reachable through the SVM management LIF (you get HTTP 401).

### How to look up the IP addresses

```bash
# ファイルシステム管理 IP（本ポータルが使用）
aws fsx describe-file-systems --file-system-ids <fs-id> \
  --query "FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]" \
  --output text

# SVM 管理 LIF IP（本ポータルでは使用しない）
aws fsx describe-storage-virtual-machines \
  --filters "Name=file-system-id,Values=<fs-id>" \
  --query "StorageVirtualMachines[0].Endpoints.Management.IpAddresses[0]" \
  --output text
```

## Managing the secret

### Secret format

```json
{
  "username": "fsxadmin",
  "password": "<fsxadmin-password>"
}
```

### Creating the secret

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_SECURE_PASSWORD"}' \
  --region <your-region>
```

> **Security note**: Secrets Manager encrypts with the AWS managed KMS key (`aws/secretsmanager`) by default. If a regulatory requirement (FISC, PCI DSS, HIPAA and similar) calls for a customer managed key (CMK), pass `--kms-key-id`. To enable automatic rotation, see [AWS documentation: Rotate secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html).

### Changing the password

When you change the FSx for ONTAP `fsxadmin` password, **always update both sides together**:

```bash
# Step 1: FSx for ONTAP 側のパスワード変更
aws fsx update-file-system \
  --file-system-id <fs-id> \
  --ontap-configuration '{"FsxAdminPassword":"NewSecureP@ss2026!"}' \
  --region <your-region>

# Step 2: Secrets Manager の値を同期
aws secretsmanager put-secret-value \
  --secret-id fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"NewSecureP@ss2026!"}' \
  --region <your-region>
```

> **Note**: if the portal makes an API call between Step 1 and Step 2, authentication fails with the old password. ONTAP records authentication failures and may lock the account out once a threshold is exceeded.

## Troubleshooting

### HTTP 401 "User is not authorized"

| Cause | How to check | Action |
|------|---------|------|
| Password mismatch | The value in Secrets Manager differs from the actual FSx password | Sync both sides using "Changing the password" above |
| Account lockout | Many authentication failures (automated tests and similar) exceeded the threshold | Reset the password with `aws fsx update-file-system` → the lock is released |
| Wrong endpoint IP | Connecting to the SVM management LIF as `fsxadmin` | Check the file system management IP with `describe-file-systems` |
| No VPC connectivity | The Lambda cannot reach the ONTAP IP | Check outbound TCP/443 on the security group and the subnet routing |

### Checking in CloudWatch Logs

```bash
# Lambda ログでONTAP API エラーを検索
aws logs filter-log-events \
  --log-group-name "/aws/lambda/<ResourceMgmtFunction名>" \
  --start-time $(( $(date +%s) - 300 ))000 \
  --region <your-region> \
  --query 'events[*].message' --output text \
  | grep -i "ONTAP API error\|401\|flexcache\|snapmirror"
```

### Lambda timeout (over 120s)

FlexCache creation and SnapMirror initialization run as asynchronous jobs on the ONTAP side. With the `return_timeout=0` parameter, ONTAP returns 202 Accepted plus a job UUID immediately, but the first connection to ONTAP (TLS handshake + Basic Auth) takes 4-5 seconds.

Lambda timeout: 120 seconds (set in `backend.ts`). A normal API call completes in 4-8 seconds.

## Notes on FlexCache operations

### Behaviour specific to FSx for ONTAP

- **No aggregate to specify**: FSx for ONTAP uses a single automatically managed aggregate, so the `aggregate_name` parameter can be omitted (the ONTAP REST API selects the default aggregate). On-premises ONTAP may require it explicitly.
- **SVM creation is AWS API only**: an SVM cannot be created from the ONTAP CLI or REST API. Use `aws fsx create-storage-virtual-machine`.
- **FlexCache can be created within the same cluster**: another volume on the same file system can be the origin, with no cluster peering.

### Creation

```
POST /storage/flexcache/flexcaches?return_timeout=0
```

- Without `return_timeout=0`, ONTAP waits synchronously for completion (30-120 seconds, which causes the Lambda timeout)
- Creation is an asynchronous job. It takes 30 seconds to a few minutes. The portal refreshes the list automatically at 10s/30s/60s intervals

### Deletion (3 steps, all required)

A mounted FlexCache volume cannot be deleted directly:

```
1. PATCH /storage/volumes/{uuid} → {"nas": {"path": ""}}      // unmount
2. PATCH /storage/volumes/{uuid} → {"state": "offline"}       // offline
3. DELETE /storage/flexcache/flexcaches/{uuid}?return_timeout=0  // delete
```

The portal's `_delete_flexcache` automates these three steps.

## Notes on SnapMirror operations

### State transitions

| State | Meaning | Permitted operations |
|------|------|---------------|
| `snapmirrored` | Synchronizing normally | sync, break, quiesce |
| `broken_off` | The DP volume is read-write | resync |
| `transferring` | Transferring data | abort |
| `quiesced` | Synchronization paused | resume, break |

### Initialization (existing relationships)

Creating a SnapMirror relationship normally goes `volume create -type DP` → `snapmirror create` → `snapmirror initialize`, but this portal focuses on **managing existing relationships** (create them initially in the FSx Console or the CLI).

## Behaviour of the Amplify sandbox

### Scope of file change detection

| Directory | Change detected | Lambda code updated |
|------------|:--------:|:--------------:|
| `amplify/` | ✅ automatic | Re-bundled when `backend.ts` changes |
| `functions/` | ⚠️ indirect | Re-bundled only once a file under `amplify/` changes |
| `src/` (frontend) | ✅ Vite HMR | No effect on the Lambda |

**Important**: when you change `functions/resource-management/handler.py`, the sandbox may not detect it automatically. Force the trigger with either of:
1. Change the Lambda `description` in `backend.ts` (this changes the asset hash)
2. Stop the sandbox with Ctrl+C, then restart it

### Why `authMode: "userPool"` is needed

When Amplify Gen2 has multiple authentication providers configured (Cognito User Pools + IAM), failing to pass `authMode` explicitly to `generateClient<Schema>()` means the Cognito ID Token is not sent to AppSync, producing a "User is not authorized" error.

```typescript
// ❌ 動作しない（authMode 未指定）
const client = generateClient<Schema>();

// ✅ 正しい（Cognito token を確実に送信）
const client = generateClient<Schema>({ authMode: "userPool" });
```

## Deploying to a new environment (end to end)

```bash
# 1. リポジトリ取得
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. 依存関係
npm install

# 3. 設定ファイル（FSx for ONTAP の情報を自動取得）
./scripts/setup-prerequisites.sh --fs-id <your-fs-id>
cp amplify/portal-config.example.ts amplify/portal-config.ts
# 出力された値を portal-config.ts に転記

# 4. Secrets Manager にクレデンシャル登録
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-password>"}'

# 5. 起動
npm start

# 6. 初回ユーザー作成（自動で Cognito サインアップ画面が表示される）
# ブラウザで http://localhost:5173 → Create Account
```

## Patterns for using this alongside other SaaS tools

| Situation | Combined approach | Role of the portal |
|-----------|-------------|-------------|
| Using a cloud file sharing SaaS | Keep day-to-day file sharing in the SaaS | AI processing and auditing for large data on NAS (EDA, video, HPC results) |
| Running a self-hosted file sharing service | Just add the S3 AP as External Storage | Browse NAS data directly from the existing UI + admin operations in the portal |
| Using groupware (M365 and similar) | Leave the groupware integration as it is | SnapMirror replication management between on-premises NAS and FSx for ONTAP |
| Using a hybrid file service | Keep using the file service | Visibility into data protection (Tamperproof Snapshot) and ransomware defence (ARP/AI) |

**Design philosophy**: this portal is not a "replacement" for an existing file sharing tool. It is a layer providing **AI processing + data protection visibility + admin operations** over NAS data. Day-to-day file sharing continues in the existing tool, while NAS-specific features (Snapshot, FlexClone, FlexCache, SnapMirror, ARP) become operable from a browser.


## Future Improvements

The items below were identified during review:

### Performance visibility
- **Cache hit ratio display** (EDA/VFX workloads): use the `cache_hit_ratio` field of the ONTAP REST API to show the live hit ratio on a dashboard
- **Throughput / IOPS graphs**: draw on CloudWatch metrics or the ONTAP REST metrics API

### Operational automation
- **RPO alerts**: SNS notification plus a UI warning badge when SnapMirror lag exceeds a threshold (implemented: the UI warning)
- **FlexCache prepopulate**: allow an initial warm-up directory to be specified at creation time
- **Automated secret rotation**: periodic password update via a Lambda rotation function

### UX improvements
- **FlexCache creation wizard**: origin volume dropdown (implemented: datalist), automatic size suggestion (10% of the origin)
- **Inline delete confirmation UI**: window.confirm() → a custom confirmation dialog (ARIA support)
- **Multi file system switching**: define several file systems in portal-config and switch between them in the UI

### Auditing and compliance
- **Operation audit trail**: write every operation to DynamoDB (who / when / what)
- **mTLS support**: make CA verification of the ONTAP self-signed certificate optional

### Accessibility
- **ARIA dialog pattern**: aria-modal + focus trap on confirmation dialogs
- **aria-label on status badges**: screen reader support
