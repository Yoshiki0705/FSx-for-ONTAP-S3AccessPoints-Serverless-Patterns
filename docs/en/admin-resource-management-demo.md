# Admin Resource Management — Demo Guide

🌐 **Language / 言語**: [日本語](../ja/admin-resource-management-demo.md) | English

**English** | [日本語](../ja/admin-resource-management-demo.md)

> E2E verified on 2026-07-26 against FSx for ONTAP (fs-0123456789abcdef1, ONTAP 9.17.1)

## Overview

The **Admin > Resources** section provides ONTAP System Manager-equivalent storage administration through the File Portal web UI. All operations execute via ONTAP REST API through VPC-internal Lambda functions.

**Architecture**: Browser → AppSync (Cognito auth) → Lambda (VPC) → ONTAP REST API (management LIF)

## Prerequisites

| Item | Value |
|------|-------|
| Cognito Group | `storage-admin` (required for all admin operations) |
| Lambda VPC | Same VPC as FSx for ONTAP file system |
| Secret | `fsx-ontap-fsxadmin-credentials` (username/password JSON) |
| ONTAP Version | 9.13.1+ (ARP/AI requires 9.16+) |

## Quick Start (Deploy)

```bash
cd solutions/amplify-portal

# 1. Copy and edit configuration (gitignored — safe to commit)
cp amplify/portal-config.example.ts amplify/portal-config.ts
# Edit portal-config.ts with your values:
#   ontapMgmtIp, ontapSecretName, ontapSvmName, ontapVolumeName
#   vpcId, vpcSubnetIds, vpcSecurityGroupIds

# 2. Start both backend + frontend in one command
npm start
# Or manually in separate terminals:
#   Terminal 1: npx ampx sandbox
#   Terminal 2: npm run dev
```

### Discover Your Values

```bash
# Get FS management IP and VPC info
FS_ID="fs-xxxxxxxxxxxxxxxxx"
aws fsx describe-file-systems --file-system-ids $FS_ID \
  --query "FileSystems[0].{VpcId:VpcId,SubnetIds:SubnetIds,MgmtIP:OntapConfiguration.Endpoints.Management.IpAddresses[0]}"

# Get Security Group from FSx ENIs
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*FSx*${FS_ID}*" \
  --query "NetworkInterfaces[0].Groups[0].GroupId" --output text

# Get SVM name
aws fsx describe-storage-virtual-machines \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query "StorageVirtualMachines[].Name" --output text
```

## Panel Descriptions

### Storage Category

| Panel | Description | ONTAP REST Endpoint |
|-------|-------------|---------------------|
| **Volumes** | Create, resize, delete volumes with capacity visualization | `/storage/volumes` |
| **FlexClone** | Instant zero-copy volume clones: create, list, split | `/storage/volumes` (clone fields) |
| **Qtrees** | Manage directory structures within volumes | `/storage/qtrees` |
| **Quotas** | User/tree/group space and file limits | `/storage/quota/rules`, `/storage/quota/reports` |
| **Storage Efficiency** | Deduplication, compression, savings ratio dashboard | `/storage/volumes?fields=efficiency,space` |

### Access Control Category

| Panel | Description | ONTAP REST Endpoint |
|-------|-------------|---------------------|
| **Export Policies** | NFS access rules (clients, ro/rw, superuser) | `/protocols/nfs/export-policies` |
| **SMB Shares** | CIFS/SMB shared folder management | `/protocols/cifs/shares` |
| **Local Users** | SMB local users/groups: create, list, delete, membership | `/protocols/cifs/local-users`, `/protocols/cifs/local-groups` |
| **Name Mapping** | Windows↔UNIX/S3 user name translation rules | `/name-services/name-mappings` |
| **QoS Policies** | Fixed (max IOPS/MBps) and Adaptive (expected/peak) | `/storage/qos/policies` |

### Data Protection Category

| Panel | Description | ONTAP REST Endpoint |
|-------|-------------|---------------------|
| **ARP/AI Protection** | Ransomware protection state per volume, bulk enable | `/storage/volumes?fields=anti_ransomware` |
| **Snapshot Management** | Policies, schedules, tamperproof locking | `/storage/snapshot-policies`, `/storage/volumes/{id}/snapshots` |
| **SnapLock** | WORM retention configuration (Compliance/Enterprise) | `/storage/volumes?fields=snaplock` |
| **FPolicy** | File access event notification and audit configuration | `/protocols/fpolicy` |
| **Vscan** | On-access virus scanning setup + vendor guidance | `/protocols/vscan` |
| **SnapMirror** | Replication lifecycle: sync, break, resync, quiesce, delete + transfer history | `/snapmirror/relationships`, `/snapmirror/relationships/{id}/transfers` |
| **FlexCache** | Cache volumes: create (async), list, delete (3-step auto), switch write mode, with origin visualization | `/storage/flexcache/flexcaches` |

