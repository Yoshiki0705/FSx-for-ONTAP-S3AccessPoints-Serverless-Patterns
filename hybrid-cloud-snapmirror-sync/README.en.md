# SnapMirror One-Click Sync

[日本語](README.md) | [English](README.en.md)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)

> **This pattern is not a data migration demo.**
> It demonstrates how enterprise file data replicated from an on-premises ONTAP environment to Amazon FSx for NetApp ONTAP can be made available to analytics, BI, and AI services through S3 Access Points — while preserving NAS-oriented operations and making data freshness explicit.

A demo tool that enables one-click data synchronization from on-premises NetApp ONTAP to Amazon FSx for NetApp ONTAP in a hybrid cloud environment.

## What This Repository Provides

| Provided | NOT Provided |
|----------|--------------|
| ✅ CloudFormation templates for AWS-side infrastructure | ❌ On-premises ONTAP initial setup procedures |
| ✅ Guide scripts for SnapMirror configuration | ❌ VPN device vendor-specific configuration |
| ✅ One-click sync Web UI + backend | ❌ Detailed Amazon Quick configuration guide |
| ✅ S3 Access Point configuration guide | ❌ Production-grade authentication/authorization design |
| ✅ Demo day operation guide + fallback plan | ❌ Data migration or permanent sync design |
| ✅ Cost estimate + deployment timeline | ❌ Multi-tenant / multi-region configuration |

## Use Case

This is a hybrid cloud pattern that continuously replicates enterprise file data from on-premises to FSx for NetApp ONTAP on AWS via SnapMirror scheduled replication + on-demand triggers, enabling search, analysis, and utilization through Amazon Quick via S3 Access Points.

> **Note**: SnapMirror on FSx for ONTAP provides scheduled asynchronous replication (minimum 5-minute interval). Synchronous SnapMirror is not supported. This tool adds on-demand triggering for near real-time demonstration purposes. See [docs/data-freshness.md](docs/data-freshness.md) for details.

Amazon Quick is a platform that integrates AI agents, BI (QuickSight), document search (Quick Index), research, and automation. By connecting to enterprise file data through S3 Access Points for FSx for NetApp ONTAP, it enables natural language data search, visualization, and analysis.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Event Venue (On-Premises)                                          │
│                                                                     │
│  [Smartphone/PC]  ──HTTP──▶  [Sync Server]       [ONTAP (Source)]   │
│   (Browser)                   (Python)                              │
└─────────────────────────────────────────────────────────────────────┘
                                     │                     │
                                     │ REST API (via VPN)   │ SnapMirror
                                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AWS Cloud (Tokyo Region)                                           │
│                                                                     │
│  [FSx for NetApp ONTAP]  ──S3 Access Point──▶  [Amazon Quick]       │
│   (Destination)                                 (Search/Analysis/    │
│   ← Sync Server calls REST API here             Utilization)        │
└─────────────────────────────────────────────────────────────────────┘
```

## Features

![Demo Screen — PC View](docs/images/01-ready-pc.png)

- **One-click operation**: Execute SnapMirror sync with a single button press — no technical expertise required
- **Multi-device support**: Operable from smartphone, tablet, or PC browsers
- **Double-execution prevention**: Button is disabled during sync to prevent duplicate executions from repeated clicks
- **Real-time progress display**: Sync progress shown with intuitive animations (UI progress updates are real-time; replication itself is near real-time)
- **Japanese UI**: Simple Japanese interface designed for non-technical users

## Prerequisites

- SnapMirror relationship established between on-premises NetApp ONTAP (9.8+) and FSx for NetApp ONTAP
- ONTAP REST API enabled (HTTPS, port 443)
- ONTAP user account with SnapMirror operation privileges
- Python 3.10–3.13 or Docker (**Recommended**: Docker. Python 3.14+ has dependency library compatibility issues, so please use Docker)

## Quick Start

### Docker (Recommended)

```bash
# 1. Create configuration file
cp .env.example .env
# Edit .env to configure ONTAP connection settings

# 2. Start
docker compose up -d

