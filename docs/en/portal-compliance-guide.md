# File Portal — Security & Compliance Officer Guide

> 🌐 **Language / 言語**: [日本語](../ja/portal-compliance-guide.md) | English

A guide for security officers, compliance analysts, and data protection staff who need to **verify** regulatory controls via the portal without performing storage administration. You do not need `storage-admin` privileges — all tasks below use read-only access.

---

## Your Role in the Portal

| What you can do | Where in the portal |
|----------------|-------------------|
| Verify ransomware protection status | Sidebar → 🛡️ ARP/AI |
| Confirm snapshot lock & retention periods | Sidebar → 🔒 Lock |
| Review audit trail (who accessed what) | Sidebar → 🔍 Audit Trail |
| Check PHI guardrail enforcement | Sidebar → 📂 All Files (navigate to `/dicom/` or `/phi/`) |
| Verify S3 Object Lock on output buckets | Sidebar → 🔒 Lock → S3 Object Lock tab |
| View EMS alerts (ONTAP system events) | Admin → Resources (read-only if not `storage-admin`) |

> **Note**: You cannot change configurations (lock settings, ARP state, export policies). If you need changes, request them from a `storage-admin` user.

---

## Task 1: Verify Ransomware Protection (ARP/AI)

**Regulatory context**: FISC, NIST CSF DE.CM-4, ISO 27001 A.12.2

1. Click **🛡️ ARP/AI** in the sidebar
2. Confirm each monitored volume shows a green status (🟢 No threats)
3. If a threat badge appears (🔴), note the volume name and detection timestamp
4. Check the **Incident Lifecycle badge** for current response stage:
   - 🔴 Detected — Threat identified, awaiting containment
   - 🟠 Contained — Attacker access blocked, snapshot preserved
   - 🟡 Investigating — Forensic analysis in progress
   - 🟢 Resolved — Incident closed

**Evidence for auditors**: Screenshot the ARP panel showing all volumes' protection state + any active incident badges with timestamps.

---

## Task 2: Confirm Snapshot Immutability (WORM)

**Regulatory context**: SEC 17a-4, FISC 7-year retention, HIPAA 6-year, SOX 5-year, NARA

1. Click **🔒 Lock** in the sidebar
2. Review three tabs:

### Tab A: ONTAP SnapLock
- Verify volume type: **Compliance** (nobody can delete, including root) or **Enterprise** (admin can release)
- Check retention periods match your policy:
  - Minimum period ≥ regulatory requirement
  - Compliance Clock is initialized and running

### Tab B: S3 Object Lock
- Verify output bucket has Object Lock enabled
- Confirm mode: **Compliance** for regulatory archives, **Governance** for AI output
- Check default retention days match your requirement

### Tab C: Tamperproof Snapshots
- Review locked snapshots table: name, creation time, expiry time
- Verify expiry dates align with regulatory retention:

| Regulation | Required Retention | Expected Expiry |
|-----------|-------------------|-----------------|
| FISC | 7 years (2,557 days) | Creation + 7 years |
| HIPAA | 6 years (2,192 days) | Creation + 6 years |
| SOX/J-SOX | 5 years (1,825 days) | Creation + 5 years |
| NARA | 3-75 years (varies) | Per records schedule |

**Evidence for auditors**: Screenshot each tab showing lock status + retention periods.

---

## Task 3: Review Audit Trail

**Regulatory context**: FISC, SOX Section 302/404, HIPAA §164.312(b), PCI DSS 10.x

1. Click **🔍 Audit Trail** in the sidebar
2. The panel shows CloudTrail S3 data events for the S3 Access Point
3. Key fields to review:
   - **Who**: IAM principal (Cognito user identity)
   - **When**: Event timestamp (UTC)
   - **What**: API action (`GetObject`, `PutObject`, `ListObjectsV2`)
   - **Which file**: S3 key (file path)
4. Filter by date range or user if investigating a specific incident

