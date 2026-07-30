# File Portal — Implementation Guide

> Developer/AI reference for understanding, reproducing, and customizing the portal.
> Each section documents not just WHAT was implemented, but WHY — the design intent behind each decision.

> **End users**: This document is for developers and AI agents. If you're looking for how to use the portal day-to-day, see the [User Guide](../../docs/en/portal-user-guide.md) ([日本語](../../docs/ja/portal-user-guide.md)).

## Design Intent Summary

This portal implements a **System Manager-equivalent web UI** for FSx for ONTAP, accessible via browser without VPN or CLI tools. Key constraints that shaped the architecture:

1. **CloudFormation 1MB template limit** → Led to generic dispatch pattern (8 endpoints instead of 73)
2. **ONTAP REST API requires VPC access** → Led to VPC split architecture (File Lambdas outside, Admin Lambdas inside)
3. **Non-technical users need simple navigation** → Led to card-grid categories instead of flat tab list
4. **Data protection operations are irreversible** → Led to multi-step confirmation (ENABLE typing, retention period visibility)
5. **8-language internationalization** → Led to ja.ts as type-safe source of truth
6. **Browser refresh must preserve state** → Led to URL hash persistence (`#resources`, `#arp`, etc.)

## Architecture

```
Browser → Amplify (Cognito auth) → AppSync GraphQL
                                        ↓
                    ┌─────────────────────────────────────────┐
                    │ Generic Dispatch (AWSJSON)              │
                    │ adminQuery/Mutation → ResourceMgmt λ    │ ← VPC (ONTAP REST API)
                    │ arpQuery/Mutation → ArpResponse λ       │ ← VPC
                    │ protectionQuery/Mutation → Snapshots λ  │ ← VPC
                    │ fileQuery/Mutation → ListFiles λ        │ ← No VPC (S3 AP Internet-origin)
                    │ agentQuery → AgentChat λ               │ ← No VPC (Bedrock + S3 AP)
                    └─────────────────────────────────────────┘
```

## Configuration Files — Intent per Item

### `amplify/portal-config.ts`

| Setting | Value Example | Intent |
|---------|--------------|--------|
| `region` | `ap-northeast-1` | All resources colocated in same region as FSx for ONTAP |
| `s3ApAlias` | `eda-demo-s3ap-...-ext-s3alias` | Internet-origin S3 AP for file browsing without VPC |
| `stateMachineArn` | `arn:aws:states:...` | Step Functions workflow for AI processing (UC patterns) |
| `vpcId` | `vpc-05192d06e1e91d756` | VPC where FSx ENIs reside — Lambda must be here for ONTAP REST API |
| `vpcSubnetIds` | `subnet-0dc75edfe8650bf44` | Same subnet as FSx for ONTAP — ensures network path exists |
| `vpcSecurityGroupIds` | `sg-015df9ccadf010bf5` | FSx's own SG — allows all-traffic egress by default |
| `groupApMapping` | `{}` | Per-team S3 AP routing for file isolation (My Files feature) |
| `bedrockKbId` | `""` | Bedrock Knowledge Base for semantic file search |

**Design intent**: VPC settings are optional — when empty, admin panels show "ONTAP Connection Required" gracefully. This enables DemoMode where file browsing works without VPC infrastructure.

### `amplify/backend.ts`

| Resource | Intent |
|----------|--------|
| VPC Lambda (conditional) | `vpcConfig && { vpc, securityGroups, vpcSubnets }` — only adds VPC when config is set |
| `AWSLambdaVPCAccessExecutionRole` | Required for ENI creation in VPC — added conditionally with VPC |
| `Vpc.fromVpcAttributes` | NOT `fromLookup` — avoids CDK context/account requirement during synth |
| `Code.fromAsset("functions/...")` | External files (not inline) — keeps template under 1MB |
| cdk-nag `AwsSolutionsChecks` | CI-only (`CDK_NAG=1`). NOT applied during synth/deploy. Amplify Gen2 resources (AppSync, Cognito, internal S3) produce Non-Compliant findings that are not user-configurable — applying nag as Aspect causes `[AssemblyError]` blocking all deploys. Suppressions in backend.ts document accepted findings. |

### `amplify/data/resource.ts` — Generic Dispatch Schema

**Problem**: 73 individual operations generate 146 CloudFormation resources (Resolver + FunctionConfiguration each), exceeding 1MB template limit.

**Solution**: 8 generic endpoints with `action` + `params: AWSJSON` signature.

