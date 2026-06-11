# Demo Day Operation Guide

[日本語](operation-guide-ja.md) | [English](operation-guide-en.md)

## Demo Flow

```
1. Visitor saves a file to the on-premises ONTAP shared folder
2. Demo operator presses the "Sync" button on smartphone/PC
3. Sync progress is displayed on screen (a few seconds to ~10 seconds)
4. "Sync Complete" is displayed
5. Search and analyze the file in Amazon Quick
```

### SnapMirror Sync Model

This demo combines **scheduled replication + one-click on-demand trigger**:

| Sync Method | Behavior | Purpose |
|-------------|----------|---------|
| **Scheduled (every 5 min)** | ONTAP automatically executes `snapmirror update` | Background protection (continues during demo) |
| **One-click (this tool)** | Button press triggers immediate `snapmirror update` | Demonstrates near real-time sync to visitors |

```
Timeline →
──┬────┬────┬────┬────┬────┬──
  │    │    │    │    │    │    ← Scheduled update every 5 min (automatic, background)
  
        ▲         ▲              ← One-click on-demand trigger (for demo)
        │         │
     File saved   File saved
     Button press Button press
     immediately  immediately
```

**Key point**: Data syncs even with the scheduled replication alone (minimum 5-minute intervals), but pressing the button right after a visitor saves a file demonstrates near real-time data integration. Note that SnapMirror is asynchronous replication, not synchronous replication.

For detailed schedule configuration and tuning, see [docs/snapmirror-schedule-ja.md](../docs/snapmirror-schedule-ja.md).

---

## Smartphone Access

### Challenge: Venue Network Constraints

Event venues commonly have these constraints:
- Attendees can use venue WiFi, but **direct device-to-device communication (same-subnet) is often blocked**
- A dedicated WiFi for the booth may not be available
- Attendee smartphones and the Sync Server PC may be on different network segments

### Connection Options

| Method | Difficulty | Description | Recommended For |
|--------|-----------|-------------|-----------------|
| **A: Mobile Hotspot** | ★☆☆ | Share tethering from PC, connect phone to it | **Most reliable (recommended)** |
| B: Portable Router | ★☆☆ | Bring a portable router to create dedicated WiFi | Multiple operators |
| C: USB Tethering + WiFi Share | ★★☆ | Phone USB tethering → PC becomes WiFi AP | Backup |
| D: Venue WiFi (if lucky) | ★☆☆ | Use directly if device-to-device communication is allowed | Pre-verified venues |

### Method A: Mobile Hotspot (Recommended)

**The Sync Server PC itself acts as a hotspot, and the smartphone connects to it.**
This is the most reliable method as it has no dependency on venue network constraints.

```
[Sync Server PC]
  ├── Acts as WiFi AP (hotspot ON)
  ├── Sync Server (localhost:8080)
  └── AWS VPN (via venue WiFi or mobile connection)

[Operator Smartphone]
  └── Connects to PC's hotspot via WiFi
      → Access http://172.20.10.1:8080
```

#### macOS

1. **System Settings → General → Sharing → Internet Sharing**
2. "Share your connection from": Venue WiFi (or Ethernet)
3. "To computers using": Check Wi-Fi
4. Set network name/password in Wi-Fi Options
5. Turn Internet Sharing ON

```bash
# Check PC hotspot IP
ifconfig bridge0  # Usually 192.168.2.1
# or
ifconfig en0      # WiFi IP
```

Access from smartphone: `http://192.168.2.1:8080`

#### Windows

1. **Settings → Network & Internet → Mobile hotspot**
2. "Share my Internet connection from": WiFi
3. "Share over": Wi-Fi
4. Turn hotspot ON

Access from smartphone: `http://192.168.137.1:8080` (Windows default)

### Method B: Portable Router

Bring a small WiFi router (e.g., GL.iNet GL-MT300N) to the venue:

