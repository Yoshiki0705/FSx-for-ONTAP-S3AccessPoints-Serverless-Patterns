# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/Edge (vendor-neutral)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Overview

A vendor-neutral serverless pattern that keeps FSx for NetApp ONTAP as the **single source of truth**
and makes **delivery-approved renditions** on S3 Access Points (S3 AP) deliverable through a CDN/edge
network.

For the technical feasibility comparison across delivery networks (CloudFront / Akamai / Fastly /
Cloudflare / Bunny.net / Google Media CDN, etc.), see **[docs/cdn-comparison.md](../docs/cdn-comparison.md)**.

> This is a reference implementation. Delivery-vendor selection, rights management, geo-restrictions,
> and compliance are the customer's responsibility.

> **TL;DR (30s)**: Without moving the ONTAP/NAS master, deliver **only approved renditions** via CloudFront
> or a third-party CDN. Start with the lowest-risk `PUBLISH_PUSH` (M3). Adopt SigV4 direct pull (ORIGIN_PULL)
> only after measuring it with the [verification checklist](../docs/cdn-origin-verification-checklist.en.md).

## Business outcome & adoption

Evaluate by **business outcome**, not "it deployed".

| Aspect | Outcome / Metric / Measurement |
|---|---|
| Business outcome | Edge delivery without duplicating the master (only approved renditions are copied) |
| Metric | Master objects leaking to the delivery layer = 0 / count of `unrecorded` approvals |
| Measurement | Aggregate `provenance` and `skipped`/`published` from the publish manifest |

- **Safe experimentation boundary**: `DemoMode=true` validates logic without FSx/external CDN.
- **Business sponsor**: assign a delivery owner (media/delivery-platform team) who approves Go/No-Go.
- **Go/No-Go checklist**: no objects outside `ApprovedPrefix` are targeted; approval provenance is recorded;
  viewer tokens work via CDN-native mechanism; for ORIGIN_PULL, SigV4×alias measurement is PASS.
- Frame future work as **evidence expansion** (TBV → measured), not incompleteness.

## Partner/SI guide

- **First customer question**: "Do you want to connect existing NAS/ONTAP assets to edge delivery without
  copying? Is delivery via CloudFront or an existing contracted CDN (e.g. Akamai)?"
- **PoC deliverables**: DemoMode demo → delivery manifest of approved renditions → (optional) hardware SigV4
  verification result. Use the [CDN comparison](../docs/cdn-comparison.en.md) directly in customer conversations.

## Two integration mechanisms

- **ORIGIN_PULL**: No object copy. Generates an origin-reference manifest for a CDN that pulls the S3 AP
  directly via SigV4. CloudFront is supported natively via OAC (reference implementation). SigV4 origin
  signing on third-party CDNs is **to be verified** (see the comparison doc).
- **PUBLISH_PUSH**: Replicates approved renditions to the CDN-side S3-compatible object store. Avoids the
  origin-auth question and is CDN-agnostic — the lowest-risk first step.

## Key components

| Component | Role |
|---|---|
| `functions/publish/handler.py` | Reflects approved renditions to the delivery layer and writes a delivery manifest back to the S3 AP |
| `functions/delivery_log_sync/handler.py` | Normalizes CDN delivery logs (with IP redaction) and writes them back to the S3 AP for correlation with production data |
| Step Functions | Publish → SNS notification |
| CloudFront (optional) | Reference delivery for ORIGIN_PULL (OAC + SigV4) |

## Deploy

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

> **Note**: `template.yaml` is designed for use with SAM CLI (`sam build` + `sam deploy`).
> To deploy with raw `aws cloudformation deploy`, use `template-deploy.yaml` instead (requires pre-packaging Lambda zip files and uploading them to an S3 bucket).

## Security / Governance

- **permission-aware**: Delivery is limited to objects under `ApprovedPrefix`. ACL-controlled master data
  is not delivered directly.
- **Viewer auth**: S3 presigned URLs are unsupported; use CDN-native token mechanisms.
- **PII**: Client IPs are redacted when writing delivery logs back (`RedactClientIp=true`).
- **Least privilege**: Delivery Lambdas run **outside the VPC** for Internet-origin S3 AP access.

> **Governance Note**: Delivery does not enforce ONTAP file permissions. The delivery boundary is enforced
> by the "approved renditions only" operating rule and the delivery target's access controls.

### Responsibilities (RACI / Public Sector lens)

| Role | Responsibility |
|---|---|
| Data Owner | Final accountability for classification, residency, and public-release eligibility |
| Approver | Approves placement under `ApprovedPrefix`; sets approval provenance (approved-by / approval-id) |
| Audit Reviewer | Periodically reviews `provenance` in publish manifests and delivery logs |
| Ops Owner | Receives alarms, handles incidents, executes rollback |

- AI/automated decisions are **assistive signals**; humans (Data Owner / Approver) decide public-release.
- Use **non-sensitive synthetic/sample** data for verification (never repurpose production personal data).
- Technical validation does **not replace** legal/compliance/privacy assessment.

## Operations / Runbook

- **Alarms**: with `EnableCloudWatchAlarms=true`, Lambda errors (publish / log-sync) and Step Functions
  failures notify via SNS (`NotificationEmail`).
- **Triage**: publish errors → check `/aws/lambda/<stack>-publish`; isolate S3 AP authz (IAM + AP policy +
  ONTAP identity) vs external-store auth (Secrets Manager). External push failures → check
  `ExternalStoreSecretName`, endpoint, bucket. Suspected boundary breach → [incident response playbook](../docs/incident-response-playbook.md).
- **Rollback**: delivery only publishes approved renditions; on mis-publish, remove the object from the
  delivery target (CDN store/distribution), withdraw from `ApprovedPrefix`, and re-publish.
- **External-store auth**: for PUBLISH_PUSH to Akamai/R2/Fastly, AWS default credentials do not apply — set
  `ExternalStoreSecretName` (Secrets Manager, `{"access_key_id","secret_access_key"}`).

## Related docs

- [CDN/Edge delivery comparison](../docs/cdn-comparison.en.md)
- [ORIGIN_PULL SigV4 verification checklist](../docs/cdn-origin-verification-checklist.en.md) (hardware procedure)
- [Alternative architecture comparison](../docs/comparison-alternatives.md)
