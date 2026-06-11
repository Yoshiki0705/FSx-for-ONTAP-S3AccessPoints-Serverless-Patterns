# Deployment Timeline

[日本語](deployment-timeline-ja.md) | [English](deployment-timeline-en.md)

Step-by-step guide and estimated time for a partner engineer to build the end-to-end environment.

---

## Prerequisites

- [ ] AWS account (permissions for CloudFormation, FSx, VPN)
- [ ] On-premises NetApp ONTAP 9.8+ running
- [ ] VPN gateway (or router) with public IP on the on-premises side
- [ ] Amazon Quick Professional/Enterprise plan (or 30-day trial)
- [ ] Demo PC (Docker-capable)

---

## Timeline

```
Day -7 ┃ AWS Infrastructure
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [1] Create SSM Parameters              (5 min)
       ┃ [2] Deploy CloudFormation               (30 min)  ← FSx creation takes time
       ┃ [3] Configure Site-to-Site VPN          (1-2 hrs) ← Includes tunnel UP verification
       ┃
Day -5 ┃ SnapMirror Configuration
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [4] Cluster Peering                     (15 min)
       ┃ [5] SVM Peering                         (15 min)
       ┃ [6] Create SnapMirror Relationship      (10 min)
       ┃ [7] SnapMirror Initialize               (hours) ← Depends on data volume
       ┃ [8] Configure Schedule (5-min interval) (5 min)
       ┃
Day -3 ┃ S3 Access Point + Amazon Quick
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [8] Create S3 Access Point              (30 min)
       ┃ [9] Configure IAM Policies              (15 min)
       ┃ [10] Connect Amazon Quick + Index Setup (1 hr)
       ┃ [11] Quick Index Initial Sync           (depends on data volume)
       ┃
Day -1 ┃ Sync Server + Rehearsal
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [12] Configure Sync Server (.env)       (10 min)
       ┃ [13] Start Docker + Verify              (15 min)
       ┃ [14] Run E2E Tests                      (15 min)
       ┃ [15] Full Rehearsal (end-to-end flow)   (30 min)
       ┃ [16] Verify Fallback                    (15 min)
       ┃
Day 0  ┃ Demo Day
───────╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ┃ [17] Equipment Setup + Network Check    (30 min)
       ┃ [18] Verify VPN Connection              (10 min)
       ┃ [19] Start Phone Hotspot                (5 min)
       ┃ [20] Start Sync Server + Health Check   (5 min)
       ┃ [21] Display QR Code + Phone Test       (5 min)
       ┃ [22] Run Test Sync                      (5 min)
       ┃      → Demo begins
```

---

## Step Details

### [1] Create SSM Parameters

```bash
export FSX_ADMIN_PASSWORD='YourSecurePassword123!'
aws ssm put-parameter \
  --name "/snapmirror-demo/fsx-admin-password" \
  --type "SecureString" \
  --value "${FSX_ADMIN_PASSWORD}" \
  --region ap-northeast-1
```

### [2] Deploy CloudFormation

```bash
./infra/deploy.sh
```

Note the following from the output:
- `FsxFileSystemId`
- `FsxManagementEndpoint`
- `VpcId`

### [3] VPN Configuration

1. Download VPN configuration from CloudFormation outputs
2. Apply configuration to the on-premises VPN gateway
3. Verify tunnel status is UP
4. Confirm ping from on-premises to FSx management LIF

### [4-7] SnapMirror Configuration

```bash
# Run guided script (displays commands to execute)
./scripts/setup-snapmirror.sh
```

**Most time is spent on [7] Initialize**:
- 1 GB data → minutes
- 100 GB data → hours (depends on VPN throughput)
- For demo purposes, use a small dataset to complete Initialize quickly

### [8-11] S3 AP + Amazon Quick

```bash
# Run guided script
./scripts/setup-s3-access-point.sh
```

Amazon Quick side:
1. AWS Management Console → Amazon Quick (search "Quick" in the search bar)
2. Quick Index > Data sources > Add > Amazon S3
3. Specify S3 AP alias
4. Sync schedule: On-demand (for demo)

### [12-16] Sync Server + Rehearsal

```bash
# Configure .env
cp .env.example .env
# ONTAP_HOST = FSx management DNS endpoint
# SNAPMIRROR_UUID = UUID obtained in Step 7

# Start
docker compose up -d

# E2E test
./scripts/e2e-test.sh
```

---

## Time Summary

| Phase | Work Time | Wait Time |
|-------|-----------|-----------|
| AWS Infrastructure | 1 hour | FSx creation 30 min |
| VPN | 1-2 hours | Tunnel establishment |
| SnapMirror | 1 hour | Initialize (data-dependent) |
| S3 AP + Quick | 2 hours | Index sync |
| Sync Server | 1 hour | — |
| **Total** | **~6-7 hours** | **+ several hours (Initialize-dependent)** |

**Recommendation**: Start on Day -7 and allow ample preparation time.

---

## Checklist (All items must be ✅ by Day -1)

- [ ] FSx for ONTAP is in `AVAILABLE` state
- [ ] VPN tunnel is `UP`
- [ ] SnapMirror relationship is `snapmirrored` + `Idle`
- [ ] ListObjects / GetObject succeeds via S3 AP
- [ ] Amazon Quick returns search results
- [ ] Sync Server `/api/health` returns `ok`
- [ ] Full flow succeeds: Sync button → sync → searchable in Quick
- [ ] Fallback demo video saved to USB
- [ ] Backup VPN connection via mobile tethering tested