## Demo Scenarios

### Scenario 1: Volume Lifecycle

1. Navigate to **Admin > Resources > Volumes**
2. Click **+ Create Volume** → name: `demo_vol_01`, size: 50 GiB, style: UNIX
3. Observe the new volume in the table with 0% capacity bar
4. Click **↔** (resize) → enter 100 GiB → confirm
5. Click **✕** (delete) → confirm deletion

### Scenario 2: ARP/AI Bulk Enable

1. Navigate to **Admin > Resources > ARP/AI Protection**
2. Observe summary cards: Enabled/Learning/Disabled counts
3. Click **Bulk Enable** → select "ARP/AI (no learning period)"
4. Confirm → all disabled volumes transition to "enabled"
5. Verify summary updates to show all volumes protected

### Scenario 3: Storage Efficiency Dashboard

1. Navigate to **Admin > Resources > Storage Efficiency**
2. Observe overall ratio (e.g., 1.21x) and savings percentage (17.7%)
3. Review per-volume dedup/compression status in the table
4. Identify volumes without efficiency features enabled

### Scenario 4: Snapshot Tamperproof Locking

> ⚠️ **Irreversible operation**: Enabling snapshot locking on a volume cannot be undone. Once a snapshot is locked with a retention period, the period can only be extended — never shortened. Verify your organization's retention policy before proceeding.

1. Navigate to **Admin > Resources > Snapshot Management**
2. Switch to **Tamperproof** tab
3. Enter a volume UUID → click **Check Status**
4. If locking is disabled, click **Enable Snapshot Locking**
5. Navigate to **Data Protection > Snapshots** → click **🔒 Lock** on a snapshot
6. Set retention days (e.g., 30) → confirm → snapshot becomes immutable

### Scenario 5: ARP/AI Incident Response

1. Navigate to **Data Protection > ARP/AI**
2. If threat detected (attackProbability ≠ "none"), observe threat assessment banner
3. In the **Incident Response** section:
   - Enter domain + username → click **🛡️ Contain Threat**
   - This creates a snapshot, blocks the SMB user, and disconnects sessions
4. Switch to **Active Blocks** tab to view current blocks
5. Click **Unblock** to remove isolation after investigation

### Scenario 6: SMB Share Encryption Management

1. Navigate to **Admin > Resources > SMB Shares**
2. Observe the encryption info message explaining KMS at-rest vs SMB in-transit
3. Expand **ℹ️ CA 共有 (Continuously Available) とは？** for Hyper-V/SQL Server explanation
4. For a share showing "— 任意" (encryption off), click **ON** → encryption toggles on
5. Click **OFF** to disable → observe state returns to "— 任意"
6. Click **共有削除** → natural language confirm: 「testshare01」を本当に削除しますか？

### Scenario 7: Export Policy Create/Delete

1. Navigate to **Admin > Resources > Export Policies**
2. Click **+ ポリシー作成** → enter name `demo_readonly_policy` → Create
3. Observe the new policy appears with 0 rules
4. Click **ルール表示** → add a rule (client: 10.0.0.0/16, RO: sys, RW: none)
5. Click **← 一覧に戻る** → click **✕** next to `demo_readonly_policy` → confirm delete

### Scenario 8: Lock Panel Inline Management

1. Navigate to **Data Protection > Lock**
2. **SnapLock tab**: Observe inline volume list (empty if no SnapLock volumes exist)
3. **S3 Object Lock tab**: Confirm this tab renders without ONTAP connection errors
4. **Tamperproof tab**: If snapshot locking is enabled, observe inline lock form with:
   - Snapshot selector dropdown (unlocked snapshots)
   - Retention period dropdown (1 day → 5 years)
   - Lock button

### Scenario 9: VolumeSelector Search (Large-Scale Filtering)

1. Navigate to **Admin > Resources > Qtrees**
2. Observe the VolumeSelector with search input at the top
3. Type a partial volume name (e.g., "cache") in the search field
4. After 300ms debounce, dropdown filters to matching volumes only
5. Select a volume → qtrees for that volume are loaded