# 3. Access via browser
# http://<server-IP>:8080
```

### Direct Execution

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Create configuration file
cp ../.env.example ../.env
# Edit .env

# 3. Start
uvicorn app.main:app --host 0.0.0.0 --port 8080

# 4. Access via browser
# http://localhost:8080
```

## Configuration

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `ONTAP_HOST` | **FSx for ONTAP** management endpoint (must be reachable via VPN) | `management.fs-xxx.fsx.ap-northeast-1.amazonaws.com` |
| `ONTAP_USER` | FSx ONTAP REST API user (least privilege recommended) | `sync_user` |
| `ONTAP_PASSWORD` | REST API password | `****` |
| `ONTAP_VERIFY_SSL` | SSL certificate verification | `false` |
| `SNAPMIRROR_UUID` | SnapMirror relationship UUID | See setup guide |
| `AUTH_TOKEN` | API authentication token (empty = auth disabled) | `demo-secret-2026` |

## Detailed Setup

For SnapMirror UUID retrieval, ONTAP user creation, and full configuration details, see [docs/setup-guide-en.md](docs/setup-guide-en.md).

## Architecture Details

See [docs/architecture.md](docs/architecture.md) for details.

## AWS Infrastructure Deployment

Deploy AWS-side infrastructure (VPC, FSx for ONTAP, VPN) in one step using the CloudFormation template.

```bash
# 1. Set FSx admin password
export FSX_ADMIN_PASSWORD='YourSecurePassword123!'

# 2. Deploy (20-30 minutes)
./infra/deploy.sh

# 3. Configure SnapMirror relationship
./scripts/setup-snapmirror.sh

# 4. Configure S3 Access Point
./scripts/setup-s3-access-point.sh
```

For details, see:
- [infra/template.yaml](infra/template.yaml) — CloudFormation template
- [scripts/setup-snapmirror.sh](scripts/setup-snapmirror.sh) — SnapMirror configuration steps
- [scripts/setup-s3-access-point.sh](scripts/setup-s3-access-point.sh) — S3 AP configuration steps
- [docs/snapmirror-schedule-en.md](docs/snapmirror-schedule-en.md) — Sync interval tuning

## Cost Estimate

Estimated cost for the demo environment (~$89 for 1 week, ~$442/month).

See [docs/cost-estimate-en.md](docs/cost-estimate-en.md) for details.

## Security Notes

- This tool is designed for demo/PoC purposes
- Manage ONTAP credentials in `.env` file — do not commit to Git
- Add proper authentication/authorization mechanisms for production environments
- Intended for use within trusted networks such as event venues

### Supply Chain Security

This repository automatically runs the following security tools:

| Tool | Purpose | Trigger |
|------|---------|---------|
| [gitleaks](.github/workflows/gitleaks.yml) | Secret detection | Push/PR/Daily |
| [zizmor](.github/workflows/zizmor.yml) | GitHub Actions security | Workflow file changes/Weekly |
| [OpenSSF Scorecard](.github/workflows/scorecard.yml) | Security score | Push to main/Weekly |

Local development is protected by pre-commit hooks:
```bash
# Setup
git config core.hooksPath .githooks
# Or
pip install pre-commit && pre-commit install
```

## Demo Mode (No ONTAP Connection)

You can verify UI behavior and rehearse without an ONTAP environment:

```bash
# Enable in .env
DEMO_MODE=true

# Start
docker compose up -d
# → At http://localhost:8080, pressing the sync button
#   executes a simulated 5-12 second transfer
```

In demo mode, a "🎭 Demo Mode (ONTAP not connected)" badge is displayed at the top of the screen.

### What Can Be Verified in Demo Mode

| ✅ Verifiable | ❌ Not Verifiable |
|--------------|-------------------|
| UI behavior (buttons, progress display) | Actual SnapMirror transfer |
| Double-execution prevention | FSx connection via VPN |
| Completion/error screen display | Data verification via S3 AP |
| Audit log output | Search via Amazon Quick |
| E2E test script operation | Actual transfer speed |

## Feature Boundaries