**Intent per endpoint**:
| Endpoint | Auth | Rationale |
|----------|------|-----------|
| `adminQuery` | `storage-admin` group | Read operations that reveal infrastructure details |
| `adminMutation` | `storage-admin` group | Write operations that modify storage |
| `arpQuery` | `authenticated` | Read ARP status (all users see protection state) |
| `arpMutation` | `storage-admin` group | Incident response requires elevated privileges |
| `protectionQuery` | `authenticated` | Snapshot list visible to all (browse past versions) |
| `protectionMutation` | `storage-admin` group | Lock/create/delete snapshots requires admin |
| `fileQuery` | `authenticated` | All users can browse files |
| `fileMutation` | `authenticated` | Trash/rename accessible to file owners |

### `amplify/data/resolvers/*-dispatch.js`

**Critical design detail**: AWSJSON scalar type delivers `params` as a pre-parsed OBJECT (not string). The resolver MUST check `typeof`:
```javascript
const params = typeof ctx.arguments.params === "string"
  ? JSON.parse(ctx.arguments.params)
  : (ctx.arguments.params || {});
```
Without this, `JSON.parse(object)` silently produces `{}` → Lambda receives empty params → "required field missing" errors.

## UI Design Decisions — Intent

### Resource Management: Card Grid (not flat tabs)
- **Before**: Flat horizontal tab row with 10 items — looked machine-generated, hard to scan
- **After**: 3 category sections (Storage / Access Control / Protection) with icon cards + descriptions
- **Intent**: Match System Manager's grouped navigation. Users can find related functions visually.
- **File**: `src/components/ResourceManagement.tsx`

### VolumeSelector: Dropdown (not manual input)
- **Before**: Text input for volume name/UUID — users didn't know valid values
- **After**: Pre-populated dropdown from ONTAP REST API with `autoSelectFirst`
- **Intent**: System Manager never requires manual UUID input. All selectable entities should be queryable.
- **File**: `src/components/admin/VolumeSelector.tsx`

### Tamperproof Enable: ENABLE Prompt (not simple confirm)
- **Before**: `window.confirm("Enable?")` — one click enables irreversible operation
- **After**: `window.prompt` requiring user to TYPE "ENABLE"
- **Intent**: Compliance SnapLock volumes cannot disable locking once enabled. Accidental clicks must be prevented. The typed confirmation pattern is industry standard for destructive/irreversible operations (AWS, Terraform, etc.)
- **File**: `src/components/admin/SnapshotAdminManager.tsx`

### SnapLock Volume Creation: Retention Period Presets
- **Before**: Raw ISO 8601 input (P30D, P1Y) — even engineers found it confusing
- **After**: Natural language dropdown presets (1 day, 7 days, 30 days, 1 year, etc.) with custom option
- **Intent**: SnapLock retention is immutable after creation. Confusing input increases risk of incorrect configuration. Preset values cover 90% of use cases; custom allows power users to set specific durations.
- **File**: `src/components/admin/VolumeManager.tsx`

### URL Hash Navigation
- **Before**: Browser refresh always returned to "All Files"
- **After**: URL hash (`#resources`, `#arp`, `#snapshots`) persists active section
- **Intent**: Admin users frequently refresh during configuration tasks. Losing context is frustrating and wastes time.
- **File**: `src/App.tsx` — `getInitialSection()` reads hash, `setActiveSection()` writes hash

### Lock Panel: Live Data (not informational)
- **Before**: Static cards explaining what SnapLock/S3 Object Lock/Tamperproof are
- **After**: Real-time state from ONTAP REST API — locked snapshots table, retention config display
- **Intent**: An admin panel that only describes features but doesn't show current state is useless for operational monitoring. Users need to see "what is locked NOW" and "when does it expire."
- **File**: `src/components/SnaplockStatus.tsx`

## Adding a New Admin Action

1. Add handler in `functions/resource-management/handler.py`:
   ```python
   elif action == "myNewAction":
       return _my_new_action(http, headers, event, user_id)
   ```
2. Frontend call (no schema/CDK changes needed):
   ```typescript
   const resp = await (client.mutations as any).adminMutation({
     action: "myNewAction",
     params: JSON.stringify({ param1: "value" }),
   });
   const data = parseResponse<{ success: boolean }>(resp);
   ```

## Modification Log

