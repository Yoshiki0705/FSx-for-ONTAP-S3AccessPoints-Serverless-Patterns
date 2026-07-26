# Round 4 — Expert Persona Review (ONTAP System Manager UX + SRE/DevOps)

> 30 world-class expert personas review the portal for immediate business value delivery.
> Focus: "How can someone in MY role use this TODAY to solve a real problem?"
> Vendor neutrality enforced throughout.

---

## Category A: ONTAP System Manager UX Experts (1-10)

### 1. ONTAP System Manager Product Designer
**Insight**: System Manager uses a "dashboard first" pattern — the home page shows health status of all components at a glance (volumes, aggregates, network, protection). This portal's home page is a file browser. Add a **Storage Health Dashboard** as the default admin landing page showing: volume capacity %, ARP threats, locked snapshot count, replication lag.
**Action**: Create `StorageDashboard.tsx` with 4 summary cards pulling from existing API calls.

### 2. Storage Workflow UX Researcher
**Insight**: System Manager never requires users to know UUIDs or internal names — it auto-discovers and presents human-readable labels. The portal's `portal-config.ts` requires manual SVM/volume name input. Add a **"Discover My Environment"** button that calls `setup-prerequisites.sh` logic from the browser (via Lambda).
**Action**: Add `discoverEnvironment` Lambda action that returns SVM list, volume list, S3 AP list.

### 3. Enterprise Storage Console Architect
**Insight**: System Manager shows operation history (who changed what, when) inline next to each resource. The portal has Audit Trail as a separate section but no inline "last modified by" on volumes/shares. Add **last-modified metadata** to list views.
**Action**: Include `modify_time` from ONTAP REST in listVolumes/listCifsShares responses.

### 4. Data Protection Visualization Designer
**Insight**: System Manager shows protection topology as a visual graph (source → mirror → vault). The Lock panel shows text status only. Add a simple **protection timeline** showing: "Created → Locked → Expires in X days" for each locked snapshot.
**Action**: Calculate and display days-until-expiry in the locked snapshots table.

### 5. Multi-Protocol Access Pattern Expert
**Insight**: The dual-access demo script exists but is CLI-only. System Manager shows protocol access statistics (NFS ops/sec, SMB sessions, S3 requests). Add a **protocol activity summary** to the file browser header showing which protocols are active.
**Action**: Document as future enhancement (requires ONTAP performance counters API).

### 6. Storage Efficiency Visualization Specialist
**Insight**: System Manager shows savings as a comparison bar (logical vs physical). The portal shows a ratio number only. Add a **visual savings bar** (e.g., "Using 80GB physical for 100GB logical = 20% saved") with color coding.
**Action**: Add CSS bar visualization to StorageEfficiency component.

### 7. Alert/Event Integration Designer
**Insight**: System Manager has an event log with severity levels (Critical/Warning/Info) filterable by component. The portal's audit trail is file-access only. Consolidate **ONTAP EMS events + CloudTrail** into a unified event timeline.
**Action**: Document as future enhancement (EMS requires ONTAP REST `/support/ems/events`).

### 8. Snapshot Management UX Lead
**Insight**: System Manager allows snapshot comparison (diff between two snapshots). The portal has "Version Diff" in the nav but the actual diff implementation is basic. Ensure the **snapshot diff shows file-level changes** (added/modified/deleted) between two points in time.
**Action**: Already implemented via FlexClone comparison. Verify in demo guide.

### 9. Quota Management Interaction Designer
**Insight**: System Manager shows quota usage with traffic-light indicators (Green <80%, Yellow 80-95%, Red >95%). The portal shows numbers only. Add **color-coded capacity badges** to quota display.
**Action**: Add CSS classes for quota thresholds in QuotaManager.