```
[Portable Router]  ←── Wired or WiFi upstream (not required)
  ├── PC (wired or WiFi)
  └── Smartphone (WiFi)
      → Same-segment communication possible
```

- Router cost: ~$30-50
- Pre-configure SSID/password
- Sync Server access works without upstream internet (AWS VPN uses PC's mobile connection separately)

---

## Pre-Event Checklist

### Day Before

- [ ] SnapMirror relationship verified working
- [ ] Sync Server confirmed starting normally
- [ ] Data sync completion tested
- [ ] Amazon Quick search and display confirmed
- [ ] Demo files prepared (templates for visitors to fill in, etc.)

### Day Of (Venue Setup)

- [ ] On-premises ONTAP powered on and verified
- [ ] VPN / connection between ONTAP and AWS established
- [ ] Sync Server started
- [ ] **Smartphone connection network prepared** (hotspot or portable router)
- [ ] Sync Server IP address confirmed (hotspot IP)
- [ ] Smartphone connected to hotspot WiFi
- [ ] Smartphone can access `http://<IP>:8080`
- [ ] QR code printed or displayed on PC screen
- [ ] Test sync executed to verify operation

---

## Normal Operations

### Screen Layout

- Top: Status display (green = ready to sync)
- Center: Sync button (large orange circle)
- Bottom: Architecture flow

### Executing a Sync

1. Open the sync screen in a browser
2. Confirm green "Ready" status
3. Tap the large orange button
4. Monitor progress (detecting changes → transferring data → complete)
5. Confirm "🎉 Data sync complete!"

### Consecutive Syncs

- After completion, the button re-enables automatically after 10 seconds
- For urgent syncs, press the "Re-sync" button immediately

---

## Common Scenarios and Responses

### Scenario 1: Button pressed twice

**No problem.** The server prevents duplicate execution.
The screen displays "Sync is already in progress."

### Scenario 2: Screen stuck on "Syncing"

**Cause**: Network disconnection or ONTAP-side issue

**Response**:
1. Wait 30 seconds
2. If unchanged, reload the page (F5 / pull-to-refresh)
3. If still not resolved:
   ```
   POST http://<IP>:8080/api/reset
   ```
   Or check connection status:
   ```
   http://<IP>:8080/api/health
   ```

### Scenario 3: "Connection Error" displayed

**Response**:
1. Verify the Sync Server PC is running
2. Check WiFi connection
3. Verify Docker is running:
   ```bash
   docker compose ps
   ```
4. Confirm ping to ONTAP management LIF

### Scenario 4: Sync succeeded but cannot search in Amazon Quick

**Cause**: Amazon Quick data source re-sync needed

**Response**:
1. Open Amazon Quick in the AWS Console
2. Check data source sync schedule
3. Manually trigger data source sync (if needed)

---

## ⚠️ Important Notes

### Throughput Sharing

FSx for ONTAP's 128 MBps throughput capacity is shared across NFS/SMB/S3 AP/SnapMirror.
- **SnapMirror Initialize (initial sync)**: Bulk data transfer. May impact Amazon Quick access performance.
- **SnapMirror Update (incremental = demo one-click)**: Only transfers differences, takes a few seconds. Minimal impact.

### Amazon Quick Index Refresh Lag

After SnapMirror sync completes, there may be a time lag before data is searchable in Amazon Quick:
1. SnapMirror complete → Immediately readable via S3 AP (seconds)
2. S3 AP → Amazon Quick Index refresh → Depends on Quick Index sync schedule

**Demo countermeasures**:
- Set Quick Index data source to On-demand sync, manually trigger after sync completes
- Or talk through: "SnapMirror is complete, now we'll update the Quick index"
- **Measure Quick Index sync latency during Day -1 rehearsal** (target: within 30-60 seconds)

---

## Emergency Response

### Fallback Plans

| Failure | Plan A | Plan B | Plan C (last resort) |
|---------|--------|--------|---------------------|
| VPN down | Retry VPN connection (1 min) | Mobile tethering + WireGuard | Play pre-recorded demo video |
| ONTAP not responding | Restart Sync Server | Run `snapmirror update` directly via ONTAP CLI | Play pre-recorded demo video |
| Quick not searchable | Manual Quick Index sync | Demo with pre-indexed data | — |
| Sync Server down | `docker compose restart` | Reboot PC → Docker auto-starts | Execute directly via ONTAP CLI |

**Preparation**: Save a demo video (~30 seconds) to USB and place on the venue PC.

### Restart Sync Server

```bash
# Docker
docker compose restart

# Direct execution
# Ctrl+C to stop, then restart
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Force State Reset

```bash
curl -X POST http://localhost:8080/api/reset
```

### Manually Update SnapMirror via ONTAP (Emergency)

```bash
# ONTAP CLI (SSH connection)
snapmirror update -destination-path <svm_dst:vol_demo>
```

---

## Cleanup Procedure

Resource deletion procedure after testing. Delete in reverse dependency order.

### Deletion Order (Correct Procedure)

```
1. Delete SnapMirror relationship on Destination (destination_only)
2. Delete SnapMirror source info on Source (source_info_only)
3. Force-delete SVM Peer on both sides
4. Delete Cluster Peer on both sides
5. Delete Volume → SVM → File System via AWS FSx API
```

### Step 1: Delete SnapMirror Relationship

```bash
# Destination side (FSx REST API)
curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Dest_Management_IP>/api/snapmirror/relationships/<UUID>?destination_only=true"

# Source side (delete list-destinations info = snapmirror release equivalent)
curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Source_Management_IP>/api/snapmirror/relationships/<UUID>?source_info_only=true"
# ※ HTTP 404 means no tracking info on Source — this is normal (skip)
```

> ⚠️ `destination_only=true` alone leaves tracking info on Source,
> which blocks subsequent SVM peer deletion. Always execute on Source side too.

### Step 2: Delete SVM Peer

```bash
# Force-delete on both sides (specify force: true in request body)
curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Source_Management_IP>/api/svm/peers/<UUID>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Dest_Management_IP>/api/svm/peers/<UUID>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

> ⚠️ `force` must be passed in the **request body**, not as a query parameter.

### Step 3: Delete Cluster Peer

```bash
curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Source_Management_IP>/api/cluster/peers/<UUID>"

curl -sk -u fsxadmin:<password> -X DELETE \
  "https://<Dest_Management_IP>/api/cluster/peers/<UUID>"
```

### Step 4: Delete AWS Resources

```bash
# Delete volume
aws fsx delete-volume --volume-id <vol-id> \
  --ontap-configuration SkipFinalBackup=true --region ap-northeast-1

# Delete SVM (after volume deletion completes)
aws fsx delete-storage-virtual-machine \
  --storage-virtual-machine-id <svm-id> --region ap-northeast-1

# Delete file system (after SVM deletion completes)
aws fsx delete-file-system --file-system-id <fs-id> --region ap-northeast-1
```

---

## Technical Specifications (For Operators)

| Item | Value |
|------|-------|
| Sync Server port | 8080 |
| Polling interval (idle) | 3 seconds |
| Polling interval (syncing) | 1.5 seconds |
| Max monitoring time | 10 minutes (configurable via `SYNC_TIMEOUT_SECONDS`) |
| Duplicate prevention | 3-layer: Frontend + Backend + ONTAP |
| API auth | Bearer Token (active only when `AUTH_TOKEN` is set) |
| Audit log | `audit.jsonl` (JSON Lines format) |
| API Base Path | `/api/sync`, `/api/status`, `/api/health`, `/api/reset` |
| REST API target | FSx for ONTAP management endpoint (via VPN) |
| HTTPS (Sync Server) | Optional (`--ssl-keyfile`, `--ssl-certfile` to enable) |