| Component | Is | Is NOT |
|-----------|------|--------|
| SnapMirror | Scheduled async replication (min 5-min interval) + on-demand trigger | Synchronous replication or transaction sharing |
| FSx S3 Access Points | S3 API access to ONTAP file data | A standard S3 bucket |
| Amazon Quick | Consumption / insight / visualization layer | Source of truth for data |
| This tool | On-demand SnapMirror update trigger with UI | Data migration or ETL pipeline |

> The goal is not to demonstrate a dashboard. The goal is to demonstrate how existing enterprise file data can become actionable through AWS analytics and AI services without first moving it into a separate data lake.

## AWS-Native Observability

This pattern can be monitored entirely with AWS-native services — no third-party platforms required.

Amazon CloudWatch provides metrics (EMF), logs, dashboards, alarms, Logs Insights queries, Synthetics canaries, and Application Signals SLOs. AWS X-Ray and ADOT can trace the sync pipeline end-to-end. All events use a shared `correlation_id` for cross-service investigation.

See:
- [Observability Design](docs/observability-aws-native.md) — Metrics, dashboards, canaries, tracing
- [Event Schema](docs/observability-events.md) — Structured events, Logs Insights queries
- [SLO Design](docs/slo-design.md) — 5 SLOs with error budgets and incident response

## Data Validation and AI Readiness

This pattern does not assume that replicated data is automatically ready for BI, AI, or operational decisions.

Before Amazon Quick / QuickSight users consume the data, operators should validate freshness, schema expectations, classification, ownership, and usage boundaries. Business users should verify the source-of-record timestamp, replication timestamp, and dashboard refresh timestamp before using insights for operational decisions.

See:
- [Data Validation](docs/data-validation.md) — Raw → validated → consumption states
- [Business User Guide](docs/business-user-guide.md) — Dashboard labels, safe usage guidelines
- [AI Readiness Checklist](docs/ai-readiness-checklist.md) — Pre-AI/BI verification checklist

## Documentation

| Document | Audience | Content |
|----------|----------|---------|
| [Partner One-Pager](docs/partner-one-pager.md) | Partner/SI sales & pre-sales | Target customer, pain points, demo talk track |
| [Data Freshness & RPO](docs/data-freshness.md) | Storage architect, security | Replication model, RPO, consistency |
| [Governance & Audit](docs/governance-and-audit.md) | Security, compliance, public sector | Data classification, responsibility, audit trail |
| [Architecture](docs/architecture.md) | Technical | Component details, network, API |
| [Setup Guide](docs/setup-guide-en.md) | Engineer | Step-by-step deployment |
| [Operation Guide](docs/operation-guide-en.md) | Demo operator | Day-of-event procedures |
| [SnapMirror Schedule](docs/snapmirror-schedule-en.md) | Engineer | Schedule tuning, interval design |
| [Cost Estimate](docs/cost-estimate-en.md) | PM / Finance | AWS cost breakdown |
| [Deployment Timeline](docs/deployment-timeline-en.md) | PM / Engineer | Day-by-day plan |
| [Network Alternatives](docs/network-alternatives-en.md) | Network engineer | VPN alternatives for venues |
| [Observability (AWS-native)](docs/observability-aws-native.md) | SRE / DevOps | Metrics, dashboards, canaries, tracing |
| [Observability Events](docs/observability-events.md) | SRE / Developer | Event schema, Logs Insights queries |
| [SLO Design](docs/slo-design.md) | SRE / Platform | SLO definitions, error budgets |
| [Data Validation](docs/data-validation.md) | Data engineer | Raw → validated → consumption |
| [Business User Guide](docs/business-user-guide.md) | Business user | Dashboard labels, safe usage |
| [AI Readiness Checklist](docs/ai-readiness-checklist.md) | Data governance / AI | Pre-AI/BI verification |
| [Handover Guide](docs/handover-en.md) | Partner receiving the tool | Quick start + checklist |
| [Quick Demo Prompts](docs/quick-demo-prompts.md) | Demo operator / business | Sample prompts for Amazon Quick |

## License

MIT License