### 10. RBAC/Security Posture Designer
**Insight**: System Manager has a security dashboard showing compliance posture (FIPS, TLS versions, certificate expiry). The portal has no equivalent. Add a **Security Posture card** to the admin overview showing: encryption status, certificate validity, access policy count.
**Action**: Document as future enhancement (requires ONTAP `/security` endpoints).

---

## Category B: SRE/DevOps World-Class Experts (11-20)

### 11. Google SRE (Golden Signals Expert)
**Insight**: The portal has ZERO observability into its own health. No latency/traffic/errors/saturation metrics. Add **4 Golden Signals** as a meta-dashboard: Lambda p99 latency, request rate, error rate, DynamoDB consumed capacity.
**Action**: Add CloudWatch dashboard template (JSON) + link from admin panel.

### 12. Netflix Chaos Engineer
**Insight**: No failure injection or resilience testing. What happens when ONTAP is unreachable for 5 minutes? The portal shows "ONTAP connection required" gracefully (good), but does it cache last-known state? Add **stale-data indicator** when API calls fail but cached data exists.
**Action**: Document pattern in IMPLEMENTATION.md. Actual caching is future work.

### 13. Spotify Platform Engineer (Developer Experience)
**Insight**: `npm start` is excellent DX. But there's no `npm run validate` that checks portal-config.ts values against the actual AWS environment before deploying. Add a **pre-deploy validation** step.
**Action**: `scripts/setup-prerequisites.sh` already validates. Add `npm run validate` script alias.

### 14. Datadog Observability Architect
**Insight**: No structured logging in Lambda functions (just `logger.info`). Switch to **JSON structured logs** with consistent fields (action, userId, duration_ms, status) for easier querying in CloudWatch Insights.
**Action**: Document as tech debt. Lambda handlers already log action/userId.

### 15. HashiCorp Infrastructure-as-Code Specialist
**Insight**: The portal uses Amplify Gen2 CDK — not standalone Terraform/CloudFormation. For teams that DON'T use Amplify, provide a **standalone CloudFormation template** that deploys just the VPC Lambdas + AppSync API without the Amplify framework.
**Action**: Document as alternative deployment path in GETTING-STARTED.md.

### 16. PagerDuty Incident Response Designer
**Insight**: ARP/AI containment is one-click but has no **post-incident workflow** — no "create incident ticket", no "assign to on-call", no "track resolution". Add incident lifecycle state (Detected → Contained → Investigating → Resolved) to the ARP panel.
**Action**: Document incident workflow states. Actual implementation requires SNS + external ticketing.

### 17. AWS Well-Architected Review Lead
**Insight**: The Well-Architected review is self-assessed. For credibility, run the actual **AWS Well-Architected Tool** (in console) and include the workload ID for readers to reference.
**Action**: Document recommendation in well-architected-review.md footer.

### 18. GitOps / ArgoCD Practitioner
**Insight**: `npx ampx sandbox` is imperative. For production, teams want **declarative GitOps** — push to branch triggers deploy. Document how to set up Amplify Hosting CD pipeline (branch-based deploys).
**Action**: Add section to GETTING-STARTED.md on `amplify deploy` with GitHub branch triggers.

### 19. Prometheus/Grafana Monitoring Expert
**Insight**: CloudWatch is AWS-native but many teams use Prometheus + Grafana. Provide **CloudWatch Metric Stream → Prometheus** pattern for teams using open-source observability.
**Action**: Brief note in observability section of docs.

### 20. Kubernetes Platform Engineer
**Insight**: The portal runs on Lambda/AppSync, but some teams want to run on EKS. The React frontend can be containerized trivially. Document a **container deployment alternative** (Docker build + EKS/Fargate).
**Action**: Add `Dockerfile` for the frontend (Vite build → nginx serve).

---

## Category C: Business Value Delivery Experts (21-30)

### 21. Management Consultant (McKinsey Digital)
**Insight**: The README/blog focuses on technical "how" but lacks a clear **business case one-pager**: "Before this portal: 4 hours to process 1000 contracts manually. After: 15 minutes with AI + human review for edge cases." Add a quantified value statement.
**Action**: Add "Business Value" section to README with time-savings calculation.

