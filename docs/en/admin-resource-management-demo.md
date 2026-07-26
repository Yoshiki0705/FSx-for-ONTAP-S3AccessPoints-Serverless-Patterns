# Admin Resource Management — Demo Guide

> E2E verified on 2026-07-26 against FSx for ONTAP (fs-0123456789abcdef0, ONTAP 9.17.1)

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
| **Qtrees** | Manage directory structures within volumes | `/storage/qtrees` |
| **Quotas** | User/tree/group space and file limits | `/storage/quota/rules`, `/storage/quota/reports` |
| **Storage Efficiency** | Deduplication, compression, savings ratio dashboard | `/storage/volumes?fields=efficiency,space` |

### Access Control Category

| Panel | Description | ONTAP REST Endpoint |
|-------|-------------|---------------------|
| **Export Policies** | NFS access rules (clients, ro/rw, superuser) | `/protocols/nfs/export-policies` |
| **SMB Shares** | CIFS/SMB shared folder management | `/protocols/cifs/shares` |
| **QoS Policies** | Fixed (max IOPS/MBps) and Adaptive (expected/peak) | `/storage/qos/policies` |

### Data Protection Category

| Panel | Description | ONTAP REST Endpoint |
|-------|-------------|---------------------|
| **ARP/AI Protection** | Ransomware protection state per volume, bulk enable | `/storage/volumes?fields=anti_ransomware` |
| **Snapshot Management** | Policies, schedules, tamperproof locking | `/storage/snapshot-policies`, `/storage/volumes/{id}/snapshots` |
| **SnapLock** | WORM retention configuration (Compliance/Enterprise) | `/storage/volumes?fields=snaplock` |

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

## Architecture Notes

### CloudFormation Template Size Optimization

The portal uses a **generic dispatch pattern** to keep the CloudFormation template under 1MB:

```
57 individual GraphQL operations → 8 generic dispatch endpoints
```

| Endpoint | Data Source | Operations |
|----------|------------|------------|
| `adminQuery` / `adminMutation` | ResourceMgmtLambda | 36 admin operations |
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
};
```

When `vpcId` is empty, Lambda deploys without VPC (admin panels show "ONTAP Connection Required" gracefully).

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
| File Explorer | ✅ | 29 directories from S3 AP (ai-outputs, contracts, dicom, ...) |

## Screenshots

| File | Description |
|------|-------------|
| `docs/screenshots/01-file-explorer-with-data.png` | File Explorer showing 29 directories from FSx for ONTAP S3 AP |
| `docs/screenshots/05-resource-management-overview-en.png` | Resource Management card grid (Storage/Access/Protection categories) |
| `docs/screenshots/06-volumes-panel-en.png` | Volume Manager with live ONTAP data |
| `docs/screenshots/07-storage-efficiency-en.png` | Storage Efficiency dashboard (1.21x ratio) |
| `docs/screenshots/08-arp-admin-panel-en.png` | ARP/AI Administration with 9 volumes |
| `docs/screenshots/09-snapshots-version-history-en.png` | Snapshot Version History with hourly/weekly/daily |
| `docs/screenshots/10-file-explorer-directories-en.png` | File Explorer (English) with directory listing |
| `solutions/amplify-portal/docs/screenshots/smb-shares-panel.png` | SMB Shares with encryption toggle + CA info + delete button |
| `solutions/amplify-portal/docs/screenshots/export-policy-panel.png` | Export Policy with create/delete policy actions |
| `solutions/amplify-portal/docs/screenshots/lock-panel-snaplock.png` | Lock panel SnapLock tab (inline volume list) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-tamperproof.png` | Lock panel Tamperproof tab (inline lock form) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock.png` | Lock panel S3 Object Lock tab (ONTAP-independent) |
| `solutions/amplify-portal/docs/screenshots/qtree-volume-selector.png` | Qtree panel with VolumeSelector search/filter |
| `solutions/amplify-portal/docs/screenshots/storage-dashboard.png` | Storage Health Dashboard (4-card grid: capacity, ARP, locks, efficiency) |
| `solutions/amplify-portal/docs/screenshots/ai-processing-ready.png` | AI Processing page (ready, no error) |
| `solutions/amplify-portal/docs/screenshots/lock-panel-s3objectlock-config.png` | S3 Object Lock config form with bucket list |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "ONTAP Connection Required" | Lambda not in VPC | Set `AMPLIFY_PORTAL_VPC_ID/SUBNET_IDS/SG_IDS` |
| "User is not authorized" | fsxadmin password mismatch | Reset via `aws fsx update-file-system --ontap-configuration '{"FsxAdminPassword":"..."}' ` then update Secret |
| "Execution timed out" | VPC Endpoint missing or SG blocking | Ensure Secrets Manager VPC Endpoint exists with port 443 from Lambda SG |
| "Volume not found" | Wrong SVM name | Verify `ONTAP_SVM_NAME` matches `aws fsx describe-storage-virtual-machines` |
| Template > 1MB | Too many resolvers | Already solved via generic dispatch pattern |
| No files in File Explorer | S3 AP alias incorrect | Verify alias in `portal-config.ts` matches `aws fsx describe-storage-virtual-machines --query ...S3AccessPoints` |

## New Feature Scenarios (2026-07-26)

### Scenario 10: Storage Health Dashboard

1. Navigate to **Admin > Resources**
2. Observe the **4 summary cards** at the top of the overview:
   - 💾 Volumes (count + average capacity %)
   - 🛡️ ARP Protected (count + threat indicator)
   - 🔐 Locked Snapshots (tamperproof count)
   - 📊 Storage Efficiency (ratio + savings %)
3. Click any card to navigate directly to that panel
4. If capacity > 85%, the card shows a yellow warning indicator

### Scenario 11: Welcome Onboarding (First-Time User)

1. Clear localStorage: `localStorage.removeItem('portal-welcome-dismissed')`
2. Reload the page — a welcome modal appears with 3 steps
3. Step 1: Browse files (S3 AP access explanation)
4. Step 2: AI Processing (Bedrock/Rekognition/Textract)
5. Step 3: Data Protection (Snapshots/SnapLock/ARP)
6. Click "Get Started" — modal dismisses
7. Check "Don't show again" → modal won't appear on next visit

### Scenario 12: Incident Lifecycle (ARP Containment)

1. Navigate to **Data Protection > ARP/AI**
2. In the **Incident Response** section, observe the state badge:
   - 🔴 検知済み (when threat is detected)
   - 🟠 封じ込め完了 (after containment action)
   - 🟡 調査中 (during investigation)
   - 🟢 解決済み (resolved)
3. Execute **脅威封じ込め** → badge transitions to 「封じ込め完了」
4. Click **→ 調査開始** → badge transitions to 「調査中」
5. Click **→ 解決** → badge transitions to 「解決済み」

### Scenario 13: EMS Events (ONTAP Alerts)

1. Navigate to **Admin > Resources** (StorageDashboard will show summary)
2. EMS events are available via admin API: `getEmsEvents` action
3. Returns: timestamp, severity (alert/error/emergency), message, node name
4. Use for operational awareness: disk failures, aggregate warnings, HA takeover events