**Evidence for auditors**: Export or screenshot the audit trail filtered to the review period.

---

## Task 4: Verify PHI Guardrail

**Regulatory context**: HIPAA §164.502 (minimum necessary), 45 CFR 164.514

1. Click **📂 All Files** in the sidebar
2. Navigate into a folder named `/dicom/`, `/phi/`, `/pii/`, or `/hipaa/`
3. Observe the AI processing button shows: **🚫 PHI — AI Blocked**
4. Verify the button is disabled (cannot be clicked regardless of user role)

**What this means**: Files in these protected paths are structurally prevented from being sent to external AI services (Bedrock, Rekognition, Textract, Comprehend). This is enforced at the UI layer via path-pattern matching and cannot be overridden by any user.

**Limitation**: This guardrail depends on folder naming conventions. Files with PHI content placed in non-protected paths are NOT blocked. Ensure organizational folder structure policies are enforced upstream.

**Evidence for auditors**: Screenshot showing the disabled AI button in a `/dicom/` folder.

---

## Task 5: Verify S3 Object Lock on AI Output

**Regulatory context**: SEC 17a-4(f), CFTC 1.31, FINRA 4511

1. Click **🔒 Lock** → **S3 Object Lock** tab
2. Verify:
   - Object Lock is **Enabled** on the output bucket
   - Mode is appropriate: **Compliance** (immutable) or **Governance** (override with permission)
   - Default retention period matches your retention schedule
3. If Object Lock is not configured, escalate to a `storage-admin` user

**Why this matters**: AI processing results (classification labels, extracted text, compliance reports) stored in S3 may themselves be regulatory records. Object Lock ensures these outputs cannot be altered or deleted during the retention period.

---

## Task 6: Incident Response Verification

When a ransomware incident is detected:

1. Go to **🛡️ ARP/AI** → check incident badge state
2. Verify containment was executed:
   - Snapshot taken (preserved evidence)
   - Suspect user/IP blocked
3. Go to **🔍 Audit Trail** → filter events around the detection timestamp
4. Document the timeline: detection time → containment time → investigation start
5. After resolution, verify the incident badge shows 🟢 Resolved

**Incident timeline SLA reference**:

| Phase | Typical Duration | Your SLA |
|-------|:---:|:---:|
| Detection → Containment | < 5 minutes (automated) | _____ |
| Containment → Investigation start | < 1 hour | _____ |
| Investigation → Resolution | Case-dependent | _____ |

---

## Regulatory Mapping

| Portal Feature | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|---------------|:---:|:---:|:---:|:---:|:---:|
| ARP/AI ransomware detection | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (Compliance mode) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| PHI Guardrail | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| Incident Lifecycle tracking | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## What You Cannot Do (and Who Can)

| Action | Required Group | Who to Contact |
|--------|:---:|------|
| Change ARP/AI state | `storage-admin` | Storage administrator |
| Lock/unlock snapshots | `storage-admin` | Storage administrator |
| Configure S3 Object Lock | `storage-admin` | Storage administrator |
| Block/unblock users (containment) | `storage-admin` | Security operations + storage admin |
| Create/delete volumes | `storage-admin` | Storage administrator |
| Modify export policies | `storage-admin` | Storage administrator |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [User Guide](portal-user-guide.md) | End-user daily operations |
| [Authorization Model](portal-authorization-model.md) | Full permission matrix |
| [Admin Demo Guide](admin-resource-management-demo.md) | Storage admin operations |
| [Incident Response Playbook](../../docs/incident-response-playbook.md) | Full incident response procedures |
| [Quick Reference Card](portal-quick-reference.md) | 1-page cheat sheet |
| [PoC → Production Guide](portal-poc-to-production.md) | Production deployment checklist (audit trail, MFA, secrets) |
| [Accessibility Statement](portal-accessibility.md) | WCAG compliance and assistive technology support |