### Scenario 10: FlexClone — Instant Volume Copy

1. Navigate to **Admin > Resources > FlexClone**
2. Observe existing clones (if any) with parent volume and split status
3. Click **+ Create Clone** → fill:
   - Clone Name: `clone_dev_test`
   - Parent Volume: `vol_production`
   - Snapshot (optional): leave empty for current state, or enter a snapshot name
4. Click **Create** → observe new clone appears instantly (metadata-only copy)
5. Click **Split** on the clone → confirm → split initiates (background process)
6. Observe split progress percentage updating

> **Note**: FlexClone shares the parent volume's throughput budget. Use for dev/test or forensics, not as a permanent parallel workload.

### Scenario 11: Vscan — Antivirus Setup Guidance (DemoMode)

1. Navigate to **Admin > Resources > Vscan**
2. Since Vscan is not configured, the 5-step setup guidance displays:
   - **Step 1**: Vendor selection table (6 vendors with license links)
   - **Step 2**: NetApp Antivirus Connector download button
   - **Step 3**: EC2 architecture diagram + AWS Blog/GitHub links
   - **Step 4**: ONTAP CLI commands (scanner-pool, policy, enable)
   - **Step 5**: Return to this panel to verify
3. Click vendor links → verify they open correct external pages
4. Click the Antivirus Connector download button → verify it opens mysupport.netapp.com
5. After configuring Vscan (production), this panel shows on-access policy details

### Scenario 12: SnapMirror — Replication Lifecycle Management

> ⚠️ **Destructive operations**: The Break action severs the replication relationship. After breaking, the destination volume becomes writable but re-sync requires delta transfer and overwrites destination changes. The Resync action discards all changes on the destination. Both require explicit confirmation in the UI.

1. Navigate to **Admin > Resources > SnapMirror**
2. Observe replication relationships displayed as source→destination cards:
   - Source path badge: `📦 svm01:vol_production`
   - Arrow: `→`
   - Destination path badge: `🪞 svm01_dr:vol_production_mirror`
3. Each relationship shows:
   - **Health badge**: 正常 (green) / 異常 (red)
   - **State badge** with color coding:
     - ✅ 同期中 (snapmirrored) — green
     - 🔴 ブレーク済み (broken_off) — red
     - 🔄 転送中 (transferring) — blue
     - ⏸️ 一時停止 (quiesced/paused) — gray
     - ⚪ 未初期化 (uninitialized) — white
   - **Lag time** with RPO warning: if lag contains "hour" or "day", shows `⚠️ RPO` in red bold
   - **Policy**: e.g., MirrorAllSnapshots, Asynchronous
4. **Action buttons** (context-sensitive per state):
   - `snapmirrored` state: [🔄 同期] [⏸️ 一時停止] [⚡ ブレーク] [🗑️ 削除]
   - `broken_off` state: [🔁 再同期] [🗑️ 削除]
   - `paused` state: [▶️ 再開] [🗑️ 削除]
5. Click **🔄 同期** → confirm dialog → manual transfer initiates
6. Click **⚡ ブレーク** → confirm (warns: "フェイルオーバーに使用します") → destination becomes writable
7. Click **🔁 再同期** → confirm (warns: "宛先の変更は破棄されます") → relationship resumes
8. Click **▶ 転送履歴** on a relationship → expand transfer history table:
   - Columns: 状態 (success/failed badge), サイズ (formatted bytes), 完了日時, 所要時間, 操作
   - Shows last 10 transfers
   - A transfer still running (transferring / queued / preparing / finalizing) offers **⏹ Abort transfer**. Aborting re-sends the delta on the next update rather than losing it
9. Click **▼** to collapse transfer details

> **RPO monitoring**: If lag time exceeds your RPO target (e.g., "2 hours"), the red `⚠️ RPO` warning indicates replication is behind schedule. Trigger a manual sync or investigate network/load issues.

> **DR failover workflow**: Break → promote destination as primary → redirect client access → after recovery, resync to original source.

### Scenario 13: Local Users — SMB User/Group Management

1. Navigate to **Admin > Resources > Local Users**
2. **Users tab**:
   - View list of SMB local users (name, full name, disabled status)
   - Click **+ Create User** → fill name, password (must meet complexity requirements), full name
   - Click Create → user appears in list
   - Click **Delete** → confirm → user removed
