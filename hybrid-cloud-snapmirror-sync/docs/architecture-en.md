# Architecture

[日本語](architecture.md) | [English](architecture-en.md)

## Overall Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Demo Venue (On-Premises Environment)                                       │
│                                                                             │
│  ┌──────────┐     HTTP      ┌──────────────┐                  ┌────────┐    │
│  │Phone/PC  │ ───────────▶  │  Sync Server │                  │ ONTAP  │    │
│  │(Browser) │               │  (Python)    │                  │ (SRC)  │    │
│  └──────────┘               └──────┬───────┘                  └───┬────┘    │
│       ▲                            │                              │         │
│       │ Progress polling            │ ONTAP REST API               │         │
│       └────────────────────────────┘ (HTTPS/443)                  │         │
│                                      │                            │         │
└──────────────────────────────────────│────────────────────────────│─────────┘
                                       │ VPN Tunnel                 │ SnapMirror
                                       ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS Cloud (ap-northeast-1)                                                 │
│                                                                             │
│  ┌──────────────────┐    S3 Access Point    ┌───────────────────────────┐   │
│  │ FSx for ONTAP    │ ──────────────────▶   │ Amazon Quick              │   │
│  │ (DST)            │                       │ (AI search/analysis)      │   │
│  │ ← REST API here  │                       └───────────────────────────┘   │
│  └──────────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Important**: The Sync Server calls the REST API of FSx for ONTAP (Destination side).
Since the Destination cluster owns the SnapMirror XDP relationship, transfer triggers must be issued to the FSx side.
Communication between the Sync Server and FSx goes through a VPN tunnel.

## Component Details

### 1. Frontend (Browser)

- **Technology**: Static HTML + CSS + JavaScript (no framework required)
- **Responsive**: Supports smartphones, tablets, and PCs
- **Communication**: REST API polling (1.5–3 second intervals)
- **Safety**: Immediate button disable + server-side lock

### 2. Sync Server (Backend)

- **Technology**: Python FastAPI
- **Responsibilities**:
  - Frontend serving (static files)
  - ONTAP REST API proxy
  - Sync state management (duplicate execution prevention)
  - Transfer progress monitoring
- **Deployment**: Docker or direct execution

### 3. ONTAP REST API

The Sync Server calls the **FSx for ONTAP (Destination cluster)** REST API.
This is because the Destination side owns the SnapMirror XDP relationship.

Endpoints used:

| API | Method | Purpose |
|-----|--------|---------|
| `/api/snapmirror/relationships/{uuid}` | GET | Get relationship status |
| `/api/snapmirror/relationships/{uuid}/transfers` | GET | Get transfer history |
| `/api/snapmirror/relationships/{uuid}/transfers` | POST | Trigger transfer |

**Target**: FSx for ONTAP management DNS endpoint (`management.fs-xxx.fsx.ap-northeast-1.amazonaws.com`)
**Path**: Sync Server → VPN Tunnel → FSx Management LIF

### 4. SnapMirror

- **Direction**: On-premises ONTAP (Source) → FSx for NetApp ONTAP (Destination)
- **Type**: Asynchronous SnapMirror (XDP)
- **Scheduled**: Automatic incremental transfer every 5 minutes (controlled by ONTAP `job schedule`)
- **One-click on-demand**: Immediate additional transfer via `POST /transfers` from this tool
- **Transfer content**: Block-level differences only (efficiently transfers only changed blocks)

```
┌────────────────────────────────────────────────┐
│  SnapMirror Transfer Triggers                   │
│                                                │
│  [Scheduled]──every 5min──▶ snapmirror update   │
│         +                                      │
│  [One-click]──immediate──▶ snapmirror update   │
│                          (= POST /transfers)   │
│                                                │
│  → Both transfer only block-level differences   │
│  → If on-demand arrives during scheduled run,   │
│    returns 409 and waits                        │
└────────────────────────────────────────────────┘
```

For schedule configuration details, see [docs/snapmirror-schedule-ja.md](../docs/snapmirror-schedule-ja.md).

### 5. FSx for NetApp ONTAP

- **Role**: Data store on the AWS cloud side
- **Connectivity**: Provides read access via S3 Access Points

### 6. Amazon Quick

- **Role**: Leverage data on FSx for ONTAP via AI agent, BI, and search
- **Features**: Quick Sight (visualization/dashboards), Quick Index (document search), Quick Research (AI research)
- **Data source**: Connects to enterprise file data via S3 Access Points for FSx for NetApp ONTAP

> **Assumption requiring validation**: Whether Amazon Quick's Quick Index directly supports
> FSx ONTAP S3 Access Points as a data source needs to be verified at deployment time.
> Unlike standard S3 buckets, FSx ONTAP S3 AP may have differences in `GetBucketLocation`
> behavior and pagination characteristics.
> Perform a connection test during Day -3 configuration. If issues arise, use Quick Sight only
> as Plan B (Lambda formats file content via S3 AP → S3 → Quick Sight visualization).

## Duplicate Execution Prevention Mechanism

```
[User Click]
       │
       ▼
┌─────────────────┐
│ Frontend         │ ① Immediately disables button
│ (instant disable)│
└────────┬────────┘
         │ POST /api/sync
         ▼
┌─────────────────┐
│ Backend          │ ② asyncio.Lock for mutual exclusion
│ (lock check)     │    → Returns 409 if _is_running == True
└────────┬────────┘
         │ Transfer trigger
         ▼
┌─────────────────┐
│ ONTAP REST API  │ ③ ONTAP also rejects concurrent transfers (409)
│ (server control) │
└─────────────────┘
```

Three layers of defense ensure duplicate execution never occurs.

## State Transition Diagram

```
         ┌──────────┐
    ┌──▶ │  READY   │ ◀─────────────────┐
    │    └────┬─────┘                   │
    │         │ (button click)          │
    │         ▼                         │
    │    ┌──────────┐                   │
    │    │ STARTING │                   │
    │    └────┬─────┘                   │
    │         │ (trigger success)       │
    │         ▼                         │
    │    ┌──────────┐                   │
    │    │ SYNCING  │ ← polling monitor │
    │    └────┬─────┘                   │
    │         │                         │
    │    ┌────┴────┐                    │
    │    ▼         ▼                    │
    │ ┌──────┐  ┌───────┐               │
    │ │ DONE │  │ ERROR │               │
    │ └──┬───┘  └──┬────┘               │
    │    │         │                    │
    │    └─────────┴────────────────────┘
    │         (after 10s or retry)
    └───────────────────────────────────
```

## Network Requirements

- Sync Server must have HTTPS (TCP 443) access to the ONTAP management LIF
- Client devices must have HTTP (TCP 8080) access to the Sync Server
- Assumes usage within the same LAN / WiFi network

## Security Considerations

| Risk | Mitigation |
|------|-----------|
| ONTAP credential leakage | Managed in `.env`, mounted via Docker volume |
| Unauthorized sync triggers | Limited to demo environment, trusted network only |
| Man-in-the-middle attack | HTTPS on ONTAP side (self-signed certificate acceptable) |
| Server downtime | Docker restart policy + health checks |

For production use, additional authentication/authorization mechanisms are required.
