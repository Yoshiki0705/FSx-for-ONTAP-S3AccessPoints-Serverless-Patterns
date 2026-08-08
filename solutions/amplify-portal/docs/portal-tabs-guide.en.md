# Amplify Gen2 File Portal — Section Layout Guide

> 🌐 Language: **English** | [日本語](portal-tabs-guide.md)

> **Last updated**: 2026-07-22
> **Verified**: CDK Sandbox deploy → Cognito login → all 17 sections confirmed to render

---

## Overview

The File Portal for Amazon FSx for NetApp ONTAP (hereafter FSx for ONTAP) is organised as a sidebar navigation with 4 groups and 17 sections. Each section provides an independent capability, and all of them access data on the same FSx for ONTAP S3 Access Point.

![Sidebar layout](screenshots/portal-sidebar-layout.png)

```
┌────────────────────────────────────────────────────────────┐
│ File Portal                           demo@example.com     │
├──────────────┬─────────────────────────────────────────────┤
│ BROWSE       │                                             │
│  All Files   │  [Main Content Area]                        │
│  Favorites   │                                             │
│  Recent      │  + AI Assistant Panel (right, on selection) │
│  Folder Watch│                                             │
│  Upload      │                                             │
│──────────────│                                             │
│ AI & PROC.   │                                             │
│  AI Proc.    │                                             │
│  AI Chat     │                                             │
│  Search      │                                             │
│  History     │                                             │
│  Analytics   │                                             │
│  Agent Dir   │                                             │
│──────────────│                                             │
│ DATA PROT.   │                                             │
│  Snapshots   │                                             │
│  Lock        │                                             │
│  ARP/AI      │                                             │
│──────────────│                                             │
│ ADMIN        │                                             │
│  Resources   │                                             │
│  Version     │                                             │
│  Audit       │                                             │
└──────────────┴─────────────────────────────────────────────┘
```

---

## Browse group

### All Files (file browsing + AI + sharing + preview)