### 22. Product Manager (B2B SaaS)
**Insight**: No **user onboarding flow** in the portal itself. First-time users land on a file browser with no guidance. Add a "Welcome" modal or guided tour (3 steps) on first login.
**Action**: Document as UX enhancement. Implement in future sprint.

### 23. Chief Information Security Officer (CISO)
**Insight**: The production checklist covers individual items but lacks a **security sign-off template**. CISOs need a one-page summary: "These are the security controls in place, these are the residual risks, this is the acceptance criteria." Add a security review template.
**Action**: Create `docs/en/security-review-template.md`.

### 24. Data Governance Officer
**Insight**: Data classification labels (INTERNAL/CUI/PUBLIC) are in `shared/data_classification.py` but the portal UI doesn't show them to end users. When browsing files, show a **classification badge** next to file names.
**Action**: Document as future feature (requires metadata enrichment at S3 AP level).

### 25. Compliance Program Manager (ISO 27001)
**Insight**: ISO 27001 requires documented **Access Review** procedures. The portal has auth but no "show me who has access to what" admin view. Add a **user access report** (Cognito users × groups → permissions matrix).
**Action**: Document as future enhancement. Cognito ListUsers API available.

### 26. Enterprise Sales Engineer (Partner SI)
**Insight**: The Getting Started guide assumes CLI comfort. Many SI field engineers prefer **click-through setup in AWS Console**. Add a "Console-Based Setup" alternative with screenshots of each AWS Console step.
**Action**: Document as alternative path (lower priority — CLI is faster and more reproducible).

### 27. Financial Controller (FinOps)
**Insight**: The cost calculator shows monthly estimates but doesn't show **cost per operation** (how much does one AI processing job cost?). Break down: "Processing 1 PDF contract = ~$0.003 (Lambda) + $0.002 (Bedrock Nova Lite) = $0.005 per file."
**Action**: Add per-operation cost table to cost-measurement.md.

### 28. Open Source Community Maintainer
**Insight**: The repo has MIT license but no **CONTRIBUTING.md** or issue templates. OSS contributors don't know how to participate. Add contribution guidelines and good-first-issue labels.
**Action**: Create CONTRIBUTING.md with PR workflow, code style, and issue template.

### 29. Technical Writer (Developer Relations)
**Insight**: The blog is comprehensive (25 min read) but lacks a **TL;DR architecture diagram** at the top. Add a single visual (already exists in docs/diagrams/) as the first image in the blog.
**Action**: Ensure blog references the architecture diagram file from docs/diagrams/.

### 30. Startup CTO (Move Fast)
**Insight**: "I have 30 minutes. Show me the fastest path to value." The DemoMode path is good but buried. Make **DemoMode the FIRST thing in README** — not "Prerequisites" → "Clone" → "Configure". Instead: "Run this ONE command to see it work, THEN read about configuration."
**Action**: Update portal README.md to lead with DemoMode one-liner.

---

## Immediate Actions (This Session)

Based on the 30 reviews, the highest-impact items executable NOW:

| # | Action | Time | Impact |
|---|--------|------|--------|
| 1 | Add `npm run validate` script alias | 1 min | DX |
| 2 | Add per-operation cost to cost-measurement.md | 3 min | FinOps clarity |
| 3 | Create CONTRIBUTING.md | 5 min | OSS adoption |
| 4 | Add Dockerfile for container deployment | 3 min | K8s teams |
| 5 | Update persona-review doc with Round 4 results | Done | Tracking |

**Deferred (future sessions):**
- StorageDashboard.tsx (new component)
- Incident lifecycle states
- Security review template
- Welcome modal / onboarding flow
- Console-based setup guide

**Rejected (vendor neutrality):**
- None of the suggestions violated neutrality in this round.
