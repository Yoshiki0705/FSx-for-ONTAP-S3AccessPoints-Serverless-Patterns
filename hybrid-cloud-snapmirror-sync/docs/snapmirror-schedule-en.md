# SnapMirror Schedule and Sync Interval Design

[日本語](snapmirror-schedule-ja.md) | [English](snapmirror-schedule-en.md)

## Where This Tool Fits

SnapMirror has two transfer triggers:

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ① Scheduled (Automatic)                                        │
│     ONTAP automatically executes snapmirror update at set        │
│     intervals → Continuously syncs data in the background        │
│                                                                  │
│  ② Manual Trigger (This Tool = On-demand)                       │
│     POST /api/snapmirror/relationships/{uuid}/transfers          │
│     = CLI equivalent: snapmirror update -destination-path <svm:vol> │
│     → Executes one additional incremental transfer "right now"   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Both are used together**:
- Scheduled = Baseline protection (periodically syncs data during the demo)
- One-click = "Sync right now, immediately after a visitor saves a file"

---

## Configuring SnapMirror Policy and Schedule

### Step 1: Check/Create Schedule

```bash
# SSH into FSx ONTAP CLI
ssh fsxadmin@<FSx_Management_DNS>

# Check existing schedules
job schedule show

# Create a 5-minute interval schedule for demo (if it doesn't exist)
job schedule cron create -name 5min -minute 0,5,10,15,20,25,30,35,40,45,50,55
```

**Common schedule examples**:

| Schedule Name | Interval | Use Case |
|--------------|----------|----------|
| `5min` | 5 min | Demo — reflects data changes frequently |
| `15min` | 15 min | General PoC/testing |
| `hourly` | 1 hour | Built-in schedule |
| `daily` | 1 day | Backup purposes |

### Step 2: Assign Schedule to SnapMirror Policy

```bash
# Method A: Set schedule directly on SnapMirror relationship (recommended)
snapmirror modify -destination-path svm_demo:vol_demo -schedule 5min

# Method B: Create custom policy with schedule
snapmirror policy create -policy demo-sync-policy \
  -type async-mirror \
  -transfer-schedule 5min

# Apply policy to relationship
snapmirror modify -destination-path svm_demo:vol_demo -policy demo-sync-policy
```

### Step 3: Verify

```bash
# Confirm schedule is applied
snapmirror show -destination-path svm_demo:vol_demo -fields schedule,policy

# Expected output:
#                          Schedule  Policy
# svm_demo:vol_demo        5min      MirrorAllSnapshots (or demo-sync-policy)
```

### Setting Schedule via REST API

```bash
# PATCH to add schedule
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"policy": {"name": "MirrorAllSnapshots"}, "transfer_schedule": {"name": "5min"}}'
```

---

## Relationship Between Scheduled and One-Click Triggers

```
Timeline →
──┬────────┬────────┬────────┬────────┬──
  │        │        │        │        │
  ▼        ▼        ▼        ▼        ▼    ← Scheduled update every 5 min (automatic)
  
     ▲              ▲                      ← One-click on-demand (manual)
     │              │
  Visitor saves    Another visitor
  a file           saves a file
```

### Behavior in Each Scenario

| Situation | Behavior |
|-----------|----------|
| One-click between scheduled intervals | Starts incremental transfer immediately (doesn't wait for next schedule) |
| One-click during scheduled transfer | ONTAP returns HTTP 409 → UI shows "Already in progress" |
| Scheduled interval arrives during one-click transfer | Schedule is queued or skipped (controlled by ONTAP) |
| One-click immediately after scheduled completes | Completes instantly if no differences (0 bytes transferred) |

### Typical Demo Scenario Flow

```
1. [Scheduled 5min] ONTAP auto-update → no differences → instant completion
2. Visitor saves a file to the shared folder
3. [One-click] Operator presses button → differential transfer (seconds) → complete
4. Search in Amazon Quick → file found!
5. [Scheduled 5min] ONTAP auto-update → no differences → instant completion
```

---

## Tuning Sync Intervals

### Recommended Settings for Demo Use

| Parameter | Recommended Value | Reason |
|-----------|-------------------|--------|
| SnapMirror schedule | **5 min** | Data reflects within 5 min even if one-click is forgotten |
| One-click timeout | **600 seconds (10 min)** | Usually seconds, but handles large files |
| Polling interval | **2 seconds** | Fast UI response |

### Considerations When Shortening Schedule Interval

| Interval | Advantage | Disadvantage |
|----------|-----------|--------------|
| 1 min | Near real-time (Note: FSx for ONTAP minimum supported interval is 5 min) | Increased ONTAP load, excessive logs |
| 5 min | FSx for ONTAP recommended minimum interval (near real-time) | Syncs within 5 min even without one-click |
| 15 min | Minimal ONTAP load | One-click becomes nearly essential |

**5 minutes is recommended for demos.** Ideal for showing the contrast: "Data syncs on schedule, but one-click syncs it right now."

### Throughput Impact

```
FSx Throughput Capacity (e.g., 128 MBps)
  = NFS/SMB + S3 AP + SnapMirror combined

Scheduled SnapMirror update:
  - No differences → completes in seconds, near-zero throughput consumption
  - With differences (a few MB) → transfers for a few seconds, minimal impact

One-click update:
  - Same as above (transfers only differences)

SnapMirror Initialize (initial sync):
  - Full data transfer → consumes significant throughput
  → Complete Initialize in advance!
```

---

## Changing SnapMirror Schedule

### To Increase Data Freshness During Demo

```bash
# Change to 1-minute interval
job schedule cron create -name 1min -minute */1
snapmirror modify -destination-path svm_demo:vol_demo -schedule 1min
```

### Revert to Normal Interval After Demo

```bash
# Revert to hourly
snapmirror modify -destination-path svm_demo:vol_demo -schedule hourly
```

### Change Schedule via REST API

```bash
# Set to 5-minute interval
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"transfer_schedule": {"name": "5min"}}'

# Disable schedule (one-click only)
curl -k -u fsxadmin:<password> -X PATCH \
  'https://<FSx_Management_DNS>/api/snapmirror/relationships/<UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"transfer_schedule": {"name": ""}}'
```

---

## Troubleshooting

### Sync Completes Instantly with "No Differences"

**Cause**: SnapMirror uses block-level difference detection. Changes are not recognized until the file save (write → close) completes.

**Countermeasure**:
- Instruct visitors to press the button after saving (closing) the file
- For Excel/Word, ask them to explicitly press "Save"

### Scheduled Replication Not Running

```bash
# Verify schedule is correctly configured
snapmirror show -fields schedule
job schedule show -name 5min

# Check last transfer time
snapmirror show -fields last-transfer-end-timestamp
```

### SnapMirror Relationship in `quiesced` State

```bash
# Resume from quiesced state
snapmirror resume -destination-path svm_demo:vol_demo
```

---

## Summary: Demo Day Configuration

```bash
# 1. Verify schedule (5min should be set)
snapmirror show -destination-path svm_demo:vol_demo -fields schedule

# 2. Verify relationship is Idle
snapmirror show -destination-path svm_demo:vol_demo -fields status

# 3. Verify one-click tool is healthy
curl -s http://<Sync_Server>:8080/api/health

# 4. Test execution
curl -s -X POST http://<Sync_Server>:8080/api/sync
```

**Key point**: The scheduled replication (5 min) continuously protects data in the background, while one-click provides the "near real-time sync right after a visitor saves a file" experience. SnapMirror on FSx for ONTAP is volume-level asynchronous replication; Synchronous SnapMirror and SVMDR are not supported.