| Feature | Action | Icon |
|------|------|:---:|
| Folder navigation | Click a directory to move into it. Breadcrumbs show the hierarchy | — |
| Image preview | Click 🖼️ for an image popover served through a Presigned URL | 🖼️ |
| **PDF preview** | Click 📕 to display the PDF in an iframe (the browser's built-in viewer) | 📕 |
| **DOCX preview** | Click 📝 for inline rendering by docx-preview | 📝 |
| File download | Click 📄 to download through a Presigned URL | 📄 |
| Share link generation | 🔗 → choose a TTL (5 minutes / 15 minutes / 1 hour) → copy the URL | 🔗 |
| AI Q&A | Select a file → ask from the AI panel (Bedrock Converse API) | 🤖 |
| Rekognition | The "Detect Objects" button inside the image preview | 🏷️ |
| Restore from Snapshot | FlexClone creation dialog (FC7_FLEXCLONE_RESTORE) | 📸 |
| Process this folder | Passes the selected folder to AI Processing | ⚡ |
| **File tags** | Click 🏷️ to edit tags. Tag badges are shown on the row | 🏷️ |
| **AI metadata badges** | Shows AI processing results (classification, label count, entity count, whether a summary exists) on the row | — |
| **Rename** | Click ✏️ for inline editing. Names containing `/` are rejected (this is not a move) | ✏️ |
| **Move to trash** | Click 🗑️ → confirm → move to the `.trash/` prefix | 🗑️ |
| **Open trash / restore** | 🗑️ Trash in the header → browse `.trash/` → ♻️ returns the file to its original location | ♻️ |
| **Upload link** | 📤 → file name and validity period (1 hour / 24 hours) → issues a signed PUT URL | 📤 |
| **Folder download** | Click 📦 to download everything under the folder as a single ZIP | 📦 |
| **Snapshot comparison** | 🔍 → enter the S3 AP alias of the FlexClone → shows the difference between current and Snapshot side by side | 🔍 |
| **Document analysis** | 🔎 in the AI panel → text extraction with Textract, analysis with Comprehend | 🔎 |
| **QR code** | Inside the 🔗 share panel. Issues the signed URL as a QR PNG (for tablets) | 📱 |

**Office preview (new in 2026-07-22)**:
- PDF: simply passes the Presigned URL to an `<iframe>` (displayed by the browser's built-in viewer)
- DOCX: client-side rendering with the `docx-preview` library (70-80% layout fidelity)
- XLSX/PPTX: not supported at present (a download link is shown). Support via a Lambda Container Image is planned for Phase 2

**What rename and trash actually are**:
- Both are CopyObject + DeleteObject on the S3 Access Point. They are not metadata rewrites, so large files take time
- Trash is the `.trash/` prefix in the same bucket. It is not separate storage, so no capacity is freed

**Notes on upload links**:
- The issued URL is itself a credential. Until it expires, anyone holding the URL can write to that key
- This is why the UI shows the destination key alongside the validity period

**Scope of document analysis**:
- Textract and Comprehend send file content to managed services
- They are rejected under regulated folders (`phi/`, `dicom/`, `pii/`, `hipaa-`, `protected-health-`). The decision is defined in one place, `src/utils/regulatedPath.ts`

**CONFIDENTIAL guardrail**:
- When the data classification label in `shared/ai_guardrails.py` is CONFIDENTIAL/CUI, AI Q&A is blocked
- When blocked, the error message shows the classification level and the reason

---

### Favorites

Files pinned by the user are stored in DynamoDB (owner-scoped). One click jumps to that file in All Files.

---

### Recent

![Recent Files](../../../docs/screenshots/portal-demo/23-recent-files.png)

| Displayed information | Description |
|---------|------|
| File name + path | The most recently accessed file |
| Action icons | 👁️ view / 📥 download / 🤖 AI Q&A / 🖼️ preview / 🔗 share |
| Relative time | "2m ago", "3h ago", "2d ago" format |
| Click behaviour | Navigates to that file in All Files |

**Technical detail**:
- DynamoDB `RecentFile` model (owner-scoped, independent per Cognito user)
- Other components call the `recordRecentFile()` utility to log access
- Shows the 30 most recent entries in descending `accessedAt` order
- Empty state: "No recent file activity yet. Navigate to All Files to get started."

---

### Folder Watch

Appears in the sidebar only when Folder Watch is enabled in the admin settings (off by default).

| Feature | Action |
|------|------|
| Add a watch | Enter a prefix → choose the target events (create / update / delete) → add the watch |
| Remove a watch | "Remove" in the watch target table |
| Inbox | Shows events under the registered prefixes, newest first |
| Not-configured display | When the notification table is not connected, it shows "Not configured" rather than guessing |

**Why the toggle is in the admin settings**:
- The portal is not the publisher of the events. An FPolicy server or Transfer Family has to be publishing to EventBridge
- Enabling it is an administrator's declaration that a publisher exists. Turning it on by default would mean showing a permanently empty inbox in environments with no publisher

**Order in which the boundary is narrowed**:
1. The path boundary of the Cognito group (`GROUP_PATH_PREFIXES`)
2. Your own watched prefixes

This order cannot be swapped. Because a watch is your own record you can register `/` as well, but nothing outside the group boundary is visible (`storage-admin` bypasses the boundary). In a single-tenant configuration all events are visible. This is the same boundary as the file listing.

**Why the inbox is read through Lambda**:
- `FileNotification` is `allow.authenticated()`, and the bridge Lambda writes without an owner
- Reading it directly from the generated model client would let any authenticated user read every path, every user name and every client IP

**Path**: FPolicy server (or Transfer Family) → EventBridge → notification bridge Lambda → `FileNotification` table → portal. For configuring FPolicy itself, see the [event-driven/fpolicy pattern](../../event-driven/fpolicy/).

---

### Upload (Storage Browser for S3)

| Feature | Action |
|------|------|
| File upload | Drag and drop (up to 50 GB. Above 5 GB it switches to multipart automatically) |
| Folder creation | New folder |
| Copy and delete | File operations |
| Pagination | Handles large numbers of files |

- The Storage Browser component from `@aws-amplify/ui-react-storage`
- Accesses the S3 AP directly with temporary credentials from the Cognito Identity Pool (no Lambda involved)
- Files arriving from NFS/SMB are reflected in real time (ONTAP strong consistency)

---

## AI & Processing group

### AI Processing (workflow launch)

![AI Processing](screenshots/portal-ai-processing.png)

| Feature | Action |
|------|------|
| Pattern selection | UC1-UC28 / OPS1 / FC7_FLEXCLONE_RESTORE |
| Input path | The directory to process |
| Job submission | Step Functions StartExecution (AppSync HTTP resolver) |

---

### AI Chat (tool-executing agent)

An agent that responds while calling tools against files. It is used both for plain chat and for running saved agents and teams.

| Feature | Description |
|------|------|
| Mode selection | Normal chat / agent mode. Disabling agent mode in the admin settings removes the choice |
| Tools | File listing, reading, search, and approval requests. The tools in an agent definition are intersected with the tools that actually exist |
| Action approval | Operations that change something are presented as a card and are not executed until the user approves |
| Running a saved agent | Launching from Agent Directory runs with that definition (system prompt + tools). While running, a badge shows the definition name and the mode selection is hidden |
| Running a team | Launched from Multi-Agent Teams. Runs the member composition and roles as a single-turn supervisor (not as parallel agents) |

> Execution continues even when some team members are unreachable, and their names appear in `unavailableMembers` in the response. Execution is refused only when none of them are reachable.

---

### Search (semantic search)

Uses Retrieve on a Bedrock Knowledge Base to search by content rather than by file name. Choosing a file from the results moves to that location in All Files.

---

### Job History

DynamoDB `JobExecution` model (owner-scoped). Shows past jobs together with executionArn, pattern, status, and start/end times.

---

### Analytics (Athena SQL)

![Analytics](screenshots/portal-analytics.png)

Runs Athena SQL queries and shows the results as a table. A Glue Data Catalog browser (database → table → schema) is integrated as well.

---

### Agent Directory (agent definitions)

A list of saved agent definitions. Clicking a card opens the detail (tools, system prompt).

| Action | Description |
|------|------|
| 💬 Use in chat | Opens AI Chat with that definition and runs it |
| ✏️ Edit | Change the name / description / system prompt / category / icon / sharing settings. **Shown only to the author** |
| 🗑️ Delete | Delete the definition. **Shown only to the author** |
| Search / category filter | Partial match on name and description, filtering by category |

> Tools are chosen on the creation screen. At run time the intersection with the tools that actually exist is used, so they cannot be changed in the edit form (loose editing would make the display disagree with reality).

> Edit and delete are not shown for definitions shared by other users. The server side also rejects anyone other than the author, but presenting a clickable button would leave an authorisation error as the only means of explanation, so the UI hides them too.

---

## Data Protection group

### Snapshots (+ Tamperproof Snapshot locking)

![Snapshots fallback](screenshots/portal-snapshots-fallback.png)

Retrieves the Snapshot list through the ONTAP REST API. The "Browse this version" button on each Snapshot creates a FlexClone plus S3 AP to access the past state of the files.

**Tamperproof Snapshot (Snapshot Locking)**:
- Shows 🔐 (locked) / 🔓 (not locked) state on each Snapshot
- A locked Snapshot cannot be deleted until `expiry_time`, including by administrators
- The "🔒 Lock" button → specify a retention period (1-365 days) to lock (`storage-admin` group only)
- ONTAP REST API: set `expiry_time` on `PATCH /api/storage/volumes/{uuid}/snapshots/{uuid}`

**Prerequisites (enabling Tamperproof)**:
- Snapshot Locking must be enabled on the volume: `volume modify -volume <vol> -snapshot-locking-enabled true`
- No SnapLock licence is required (Snapshot Locking is a separate feature from SnapLock)

**Fallback UI when ONTAP is not connected**: instead of a blank screen, an info panel with the connection steps is shown.

---

### Lock (SnapLock + Tamperproof + S3 Object Lock)

![Lock fallback](screenshots/portal-snaplock-status-fallback.png)

Retrieved in real time from the ONTAP REST API:

| Retrieved information | API | Displayed content |
|---------|-----|---------|
| SnapLock type | `GET /api/storage/volumes?fields=snaplock` | Compliance / Enterprise / Non-SnapLock |
| Retention policy | Same as above | Default / Min / Max retention period |
| Autocommit period | Same as above | The automatic WORM commit period for inactive files |
| Snapshot Locking enabled/disabled | `fields=snapshot_locking_enabled` | 🔐 Enabled / 🔓 Not enabled |

**Three layers of immutability shown together**:
1. **ONTAP SnapLock**: volume-level WORM (enforced across all protocols — NFS/SMB/S3 AP)
2. **Tamperproof Snapshot**: per-Snapshot locking (operated from the Snapshots tab)
3. **S3 Object Lock**: WORM on the output bucket (archive protection for AI processing results)

**Fallback UI when ONTAP is not connected**: instead of a blank screen, an info panel with the connection steps is shown.

---

### ARP/AI (ransomware detection)

![ARP fallback](screenshots/portal-arp-status-fallback.png)

Retrieved in real time from the ONTAP REST API:

| Retrieved information | API | Displayed content |
|---------|-----|---------|
| ARP state | `GET /api/storage/volumes?fields=anti_ransomware` | enabled / dry_run / paused / disabled |
| Threat level | Same as above (`attack_probability`) | none / low / moderate / high |
| Learning start time | Same as above (`dry_run_start_time`) | Shown when in the dry_run state |
| Automatic Snapshot | Active when state=enabled | Creates an immutable Snapshot automatically on threat detection |

**ARP state card**:
- ✅ `enabled`: AI-driven protection is active (file entropy, extension changes, access pattern monitoring)
- 🔄 `dry_run`: Learning mode (learning patterns, no blocking)
- ⏸️ `paused`: paused by an administrator
- ⚠️ `disabled`: not configured

**Threat level display**:
- 🟢 `none`: no threat
- 🟡 `low`: low-probability anomaly detected
- 🟠 `moderate`: moderate — review recommended
- 🔴 `high`: possible ransomware attack — immediate response required

**Fallback UI when ONTAP is not connected**: instead of a blank screen, an info panel with the connection steps is shown.

---

## Admin group

### Resources (resource management)

Storage administration equivalent to ONTAP System Manager. Shown in the sidebar only to members of the `storage-admin` Cognito group.

Volumes, FlexClone, Qtrees, Quotas, Storage Efficiency, Export Policies, SMB Shares, Local Users, Name Mapping, QoS, ARP/AI, Snapshot management, SnapLock, FPolicy, Vscan, SnapMirror, FlexCache, Cluster (nodes / licences / EMS events).

For the procedures, see the [Admin Resource Management demo guide](../../../docs/en/admin-resource-management-demo.md) (27 scenarios).

> It is not shown to users outside the group. AppSync also rejects them with `allow.groups(["storage-admin"])`, but a menu that always errors when opened does not work as a menu.

---

### Version Diff (difference between Snapshots)

Compares files across two S3 APs (Current Volume vs FlexClone) side by side. Additions, deletions and changes are colour-coded.

**Fallback UI when ONTAP is not connected**: the same info panel as the Snapshots section.

---

### Audit Trail

![Audit Trail](screenshots/portal-audit-trail.png)

Searches CloudTrail S3 data events with Athena. Filters: file path, event type (Read/Write/All), date range. Shows "who accessed which file, and when".

---

## Supported preview formats

| Extension | Preview method | Icon |
|--------|:---:|:---:|
| `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.svg` | Presigned URL → popover | 🖼️ |
| `.pdf` | Presigned URL → iframe (browser's built-in viewer) | 📕 |
| `.docx` | Presigned URL → docx-preview (client-side) | 📝 |
| Other | Download link | 📄 |

---

## Internationalisation (i18n)

The portal supports 8 languages, switchable instantly from the pill-shaped dropdown in the top bar.

| Language | Browser auto-detection |
|------|:--------------:|
| 日本語 / English / 한국어 / 简体中文 / 繁體中文 / Français / Deutsch / Español | ✅ |

- **Language Switcher**: 🌐 globe icon + the current language in its native script + ▾ chevron
- **Persistence**: stored in `localStorage("portal-locale")`
- **Translation coverage**: all sidebar labels, section titles, all text in ARP/Lock/Snapshots, dialogs, fallback UI
- **Technical terms**: ONTAP, SnapLock, FlexClone, S3 AP, ARP/AI and similar stay in English in every language

---

## CDK quality gates

This portal is protected by the following quality gates:

| Tool | What it checks |
|--------|------------|
| cdk-nag (AwsSolutionsChecks) | Over-permissive IAM, encryption, log retention |
| CDK harness tests (35 assertions) | Lambda count, runtime, environment variables |
| IAM Access Analyzer | SECURITY_WARNING detection in policies |
| floci integration tests (9 tests) | S3 ListObjectsV2 + Delimiter behaviour |

cdk-nag is off by default (opt-in). Run `CDK_NAG=1 npx ampx generate outputs` when you want to see it. Not integrated into CI.
