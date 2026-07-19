# Roadmap

プロジェクト全体の残課題と今後の方向性を管理するファイルです。

*Last updated: 2026-07-18*

---

## ✅ Recently Completed (this session)

| PR | Feature |
|---|---|
| #139 | CI: amplify-portal vitest + tsc in GitHub Actions |
| #140 | Job History: DynamoDB persistence + History tab |
| #141 | Loading skeleton during auth check |
| #142 | File preview (image detection + hover tooltip) |
| #143 | Results breadcrumb (click-to-navigate to folder) |
| #144 | FlexClone status display in Results tab |
| #145 | Restore from Snapshot action in Files tab |
| #136-137 | README redesign: 8 languages, hub-and-spoke (~12K→1.4K lines) |
| #138 | Documentation Design Principles in AGENTS.md |

---

## 🔜 Next Up

### File Portal UI (Amplify Gen2)

| Item | Priority | Notes |
|---|---|---|
| Connect FilePreview to actual presigned URL for image thumbnails | Medium | `fileKey` prop is ready; needs a `getPresignedUrl` AppSync query |
| Production Amplify Hosting deployment guide | Medium | Currently sandbox-only |
| SAML/OIDC Cognito integration guide | Low | For enterprise SSO |
| Mobile-responsive CSS refinements | Low | Basic responsive works, needs testing |

### Blog Publication

| Item | Status |
|---|---|
| Paste JA draft to hakobiya.hatenablog.com | Ready (`.private/article-file-portal-draft.md`) |
| Paste EN draft to dev.to | Ready (`.private/article-file-portal-draft.en.md`) |
| Update README blog link placeholders after publication | `grep 'TODO: Uncomment after blog'` in `solutions/nextcloud-test/README.md` |

---

## 📋 Operations Patterns (OPS2-OPS6)

| Pattern | Directory | Status | Description |
|---|---|---|---|
| OPS1 | `operations/capacity-rightsizing/` | ✅ Implemented | Volume/throughput monitoring + AI recommendations |
| OPS2 | `operations/storage-efficiency/` | 📋 Planned | Dedup/compression tracking |
| OPS3 | `operations/tiering-optimizer/` | 📋 Planned | FabricPool policy optimization |
| OPS4 | `operations/snapshot-lifecycle/` | 📋 Planned | Retention compliance + cleanup automation |
| OPS5 | `operations/cost-optimization/` | 📋 Planned | FinOps integration (cost allocation, recommendations) |
| OPS6 | `operations/qos-monitoring/` | 📋 Planned | QoS policy compliance monitoring |

---

## 🧪 AWS Verification Backlog

| UC Group | Status | Remaining Work |
|---|---|---|
| UC1, UC3, UC6-UC14 | ✅ E2E verified | — |
| UC2, UC4, UC5 | ✅ Deploy + components verified | Full E2E with test data |
| UC15-UC17 (Public Sector) | ⚠️ Code complete | AWS deploy + E2E verification |
| UC18-UC28 | ⚠️ Template + tests complete | AWS deploy + primary component verification |

---

## 🌐 Other Repositories README Redesign

Apply the same hub-and-spoke README design to all Yoshiki0705 public repos:

| Repository | Status |
|---|---|
| `fsxn-lakehouse-integrations` | 📋 Prompt ready |
| `fsxn-observability-integrations` | 📋 Prompt ready |
| `fsxn-cyber-resilience-patterns` | 📋 Prompt ready |
| `ontap-edge-to-cloud-ai` | 📋 Prompt ready |
| `vmware-migration-ec2-ontap` | 📋 Prompt ready |
| `blea-fsxn-usecase` | 📋 Prompt ready |
| `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | 📋 Prompt ready |

Prompt template: see main repo's global steering file (`~/.kiro/steering/global-documentation-design.md`)

---

## 🏗️ Infrastructure & CI

| Item | Status |
|---|---|
| Renovate GitHub App activation | 📋 Config exists, App needs enabling on repo |
| amplify-portal CI (vitest + tsc) | ✅ PR #139 |
| Nextcloud test CI | 📋 Not in CI (Docker-based, local only) |

---

## 📐 Design Principles (enforced)

Codified in `AGENTS.md` → "Documentation Design Principles" section:
- Hub & Spoke README model
- Progressive Disclosure (`<details>`)
- Action-First headings
- 7±2 rule
- Multi-language mirror structure
- No dead weight (no Phase history, no inline screenshots)

Global steering: `~/.kiro/steering/global-documentation-design.md`