3. **Groups tab**:
   - View list of local groups with member count
   - Click a group card → expand to see members
   - Click **+ Add Member** → select user → add
   - Click **Remove** next to a member → confirm removal
   - Click **+ Create Group** → enter name → create

### Scenario 14: Name Mapping — Identity Translation Rules

1. Navigate to **Admin > Resources > Name Mapping**
2. Observe existing rules (direction, index, pattern, replacement)
3. Click **+ Create** → fill:
   - Direction: `Windows → UNIX` (from dropdown: win_unix / unix_win / s3_unix / s3_win)
   - Index: 1 (priority order)
   - Pattern: `DOMAIN\\(.+)` (regex)
   - Replacement: `\1` (extract username from domain prefix)
4. Click Create → new rule appears in the table
5. Click **Delete** on a rule → confirm deletion
6. Test deny mapping: create with replacement = `" "` (space) to block a specific user

> **Security context**: Name mapping deny (`" "` replacement) blocks SMB access on UNIX/MIXED security style volumes. NTFS volumes use Windows ACLs directly and are not affected.

### Scenario 15: FlexCache — Create, Monitor, Delete

1. Navigate to **Admin > Resources > FlexCache** (⚡ icon in Storage category)
2. If no FlexCache volumes exist, observe the guidance panel:
   - Explanation of what FlexCache does (caching a remote volume: reads are accelerated, and writes are served in either of two modes)
   - Typical use cases (EDA/CAD, build pipelines, AI inference data)
   - Links to NetApp FlexCache docs and AWS FSx for ONTAP volume management
3. Click **+ FlexCache 作成** → the creation form opens with:
   - **キャッシュ名** (required): e.g., `flexcache_eda_tokyo`
   - **オリジンボリューム名** (required): datalist dropdown of existing volumes
   - **オリジン SVM** (optional): leave empty for same-SVM caching
   - **サイズ (GiB)**: default 100, hint says "10% of origin recommended"
   - **ジャンクションパス**: auto-fills as `/<cache_name>`
   - **プリポピュレートパス**: comma-separated paths to pre-warm (e.g., `/data/models/, /cache/datasets/`)
4. Fill the form → click **作成**:
   - Button shows spinner + "作成中..." during async request
   - Success toast: "FlexCache を作成しました（バックグラウンドで構築中）"
   - Progressive refresh at 10s / 30s / 60s (ONTAP FlexCache creation takes 30-120s)
5. After refresh, the new FlexCache appears in the list showing:
   - Origin→Cache arrow visualization: `📦 vol_production@svm01 → ⚡ flexcache_eda_tokyo@svm01`
   - Size and junction path
   - Global File Locking badge (if enabled)
   - Cache metrics reference note
6. Click **▶ Origins** → expand origin details table (cluster, SVM, volume, state)
7. To delete: click **削除** → inline confirmation appears: "本当に削除？ [実行] [取消]"
   - Deletion executes 3-step automation: unmount → offline → delete
   - Success toast confirms removal

> **Note**: FlexCache shares the parent volume's throughput budget. Recommended cache size is 10-20% of origin. Use for read-heavy workloads (EDA/CAD, build pipelines, AI inference) — not as a write target.

> **Multi-FS indicator**: The panel header shows which FSx for ONTAP management IP the operations target, useful when multiple file systems are accessible.

### Scenario 16: FPolicy — File Access Audit Configuration

1. Navigate to **Admin > Resources > FPolicy**
2. **Policies tab**: View policies with enabled/disabled state, priority, engine, events
3. **Events tab**: View configured events (protocol, monitored operations: open/close/read/write/delete/rename)
4. **Status tab**: View external engine connection state (connected/disconnected)
5. Verify the 3-tab structure renders without errors in DemoMode (empty lists displayed)

### Scenario 17: Athena SQL — NAS Data Analytics

1. Navigate to **AI & Processing > Analytics** (sidebar: 📊 分析)
2. Observe the guidance panel explaining what Athena does and how it relates to Glue Crawler + S3 AP
3. Click **🗂️ Browse data catalog** to inspect the Glue databases, tables and columns
4. Choose a table and click **Query this table** — the database and a starter query are filled in
5. Click **📝 クエリ例を見る** to expand example queries
6. Click **クエリ実行** to run the query
7. Observe results rendered as a table with column headers and row count

