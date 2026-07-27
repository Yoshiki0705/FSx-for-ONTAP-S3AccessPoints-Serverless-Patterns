# File Portal — Quick Reference Card

> 🌐 Language: **English** | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | [简体中文](../zh-CN/portal-quick-reference.md) | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

One-page cheat sheet for daily portal operations. Print or bookmark this page.

---

## Navigation

| Sidebar Section | What it does |
|:---:|------|
| 📂 All Files | Browse, preview, download, share, AI Q&A |
| ⭐ Favorites | Pinned files |
| 🕐 Recent | Your access history |
| 📤 Upload | Drag-and-drop upload (max 5 GB/file) |
| ⚡ AI Processing | Trigger AI/ML workflows on folders |
| 📋 Job History | Past job results + status |
| 📊 Analytics | Athena SQL queries |
| 📸 Snapshots | Point-in-time copies + FlexClone restore |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | Ransomware protection status |
| 🔧 Resources | Storage admin panels (admin only) |
| 🔄 Version Diff | Compare files across snapshots |
| 🔍 Audit Trail | Who accessed what, when |

---

## Common Tasks (All Users)

| I want to... | Do this |
|-------------|---------|
| Browse files | Sidebar → 📂 All Files → click folders |
| Preview a PDF | Click 📕 next to the file |
| Preview a Word doc | Click 📝 next to the file |
| Download a file | Click 📄 next to the file |
| Share a file link | Click 🔗 → choose TTL → copy URL |
| Ask AI about a file | Select file → type question in right panel |
| Detect objects in image | Select image → "Detect Objects" in right panel |
| Upload files | Sidebar → 📤 Upload → drag & drop |
| Run AI on a folder | In All Files, click ⚡ above file list |
| Check job results | Sidebar → 📋 Job History → click a job |
| Restore from snapshot | Sidebar → 📸 Snapshots → "Restore" button |
| Switch language | Click 🌐 in top bar |

---

## Common Tasks (Compliance / Security)

| I want to... | Do this |
|-------------|---------|
| Check ransomware status | Sidebar → 🛡️ ARP/AI |
| Verify WORM locks | Sidebar → 🔒 Lock → SnapLock tab |
| Check output bucket lock | Sidebar → 🔒 Lock → S3 Object Lock tab |
| View locked snapshots | Sidebar → 🔒 Lock → Tamperproof tab |
| Review access audit | Sidebar → 🔍 Audit Trail |
| Verify PHI guardrail | All Files → navigate to `/dicom/` → button shows 🚫 |

---

## Common Tasks (Storage Admin)

| I want to... | Do this |
|-------------|---------|
| View health dashboard | Sidebar → 🔧 Resources (Dashboard appears first) |
| Manage volumes | Resources → Storage → Volumes |
| Configure export policies | Resources → Access Control → Export Policies |
| Enable ARP on volumes | Resources → Protection → ARP Admin |
| Lock a snapshot | Resources → Protection → Snapshot Admin → Lock form |
| Block a compromised user | Sidebar → 🛡️ ARP/AI → Contain tab → Block SMB User |
| Unblock after resolution | Sidebar → 🛡️ ARP/AI → Unblock tab |
| Check EMS alerts | Resources → (EMS events shown in monitoring) |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Move between interactive elements |
| `Enter` | Activate button / open folder |
| `Escape` | Close modal / dismiss panel |

---

## Status Indicators

| Icon | Meaning |
|:---:|---------|
| 🟢 | Healthy / No threats / Resolved |
| 🔴 | Threat detected / Error |
| 🟠 | Contained (incident in progress) |
| 🟡 | Investigating |
| 🚫 | PHI — AI blocked (guardrail active) |
| ⚠️ | Warning (capacity > 85%, etc.) |

---

## Access Levels

| Group | Can do | Cannot do |
|-------|--------|-----------|
| `authenticated` | Browse, download, upload, AI, view protection | Modify storage config |
| `storage-admin` | Everything above + create/delete volumes, lock snapshots, block users, manage policies | — |

---

## Quick Troubleshooting

| Symptom | Fix |
|---------|-----|
| "ONTAP Connection Required" | Normal in DemoMode. Ask admin to configure VPC. |
| AI button shows 🚫 | You're in a PHI-protected folder. Navigate elsewhere. |
| Share link expired | Generate a new one (🔗). Max TTL = 1 hour. |
| File not showing after NFS write | Refresh file list. Should appear immediately. |
| Loading forever | Check internet. Try sign-out → sign-in. |

---

## Documentation Map

| I am a... | Start here |
|-----------|-----------|
| End user (daily tasks) | [User Guide](portal-user-guide.md) |
| Security / Compliance officer | [Compliance Guide](portal-compliance-guide.md) |
| Storage administrator | [Admin Demo Guide](admin-resource-management-demo.md) |
| IT administrator (deploy) | [Getting Started](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| Developer (customize) | [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
