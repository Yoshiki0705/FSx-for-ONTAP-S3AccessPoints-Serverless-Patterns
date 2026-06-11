# Partner Handover Guide

[日本語](handover-ja.md) | [English](handover-en.md)

## Deliverables

| # | Deliverable | Description |
|---|-------------|-------------|
| 1 | Source Code | This entire repository |
| 2 | Demo Mode | Instant UI verification without ONTAP connection |
| 3 | CloudFormation Template | Build AWS infrastructure with a single command |
| 4 | Setup Scripts | Generate SnapMirror / S3 AP configuration steps |
| 5 | Operation Guide | Demo day procedures + fallback plans |
| 6 | Cost Estimate | Approximate AWS monthly / weekly costs |
| 7 | Deployment Timeline | Work plan from Day -7 to Day 0 |
| 8 | Network Alternatives | Connection methods when VPN is unavailable at the venue |

---

## Get Started Quickly (5 minutes)

You can verify the UI behavior even without an ONTAP environment:

```bash
# 1. Clone the repository
git clone <repository-url>
cd snapmirror-one-click-sync

# 2. Start in demo mode
cp .env.example .env
# Edit .env: change to DEMO_MODE=true

# 3. Start with Docker
docker compose up -d

# 4. Open in browser
open http://localhost:8080
```

→ Press the orange button to run a simulated sync (5-12 seconds).

---

## Switch to Production Configuration

Once you've verified operation in demo mode, switch to production configuration:

1. Follow the timeline in [docs/deployment-timeline-ja.md](deployment-timeline-ja.md)
2. Change to `DEMO_MODE=false`
3. Set `ONTAP_HOST` and `SNAPMIRROR_UUID` to real environment values
4. Run E2E tests: `./scripts/e2e-test.sh`

---

## Documentation Index

| Document | Audience | Content |
|----------|----------|---------|
| [README.md](../README.md) | Everyone | Project overview |
| [setup-guide-ja.md](setup-guide-ja.md) | Engineers | Environment setup |
| [deployment-timeline-ja.md](deployment-timeline-ja.md) | PM/Engineers | Work plan |
| [architecture.md](architecture.md) | Engineers | Technical architecture |
| [operation-guide-ja.md](operation-guide-ja.md) | Demo operators | Day-of procedures |
| [network-alternatives-ja.md](network-alternatives-ja.md) | Network staff | VPN alternatives |
| [cost-estimate-ja.md](cost-estimate-ja.md) | PM | Cost estimates |

---

## FAQ

### Q: What equipment is needed on demo day?

- On-premises NetApp ONTAP (already set up)
- PC for Sync Server (Docker-capable, macOS/Windows/Linux)
- **Network connection for mobile hotspot** (PC mobile line or venue WiFi)
- AWS VPN connection method (Client VPN recommended)
- Smartphone (for operating the demo — connects to PC's hotspot)
- (Optional) Portable WiFi router
- (Optional) Printed QR code or QR displayed on PC

### Q: What screens do visitors see?

1. **Sync Server screen** (smartphone or PC browser) — One-click sync
2. **Amazon Quick screen** (PC browser) — Search and analyze synced data

### Q: What ONTAP-side preparation is needed?

- Prepare CIFS/NFS shared folders (for visitors to save files)
- Pre-place demo template files (recommended)
- Verify SnapMirror relationship is in Idle state

### Q: What if the demo fails?

See fallback plans in [operation-guide-ja.md](operation-guide-ja.md).
As a last resort, prepare a pre-recorded demo video on USB.

### Q: Who to contact if issues arise?

Report via GitHub Issues.

---

## Demo Success Checklist

### Day -7
- [ ] AWS CloudFormation deployment complete
- [ ] VPN connection verified

### Day -5
- [ ] SnapMirror Initialize complete
- [ ] S3 Access Point configuration complete

### Day -3
- [ ] Amazon Quick connection complete
- [ ] Verified Quick returns search results

### Day -1
- [ ] Sync Server startup confirmed
- [ ] E2E tests passed
- [ ] Full end-to-end rehearsal complete
- [ ] Fallback verified (demo video on USB ready)
- [ ] Backup VPN connection tested

### Day 0 (Demo Day)
- [ ] Equipment setup complete
- [ ] Network connection verified
- [ ] VPN UP confirmed
- [ ] Test sync executed once
- [ ] Demo begins 🎉
