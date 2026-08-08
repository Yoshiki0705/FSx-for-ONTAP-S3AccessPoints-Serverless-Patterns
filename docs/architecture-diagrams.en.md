# Architecture Diagram Index (Light / Dark)

🌐 **Language / 言語**: [日本語](architecture-diagrams.md) | **English**

🌐 **Language**: [日本語](architecture-diagrams.md) | English

Every architecture diagram in this repository is published in two themes with identical content: a **light theme (white background)** and a **dark theme (dark background)**.

- **Light is the default.** Every figure shown in the READMEs, the documentation, and the blog articles is the light version. It drops straight into white-background documents, print, and slides.
- **Dark** is the alternative for readers whose OS or browser is set to dark mode. Open it from the "Dark" column below.

Only the colours differ — layout, labels, and notes match across both. Each figure is exported with its theme pinned, so it will not flip based on the reader's dark-mode setting.

> **Note on colours**: the dark version uses `Res_*_48_Dark` (white line art) from the official AWS Architecture Icons asset package. The light `Res_*_48_Light` variant is dark navy line art and becomes illegible on a dark canvas, so the icon artwork itself is swapped rather than recoloured. Service icons (`Arch_*`) ship in a single coloured-tile form only and are therefore shared by both themes.

## Part 1 — File portal architecture

| Figure | What it shows | Light (default) | Dark |
|--------|---------------|:---:|:---:|
| Overall architecture | Two frontends reaching the same volume through one S3 Access Point | [View](images/architecture-overview-en.svg) | [View](images/architecture-overview-en-dark.svg) |
| Amplify Gen2 portal | The AI processing portal (VPC-external Lambda, S3 AP, audit logs) | [View](images/amplify-vpc-split-en.svg) | [View](images/amplify-vpc-split-en-dark.svg) |
| Nextcloud | File sharing UI mounting the S3 Access Point via the External Storage App | [View](images/nextcloud-external-storage-en.svg) | [View](images/nextcloud-external-storage-en-dark.svg) |
| Side-by-side | Amplify Gen2 and Nextcloud sharing one volume, coexisting with NFS and SMB | [View](images/coexistence-3path-en.svg) | [View](images/coexistence-3path-en-dark.svg) |

## Part 2 — Storage operations

| Figure | What it shows | Light (default) | Dark |
|--------|---------------|:---:|:---:|
| Admin operation path | Browser to ONTAP via Cognito, AppSync, and a Lambda inside the VPC | [View](images/part2-admin-operations-en.svg) | [View](images/part2-admin-operations-en-dark.svg) |
| ARP/AI lifecycle | Incidents tracked as four states (Detected / Contained / Investigating / Resolved) | [View](images/part2-arp-incident-lifecycle-en.svg) | [View](images/part2-arp-incident-lifecycle-en-dark.svg) |
| Audit log review path | Athena aggregating CloudTrail data events through the Glue Data Catalog | [View](images/part2-audit-log-pipeline-en.svg) | [View](images/part2-audit-log-pipeline-en-dark.svg) |
| ONTAP REST API path | Why the Lambda sits inside the VPC: the management LIF is private | [View](images/part2-ontap-rest-api-path-en.svg) | [View](images/part2-ontap-rest-api-path-en-dark.svg) |
| PoC to production | Adding connectivity and hardening across three phases | [View](images/part2-poc-to-production-en.svg) | [View](images/part2-poc-to-production-en-dark.svg) |

## Part 3 — AI agents

| Figure | What it shows | Light (default) | Dark |
|--------|---------------|:---:|:---:|
| AI agent architecture | File access through Bedrock Converse and AgentCore over MCP | [View](images/part3-ai-agent-overview-en.svg) | [View](images/part3-ai-agent-overview-en-dark.svg) |
| The three AgentChat modes | How mode=kb / mode=agent / mode=multi branch and call tools | [View](images/part3-agentchat-modes-en.svg) | [View](images/part3-agentchat-modes-en-dark.svg) |
| Semantic search | Vector search with Bedrock Knowledge Bases and OpenSearch Service | [View](images/part3-semantic-search-en.svg) | [View](images/part3-semantic-search-en-dark.svg) |
| Multi-agent coordination | How Supervisor / Collaborator / Reviewer split the work | [View](images/part3-agent-teams-en.svg) | [View](images/part3-agent-teams-en-dark.svg) |

## File formats and naming

| Use | Path | Notes |
|-----|------|-------|
| Documentation | `docs/images/<name>.svg` | Light. Referenced relatively from READMEs and docs |
| Documentation (dark) | `docs/images/<name>-dark.svg` | The "Dark" column above |
| Blog | `docs/images/png/<name>@2x.png` | Light. Referenced by absolute raw URL |
| Blog (dark) | `docs/images/png/<name>-dark@2x.png` | — |
| Editable source | `docs/diagrams/<name>.drawio` | Light is the only hand-edited source |
| Editable source (dark) | `docs/diagrams/dark/<name>.drawio` | Generated; do not hand-edit |

Japanese figures carry no language suffix; English figures are suffixed `-en` (for example `amplify-vpc-split-en.svg` / `amplify-vpc-split-en-dark.svg`).

## Regenerating the figures

The dark set is derived from the light set, so run these after editing a light source. Point `--icon-root` at a local extraction of the [official icon package](https://aws.amazon.com/architecture/icons/), kept outside the repository.

```bash
# 1. Regenerate the dark theme sources
python3 scripts/make-dark-diagrams.py --icon-root /tmp/awsicons

# 2. Export both themes to SVG + PNG@2x
bash scripts/export-diagrams.sh
```

## Related documents

- [File portal UI options (Amplify / Nextcloud / Custom)](file-portal-amplify-gen2.en.md)
- [Amplify Gen2 portal README](../solutions/amplify-portal/README.md)
- [Portal implementation guide](../solutions/amplify-portal/docs/IMPLEMENTATION.md)