> **Prerequisites for Athena**: A Glue Crawler must have been configured to catalog files from the S3 AP. Without a Glue table, the catalog browser is empty and says so. The portal's Athena panel is a query interface — it does not create Glue Crawlers or tables.

**What this panel enables**: Rather than opening the AWS Athena console separately, storage administrators and data engineers can run SQL queries directly from the portal. Typical use cases:
- "Which files are larger than 1 GB?" (capacity planning)
- "What was modified in the last 7 days?" (change tracking)
- "How much data is in the engineering/ folder?" (project sizing)

## Architecture Notes

### CloudFormation Template Size Optimization

The portal uses a **generic dispatch pattern** to keep the CloudFormation template under 1MB:

```
57 individual GraphQL operations → 8 generic dispatch endpoints
```

| Endpoint | Data Source | Operations |
|----------|------------|------------|
| `adminQuery` / `adminMutation` | ResourceMgmtLambda | 48 admin operations |
| `arpQuery` / `arpMutation` | ArpResponseLambda | 7 ARP operations |
| `protectionQuery` / `protectionMutation` | ListSnapshotsLambda | 9 protection operations |
| `fileQuery` / `fileMutation` | ListFilesLambda | 6 file operations |

Each dispatch resolver routes by `action` parameter to the Lambda handler's existing action-based routing.

### VPC Split Architecture

| Lambda Type | VPC | Purpose |
|-------------|-----|---------|
| ListFiles, GetPresignedUrl, SearchFiles | **No VPC** | Internet-origin S3 AP access |
| ResourceMgmt, ArpResponse, ListSnapshots | **VPC** | ONTAP management LIF (TCP/443) |
| AskAboutFile, DetectLabels, Textract, Comprehend | **No VPC** | AWS AI services |

### IaC Configuration

All VPC/ONTAP settings are in `amplify/portal-config.ts`:

```typescript
export const config: PortalConfig = {
  // ... S3 AP settings ...
  vpcId: process.env.AMPLIFY_PORTAL_VPC_ID || "",
  vpcSubnetIds: (process.env.AMPLIFY_PORTAL_VPC_SUBNET_IDS || "").split(",").filter(Boolean),
  vpcSecurityGroupIds: (process.env.AMPLIFY_PORTAL_VPC_SG_IDS || "").split(",").filter(Boolean),
  // Required whenever vpcId is set — see below.
  vpcRouteTableIds: (process.env.AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS || "").split(",").filter(Boolean),
};
```

When `vpcId` is empty, Lambda deploys without VPC (admin panels show "ONTAP Connection Required" gracefully).

#### `vpcRouteTableIds` is required when using a VPC

Set this to the route tables associated with your Lambda subnets. It creates a DynamoDB gateway endpoint, which the VPC functions need to reach the containment block ledger. **Synth refuses to run without it** when `vpcId` is set, so this is not something you can leave for later.

`portal-config.ts` is gitignored and copied from `portal-config.example.ts`, which takes plain values. The `AMPLIFY_PORTAL_*` environment variables shown above are how the reference configuration reads them — they only apply if your own `portal-config.ts` wires them up the same way. Setting the field directly always works.

A Lambda ENI has no public IP, so a subnet whose default route is an internet gateway gives the function no egress at all. Interface endpoints cover Secrets Manager; DynamoDB has no path unless one is added. Gateway endpoints carry no hourly or data processing charge.

**What happens if you leave it unset**: containment still works, but nothing expires. Blocks are placed on the cluster and the scheduled sweep never sees them, because the ledger write fails. The response reports `expiryTracked: false` rather than pretending the block will lift itself, so the condition is visible — but only to someone reading the response.

Find the route tables for your subnets with:

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<your-subnet-id>" \
  --query "RouteTables[].RouteTableId" --output text
```

If a subnet has no explicit association, it uses the VPC main route table:

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<your-vpc-id>" "Name=association.main,Values=true" \
  --query "RouteTables[].RouteTableId" --output text
```

## Verified Results (2026-07-26)

