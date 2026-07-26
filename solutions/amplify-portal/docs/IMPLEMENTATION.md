# File Portal — Implementation Guide

> Developer/AI reference for understanding, reproducing, and customizing the portal.
> Each section documents not just WHAT was implemented, but WHY — the design intent behind each decision.

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
                    └─────────────────────────────────────────┘
```

## Configuration Files — Intent per Item

### `amplify/portal-config.ts`

| Setting | Value Example | Intent |
|---------|--------------|--------|
| `region` | `ap-northeast-1` | All resources colocated in same region as FSx for ONTAP |
| `s3ApAlias` | `eda-demo-s3ap-...-ext-s3alias` | Internet-origin S3 AP for file browsing without VPC |
| `stateMachineArn` | `arn:aws:states:...` | Step Functions workflow for AI processing (UC patterns) |
| `vpcId` | `vpc-0123456789abcdef0` | VPC where FSx ENIs reside — Lambda must be here for ONTAP REST API |
| `vpcSubnetIds` | `subnet-0123456789abcdef0` | Same subnet as FSx for ONTAP — ensures network path exists |
| `vpcSecurityGroupIds` | `sg-0123456789abcdef0` | FSx's own SG — allows all-traffic egress by default |
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