| Date | Change | Intent | Files |
|------|--------|--------|-------|
| 2026-07-26 | Generic dispatch refactor | Fix CloudFormation 1MB limit (73 ops → 8 endpoints) | backend.ts, resource.ts, resolvers |
| 2026-07-26 | VolumeSelector component | Replace manual UUID/name input with System Manager-style dropdown | VolumeSelector.tsx, QuotaManager, SnaplockManager |
| 2026-07-26 | AWSJSON typeof fix | AppSync delivers objects not strings — prevent empty params | all *-dispatch.js |
| 2026-07-26 | URL hash navigation | Preserve admin context on browser refresh | App.tsx |
| 2026-07-26 | Tamperproof ENABLE prompt | Prevent accidental irreversible locking (typed confirmation) | SnapshotAdminManager.tsx |
| 2026-07-26 | SnapLock retention presets + custom | Natural language selector + Custom ISO 8601 option + docs link | VolumeManager.tsx |
| 2026-07-26 | Card grid Resource Management | Replace flat tabs with categorized card navigation | ResourceManagement.tsx |
| 2026-07-26 | Lock panel live data | Show actual locked snapshots from ONTAP instead of descriptions | SnaplockStatus.tsx |
| 2026-07-26 | Export Policy type fix | Policy ID is number from ONTAP — ensure correct type handling | ExportPolicyManager.tsx |
| 2026-07-26 | SnapLock volume creation | Add SnapLock type/retention to volume creation form | VolumeManager.tsx, handler.py |
| 2026-07-26 | ARP listActiveBlocks fix | Error "4" display — added robust fallback with empty arrays | data-protection/handler.py |
| 2026-07-26 | SnapLock custom retention: num+unit selector | Replace ISO 8601 text with number+unit dropdown for custom periods | VolumeManager.tsx |
| 2026-07-26 | ARP Active Blocks error fix | Lambda fallback for ImportError + UI filters short error codes | data-protection/handler.py, ArpResponseActions.tsx |
| 2026-07-26 | Lock panel complete rewrite | 3 tabs now show state + action buttons (not just descriptions) | SnaplockStatus.tsx |
| 2026-07-26 | Lock panel admin navigation | Buttons redirect to correct admin sub-panels (#resources) | SnaplockStatus.tsx |
| 2026-07-26 | Export Policy rule form: full fields | Add RO/RW/Superuser/Protocol selectors (System Manager parity) | ExportPolicyManager.tsx |
| 2026-07-26 | P1: Lock panel inline management | SnapLock tab shows volume list; Tamperproof tab has inline lock form + retention selector | SnaplockStatus.tsx, handler.py |
| 2026-07-26 | P2: Export Policy CRUD | Create/delete policies (not just rules). Delete protected for 'default' policy | ExportPolicyManager.tsx, handler.py |
| 2026-07-26 | P3: SMB encryption toggle + CA explanation | ON/OFF button for SMB 3.0 in-transit encryption; CA share info with ONTAP docs link | CifsShareManager.tsx, handler.py |
| 2026-07-26 | P4: VolumeSelector search/debounce | Server-side wildcard filter (ONTAP `name=*keyword*`), 300ms debounce for large environments | VolumeSelector.tsx, QtreeManager.tsx, handler.py |
| 2026-07-26 | UX: Natural confirm dialogs | Replace colon-separated "本当に削除しますか: X?" with natural "「X」を本当に削除しますか？" across all panels | All admin components, all 8 locale files |
| 2026-07-26 | UX: Explicit action buttons | Replace cryptic ✕ with labeled buttons (共有削除, ルール削除 etc.) | CifsShareManager.tsx |
| 2026-07-26 | cdk-nag: CI-only opt-in | Nag as CDK Aspect blocks deploy (Amplify Gen2 resources non-compliant). Changed to CDK_NAG=1 opt-in for CI only | backend.ts |
| 2026-07-26 | S3 Object Lock status + config UI | Live status from real S3 bucket (Governance/1-day). Bucket search + mode/retention config form | SnaplockStatus.tsx, handler.py |
| 2026-07-26 | Lock panel wording fix | コンテンツ不変性 → データ保護・改ざん防止 (natural Japanese) | ja.ts |
| 2026-07-26 | scripts/dev.sh | `npm start` runs sandbox + vite together, Ctrl+C stops both | package.json, scripts/dev.sh |
| 2026-07-27 | AI Agent Chat | Bedrock Converse + tool_use multi-agent (file-explorer, knowledge-analyst, safety-controller) | AgentChat.tsx, handler.py |
| 2026-07-27 | Admin-gated AI features | DynamoDB PortalSettingsTable + AiSettingsManager toggle UI (disabled by default) | backend.ts, AiSettingsManager.tsx, App.tsx |
| 2026-07-27 | Phase 1a: Chat history | DynamoDB ChatHistoryTable (userId+sessionId, TTL 90d), auto-save, session list | handler.py, AgentChat.tsx |
| 2026-07-27 | Phase 1b: File permissions sidebar | ONTAP REST /protocols/file-security/permissions → AgentFileSidebar.tsx | snapshots/index.py, AgentFileSidebar.tsx |
| 2026-07-27 | Phase 1c: Multimodal image upload | Drag-drop + base64 → Bedrock Converse image content block | handler.py, AgentChat.tsx |
| 2026-07-27 | Phase 1d: Mode toggle | 3-pill selector (KB/Agent/Multi) with per-mode system prompt + tool filtering | handler.py, AgentChat.tsx |
| 2026-07-27 | Phase 1e: KB Smart Routing | Group-based KB search scope filtering via GROUP_PATH_PREFIXES + retrievalFilter | handler.py, agent-dispatch.js |
| 2026-07-27 | Phase 2: Agent Directory | DynamoDB AgentDirectoryTable, CRUD (create/list/get/update/delete), card grid UI | handler.py, AgentDirectory.tsx |
| 2026-07-27 | Phase 2: Agent Creator | Emoji icon picker, tools selection, system prompt, category, shared toggle | AgentCreator.tsx |
| 2026-07-27 | Phase 2: Multi-Agent Teams | DynamoDB AgentTeamsTable, team wizard (select agents + assign roles), gallery | handler.py, AgentTeams.tsx |
| 2026-07-27 | Phase 2: Navigation integration | agentDir section with tabs (Directory/Teams), hidden when AI disabled | App.tsx |
| 2026-07-27 | Lock dialog UX fix | Error message shown inside modal (not page bottom); Enable Tamperproof button when locking not enabled | VersionHistory.tsx, snapshots/index.py |
| 2026-07-27 | Lock column display fix | Unlocked snapshots show `—` instead of 🔓 icon (was confusing: all appeared locked) | VersionHistory.tsx |
| 2026-07-27 | Version Diff feature | Checkbox selection + compare button + diff result table (added/modified/deleted). DemoMode client-side fallback | VersionHistory.tsx, snapshots/index.py |
| 2026-07-27 | Clone from Snapshot rename | "Restore" → "Clone" with ransomware recovery/audit/test use-case description. Full i18n | RestoreFromSnapshot.tsx, ja.ts, en.ts |
| 2026-07-27 | Retention period range hint | ISO field shows valid range P1D–P36500D / P1M–P1200M / P1Y–P100Y | ja.ts, en.ts |
| 2026-07-27 | Tamperproof enable: custom modal | Replace window.prompt with custom dialog: 3 bullet points + ENABLE typed confirmation + disabled-until-correct button | SnapshotAdminManager.tsx, ja.ts, en.ts |
| 2026-07-27 | Snapshot policy assign to volume | Policy tab: "Assign to volume" button + VolumeSelector dialog. Tamperproof tab: inline dropdown to change policy | SnapshotAdminManager.tsx, ja.ts, en.ts |
| 2026-07-27 | Snapshot policy delete | Delete button per policy row (red). Cannot delete if assigned — error guides to detach first | SnapshotAdminManager.tsx, handler.py, ja.ts, en.ts |
| 2026-07-27 | Tamperproof design doc | 3-layer design guide + stop flow (Pattern D) + API reference | docs/tamperproof-snapshot-design.md |
| 2026-07-28 | ShareLink i18n | Full Japanese translation for share link dialog (title, expires, generate, copy, security note) | ShareLink.tsx, ja.ts, en.ts |
| 2026-07-28 | ShareLink user guide | Detailed share link usage guide in portal-tabs-guide.md (操作手順, 仕様, セキュリティ) | portal-tabs-guide.md |
| 2026-07-28 | Folder share link | Copy direct link to folder (`#files?path=prefix`). initialPrefix prop on FileExplorer for external navigation | FileExplorer.tsx, App.tsx, ja.ts, en.ts |
| 2026-07-28 | ZIP folder download | Download all files as ZIP (500 files / 500MB max). DemoMode mock. Lambda action in list-files handler | list-files/index.py, FolderDownload.tsx, ja.ts, en.ts |
| 2026-07-28 | Folder favorites | Star button (☆/★) on both folders and files. FavoritesView shows 📁/📄 with correct navigation | FileExplorer.tsx, Favorites.tsx, App.tsx |
| 2026-07-28 | AD/OIDC auth config | Environment-driven OIDC/SAML in auth/resource.ts. authMode in portal-settings. socialProviders in Authenticator | auth/resource.ts, portal-settings.ts, main.tsx |
| 2026-07-28 | Folder sharing design doc | ZIP generation architecture + AD/OIDC integration plan | docs/folder-sharing-and-auth-design.md |

## AI Agent Architecture (Phase 1 + Phase 2)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Frontend (AgentChat.tsx)                                             │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐       │
│  │ Mode Toggle │  │ Card Grid    │  │ Chat Messages        │       │
│  │ KB/Agent/   │  │ (filtered by │  │ + Tool Trace Timeline│       │
│  │ Multi-Agent │  │  mode)       │  │ + Citations          │       │
│  └─────────────┘  └──────────────┘  └──────────────────────┘       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐       │
│  │ 📎 Image    │  │ 📜 History   │  │ 📂 File Sidebar      │       │
│  │ Upload      │  │ Panel        │  │ (Permissions)        │       │
│  └─────────────┘  └──────────────┘  └──────────────────────┘       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ agentQuery (AppSync)
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Lambda: agent-chat/handler.py                                        │
│                                                                      │
│  Dispatch:                                                           │
│  ├── chat → run_agent_loop(message, history, image, mode, groups)   │
│  ├── saveSession / loadSession / listSessions / deleteSession       │
│  ├── listAgents / getAgent / createAgent / updateAgent / deleteAgent│
│  └── listTeams / createTeam / deleteTeam                            │
│                                                                      │
│  Agent Loop:                                                         │
│  1. Select system prompt + tools based on mode                      │
│  2. Build messages (text + optional image)                          │
│  3. Call Bedrock Converse (tool_use loop, max 8 iterations)         │
│  4. Execute tools: list_files, read_file, search_files,             │
│     get_volume_summary, kb_search (with smart routing), approval    │
│  5. Return: { answer, toolCalls (with agent labels), model }        │
│                                                                      │
│  DynamoDB Tables:                                                    │
│  ├── ChatHistoryTable (userId + sessionId, TTL 90d)                 │
│  ├── AgentDirectoryTable (agentId → name, prompt, tools, icon)      │
│  ├── AgentTeamsTable (teamId → agents with roles)                   │
│  └── PortalSettingsTable (settingKey → enabled/disabled)            │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│ External Services                                                    │
│  ├── Bedrock Converse (Nova Lite / Claude) — LLM + Vision           │
│  ├── Bedrock KB Retrieve (S3 Vectors / OpenSearch Serverless)       │
│  └── S3 AP (Internet-origin) — File listing/reading                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Admin Feature Gating

All AI features are **disabled by default** and controlled via `PortalSettingsTable`:

| Setting Key | Feature | Dependency |
|-------------|---------|-----------|
| `aiAgentEnabled` | AI Agent Chat nav + page | None |
| `aiSearchEnabled` | Semantic Search nav + page | KB configured |
| `aiMultimodalEnabled` | Image upload in chat | Agent enabled |
| `chatHistoryEnabled` | Session persistence | Agent enabled |
| `aiSmartRoutingEnabled` | Group-based KB filtering | Search enabled |
| `agentDirectoryEnabled` | Agent Directory + Teams | Agent enabled |

Admin toggles these from **Resource Management > AI Settings** panel.

---

## Modification Log

### 2026-07-30: 6 New ResourceManagement Panels

**Added panels (16 total, up from 10)**:

| Panel | Category | Component | Lambda Actions |
|-------|----------|-----------|---------------|
| FlexClone | Storage | `FlexCloneManager.tsx` | listFlexClones, createFlexClone, splitFlexClone |
| Local Users | Access Control | `LocalUserManager.tsx` | listLocalUsers, createLocalUser, deleteLocalUser, listLocalGroups, createLocalGroup, deleteLocalGroup, listGroupMembers, addGroupMember, removeGroupMember |
| Name Mapping | Access Control | `NameMappingManager.tsx` | listNameMappings, createNameMapping, deleteNameMapping |
| FPolicy | Data Protection | `FPolicyManager.tsx` | listFpolicyPolicies, listFpolicyEvents, getFpolicyStatus |
| Vscan | Data Protection | `VscanManager.tsx` | getVscanStatus, listVscanPolicies |
| SnapMirror | Data Protection | `SnapMirrorStatus.tsx` | listSnapmirrorRelationships, getSnapmirrorTransfers |

**Design decisions**:
- **Vscan guidance**: When Vscan is not configured (`enabled: false`), displays a 5-step setup wizard with 6-vendor comparison table and external links (AWS Blog, GitHub samples, NetApp docs). This "zero-to-configured" flow was added because Vscan has the highest setup barrier of any ONTAP feature — it requires external Windows/Linux infrastructure.
- **FlexClone split**: Confirmation dialog required because split is irreversible (clone becomes independent volume, losing space efficiency).
- **NameMapping direction selector**: 4 directions (win_unix, unix_win, s3_unix, s3_win) exposed. `s3_unix` is auto-managed by FSx when S3 AP is attached — the UI shows it for visibility but notes it shouldn't be manually modified.
- **SnapMirror expandable transfers**: Click to expand last 10 transfers per relationship, avoiding heavy API calls on initial load.
- **DemoMode behavior**: All panels render gracefully with empty state when ONTAP is not connected. No API errors shown to users.

### 2026-07-30: Graceful Error Handling for New Panels

**Problem**: When the backend Lambda hasn't been redeployed after adding new actions (or in DemoMode), panels showed `"⚠️ Unknown action: listVscanPolicies"` etc. as red error banners.

**Fix**: All 6 new panels now filter out `"Unknown action"` and `"ONTAP connection not configured"` errors from the UI, falling back to empty state (which is the correct DemoMode behavior). Affected files:
- `VscanManager.tsx` — `loadData()` response handling
- `NameMappingManager.tsx` — `loadMappings()` response handling
- `LocalUserManager.tsx` — `loadUsers()` + `loadGroups()` (2 locations)
- `FlexCloneManager.tsx` — `loadClones()` response handling
- `SnapMirrorStatus.tsx` — `loadRelationships()` response handling
- `FPolicyManager.tsx` — `loadData()` across all 3 tabs

### 2026-07-30: Athena Query Panel UX Improvement

**Problem**: The Athena panel showed only a bare SQL textarea with `SELECT * FROM default.my_table LIMIT 10` — no explanation of what to input or how the panel relates to Glue Crawler.

**Fix**: Added guidance panel with:
- Explanation: "Catalog FSx for ONTAP files with Glue Crawler, then query with SQL here"
- Expandable `<details>` section with 3 practical query examples (copy-pasteable)
- Default SQL changed to `SHOW TABLES IN default` (discover tables first)
- Multi-line placeholder with commented examples

**ResourceManagement final layout (4 categories × 16 panels + 1 service)**:
```
Storage (🗄️):        Volumes / 🧬FlexClone / Qtree / Quotas / Efficiency
Access Control (🔐): Export Policies / SMB Shares / 👤Local Users / 🔀Name Mapping / QoS
Data Protection (🛡️): ARP/AI / Snapshots / SnapLock / 📡FPolicy / 🦠Vscan / 🪞SnapMirror
Services (🤖):       AI Settings
```


---

## Related Documents

| Document | Purpose |
|----------|---------|
| [Getting Started Guide](./GETTING-STARTED.md) | 30-minute quickstart with DemoMode |
| [PoC → Production Guide](../../docs/en/portal-poc-to-production.md) | Migration checklist for production FSx for ONTAP connectivity |
| [Scaling Guide](../../docs/en/portal-scaling-guide.md) | Capacity planning, throughput sharing, QoS, growth estimation |
| [Accessibility Statement](../../docs/en/portal-accessibility.md) | ARIA, keyboard nav, screen reader, WCAG compliance note |
| [Security Review](./SECURITY-REVIEW.md) | Threat model, IAM permissions, data flow analysis |
| [Authorization Model](../../docs/en/portal-authorization-model.md) | Cognito groups, S3 AP identity, role separation |
| [User Guide](../../docs/en/portal-user-guide.md) | End-user documentation (8 languages) |
| [Compliance Guide](../../docs/en/portal-compliance-guide.md) | Auditor-facing verification procedures |
| [AI Agent Demo Guide](./ai-agent-demo-guide.en.md) | E2E agent chat demonstration |
| [Admin Demo Guide](../../docs/en/admin-resource-management-demo.md) | Admin operations walkthrough |