| Panel | Status | Notes |
|-------|--------|-------|
| Volumes | ✅ | 9 volumes listed (clone01, cachevol01, ds_migtoaws_bk, ...) |
| Export Policies | ✅ | 2 policies (default, fsx-root-volume-policy), create/delete working |
| QoS Policies | ✅ | API works, no policies configured (empty state displayed) |
| SMB Shares | ✅ | 4 shares (c$, cachevol01, ipc$, testshare01), encryption toggle working |
| Storage Efficiency | ✅ | 1.21x ratio, 17.7% savings across 9 volumes |
| Snapshot Admin | ✅ | Policies listed, tamperproof status queryable |
| ARP/AI Admin | ✅ | 9 volumes listed, all disabled, bulk enable ready |
| SnapLock | ✅ | All volumes non_snaplock (no WORM configured) |
| Qtrees | ✅ | VolumeSelector with search filter, auto-select first |
| Quotas | ✅ | VolumeSelector integration, quota rules listed |
| Lock Panel | ✅ | 3 tabs: SnapLock (inline volume list), S3 Object Lock (ONTAP-independent), Tamperproof (inline lock form) |
| Snapshots (Data Protection) | ✅ | hourly/weekly/daily snapshots displayed with lock buttons |
| ARP/AI Status | ✅ | vol1 state: disabled, response actions available |
| FlexCache | ✅ | Create/list/delete E2E verified, 3-step delete (unmount→offline→delete), progressive refresh |
| SnapMirror | ✅ | List with state badges, action buttons (sync/break/resync/quiesce/resume/delete), transfer history |
| File Explorer | ✅ | 29 directories from S3 AP (ai-outputs, contracts, dicom, ...) |

## Screenshots

| File | Description |
|------|-------------|
| `docs/screenshots/file-explorer-directories.png` | File Explorer showing directories from FSx for ONTAP S3 AP |
| `docs/screenshots/resource-management-overview.png` | Resource Management card grid (Storage/Access/Protection/AI categories, full page) |
| `docs/screenshots/volumes-panel.png` | Volume Manager with live ONTAP data: volume style (FlexVol / FlexGroup), the capacity split into live data, snapshots and spill past the reserve, and the rebalance action on FlexGroup rows |
| `docs/screenshots/volume-rebalance-panel.png` | FlexGroup capacity rebalance: state, imbalance for the volume and for the worst constituent, per-constituent usage, and the runtime bounded at 30 minutes |
| `docs/screenshots/storage-efficiency-panel.png` | Storage Efficiency dashboard |
| `docs/screenshots/08-arp-admin-panel-en.png` | ARP/AI Administration with 9 volumes |
| `docs/screenshots/snapshots-version-history.png` | Snapshot Version History with hourly/weekly/daily, the SVM-to-volume scope bar, and the note on how snapshots hold capacity |
| `docs/screenshots/snapshot-lock-confirm.png` | Snapshot lock confirmation dialog (retention input, and that the action cannot be undone) |
| `docs/screenshots/quota-manager.png` | Quota Manager with volume selector and rule table |
| `docs/screenshots/quota-create-form.png` | Quota creation form (type, target, limits) |
| `solutions/amplify-portal/docs/screenshots/smb-shares-panel.png` | SMB Shares with encryption toggle + CA info + delete button |
| `solutions/amplify-portal/docs/screenshots/export-policy-panel.png` | Export Policy with create/delete policy actions |
| `solutions/amplify-portal/docs/screenshots/lock-panel-snaplock.png` | Lock panel SnapLock tab (inline volume list) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-tamperproof.png` | Lock panel Tamperproof tab (inline lock form) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock.png` | Lock panel S3 Object Lock tab (ONTAP-independent) |
| `solutions/amplify-portal/docs/screenshots/qtree-volume-selector.png` | Qtree panel with VolumeSelector search/filter |
| `docs/screenshots/vscan-setup-guidance.png` | Vscan 5-step setup guidance with 6-vendor comparison table |
| `docs/screenshots/flexclone-manager.png` | FlexClone panel with clone list and create form, plus the guidance on when to split and what a clone costs the parent |
| `docs/screenshots/snapmirror-status.png` | SnapMirror relationships with state badges, RPO warning, action buttons |
| `docs/screenshots/snapmirror-create-form.png` | SnapMirror create form (SVM peer selection, prerequisites, preview of the relationship that will be created) |
| `docs/screenshots/local-user-manager.png` | Local User Manager (Users tab with CRUD operations) |
| `docs/screenshots/name-mapping-manager.png` | Name Mapping rules with direction selector and create form |
| `docs/screenshots/flexcache-manager.png` | FlexCache panel with create form (origin datalist, prepopulate paths) and cache list |
| `docs/screenshots/flexcache-create-success.png` | FlexCache creation success toast + progressive refresh indicator |
| `docs/screenshots/flexcache-delete-confirm.png` | FlexCache inline delete confirmation ("本当に削除？ [実行] [取消]") |
| `docs/screenshots/snapmirror-transfers.png` | SnapMirror transfer history expansion (success/failed, size, duration) |
| `docs/screenshots/athena-query-panel.png` | Athena SQL panel with guidance text and SHOW TABLES default |
| `docs/screenshots/athena-query-panel-expanded.png` | Athena SQL panel with example queries expanded |
| `solutions/amplify-portal/docs/screenshots/storage-dashboard.png` | Storage Health Dashboard (4-card grid: capacity, ARP, locks, efficiency) |
| `solutions/amplify-portal/docs/screenshots/ai-processing-ready.png` | AI Processing page (ready, no error) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock-config.png` | S3 Object Lock config form with bucket list |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "ONTAP Connection Required" | Lambda not in VPC | Set `AMPLIFY_PORTAL_VPC_ID/SUBNET_IDS/SG_IDS` |
| "User is not authorized" | fsxadmin password mismatch, **or the account is locked out** (same message; `lockout-duration=0`, so waiting does not clear it — do not retry with the same credential) | Reset via `aws fsx update-file-system --ontap-configuration '{"FsxAdminPassword":"..."}' ` then update Secret |
| "Execution timed out" | VPC Endpoint missing or SG blocking | Ensure Secrets Manager VPC Endpoint exists with port 443 from Lambda SG |
| "Volume not found" | Wrong SVM name | Verify `ONTAP_SVM_NAME` matches `aws fsx describe-storage-virtual-machines` |
| Template > 1MB | Too many resolvers | Already solved via generic dispatch pattern |
| No files in File Explorer | S3 AP alias incorrect | Verify alias in `portal-config.ts` matches `aws fsx describe-storage-virtual-machines --query ...S3AccessPoints` |

## Additional Scenarios

### Scenario 18: Storage Health Dashboard

1. Navigate to **Admin > Resources**
2. Observe the **4 summary cards** at the top of the overview:
   - 💾 Volumes (count + average capacity %)
   - 🛡️ ARP Protected (count + threat indicator)
   - 🔐 Locked Snapshots (tamperproof count)
   - 📊 Storage Efficiency (ratio + savings %)
3. Click any card to navigate directly to that panel
4. If capacity > 85%, the card shows a yellow warning indicator

### Scenario 19: Welcome Onboarding (First-Time User)

1. Clear localStorage: `localStorage.removeItem('portal-welcome-dismissed')`
2. Reload the page — a welcome modal appears with 3 steps
3. Step 1: Browse files (S3 AP access explanation)
4. Step 2: AI Processing (Bedrock/Rekognition/Textract)
5. Step 3: Data Protection (Snapshots/SnapLock/ARP)
6. Click "Get Started" — modal dismisses
7. Check "Don't show again" → modal won't appear on next visit

### Scenario 20: Incident Lifecycle (ARP Containment)

1. Navigate to **Data Protection > ARP/AI**
2. In the **Incident Response** section, observe the state badge:
   - 🔴 検知済み (when threat is detected)
   - 🟠 封じ込め完了 (after containment action)
   - 🟡 調査中 (during investigation)
   - 🟢 解決済み (resolved)
3. Execute **脅威封じ込め** → badge transitions to 「封じ込め完了」
4. Click **→ 調査開始** → badge transitions to 「調査中」
5. Click **→ 解決** → badge transitions to 「解決済み」

### Scenario 21: EMS Events (ONTAP Alerts)

1. Navigate to **Admin > Resources > Cluster**
2. Switch to the **Events** tab
3. Observe recent EMS events: timestamp, severity (alert / error / emergency), message, node name
4. Use for operational awareness: disk failures, aggregate warnings, HA takeover events

> On FSx for ONTAP, `/cluster/nodes` and `/cluster/licensing/licenses` can legitimately return zero records, because AWS manages the cluster layer. An empty list on those tabs is not an error.

### Scenario 22: File Lifecycle (Rename, Trash, Restore)

1. Navigate to **Browse > All Files**
2. Click **✏️** on a file row → edit the name → **Save**
   - A name containing `/` is refused: this renames the file, it does not move it
3. Click **🗑️** on the row → confirm → the file moves under the `.trash/` prefix
   - On the S3 Access Point this copies the object and then deletes the original, so it takes a while for large files
4. Click **🗑️ Trash** in the header → the contents of `.trash/` are listed
5. Click **♻️** → the file returns to its original location
6. Click **🗑️ Leave trash** to return to normal browsing

### Scenario 23: Upload Link (Receiving a File from Outside the Portal)

1. Open the folder the file should land in
2. Click **📤 Upload link**
3. Enter a file name (generated if left empty) and choose an expiry of 1 hour or 24 hours
4. Click **Create link** → the destination key and the URL are shown
5. Copy the URL and hand it to the sender

> **Security note**: The URL is the credential. Until it expires, anyone holding it can write to that key. This is why the UI states the destination key and the expiry next to it.

### Scenario 24: Running a Stored Agent or Team

1. Navigate to **AI & Processing > Agent Directory**
2. Click an agent card → review its tools and system prompt
3. Click **💬 Use in chat** → AI Chat opens running that stored definition
   - The running agent's name is shown as a badge and the mode pills are hidden
4. If you are the creator, **✏️ Edit** appears → change name / description / system prompt / sharing → save
   - Agents shared by other people show neither Edit nor Delete
5. Choosing a team from **Multi-Agent Teams** runs its members and roles as a single supervisor turn
   - An unreachable member does not stop the run; it is named in the response as `unavailableMembers`

### Scenario 25: Document Text Extraction and Analysis

1. Select a file in **Browse > All Files** (the AI panel opens on the right)
2. Click **🔎 Analyze document**
3. Click **Extract text** → review the Amazon Textract result (page count, block count, body text)
   - For documents with no text layer, such as scanned PDFs, running this first is what lets the chat read them
4. Choose an analysis type (entities / sentiment / PII detection / key phrases) and click **Run analysis**
5. Both are refused for files in a regulated folder (`phi/`, `dicom/`, `pii/`, ...)
   - These operations send the bytes to a managed service, which is what the guard is about

### Scenario 26: Aborting a SnapMirror Transfer

1. Navigate to **Admin > Resources > SnapMirror**
2. Expand **▶ 転送履歴** on a relationship with a transfer in progress
3. Rows whose state is transferring / queued / preparing / finalizing offer **⏹ Abort transfer**
4. Click it → confirm (the prompt states that the delta is re-sent on the next update) → the transfer aborts
5. Observe that row's state update

### Scenario 27: Folder Watch and Event Notifications

Prerequisite: enable **Folder Watch** under **Admin > Resources > AI settings** (off by default). Enabling it is the admin stating that FPolicy or Transfer Family is publishing to EventBridge.

1. Open **Browse > Folder Watch** (🔔) in the sidebar
   - With the toggle off, the item does not appear in the sidebar at all
2. Enter the path to watch in **Folder (prefix)**, for example `engineering/cad/`
3. Choose the events (create / modify / delete) and click **Add watch**
   - A trailing slash is appended for you, so a prefix match cannot pull in a sibling folder
4. The watch appears in the table. **Remove** deletes it
5. **Received events** lists events under your registered prefixes, newest first
6. With no events, the three conditions that have to hold are listed (FPolicy enabled, publishing to EventBridge, prefix matching)

> **Security note**: the inbox is filtered first by the Cognito group path boundary (`GROUP_PATH_PREFIXES`), then narrowed by your own watches. A watch is your own record so you may register `/`, but that cannot reveal anything outside the group boundary. `storage-admin` bypasses the boundary. In a single-tenant deployment (no `GROUP_PATH_PREFIXES`) every event is visible, the same boundary as the file listing.

> **Architecture**: FPolicy server (or Transfer Family) -> EventBridge -> notification bridge Lambda -> the `FileNotification` table -> the portal. The portal reads what arrived; it is not what makes ONTAP emit anything. For configuring FPolicy itself see the [event-driven/fpolicy pattern](../../solutions/event-driven/fpolicy/).

## Related Documents

| Document | Contents |
|----------|----------|
| [管理者向けリソース管理 — デモガイド (JA)](../ja/admin-resource-management-demo.md) | Japanese version of this document |
| [PoC to Production Guide](portal-poc-to-production.md) | Moving from DemoMode to a real connection |
| [Scaling Guide](portal-scaling-guide.md) | Capacity planning and throughput sharing |
| [Tamperproof Snapshot Design](../tamperproof-snapshot-design.md) (Japanese) | Three-layer design and the irreversibility rules |
