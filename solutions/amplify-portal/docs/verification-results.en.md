# File Portal — Verification Results

🌐 **Language / 言語**: [日本語](verification-results.md) | **English**

**English** | [日本語](verification-results.md)

This document records **how far each portal feature has been verified against a real system**. Its purpose is to keep "verified on real hardware" clearly separate from "the tests pass".

> **Why the distinction matters**: "the tests pass" is not the same as "it works in production". Unit tests exercise handler logic; they do not exercise the actual shape of an ONTAP REST response, AppSync authorization, VPC reachability, or Cognito group propagation. Calling an unverified feature "verified" hides exactly the places a PoC breaks first.

## Verification Levels

| Level | Meaning |
|-------|---------|
| **Live E2E** | Driven from the browser against a real FSx for ONTAP, with the expected result observed |
| **Live read** | Listing and reading confirmed against a real system; write or change operations not confirmed |
| **Tests only** | Unit and component tests pass; no operation confirmed against a real system |
| **DemoMode only** | Rendering and error handling confirmed with no FSx for ONTAP connection |

## Environment

| Item | Value |
|------|-------|
| Region | ap-northeast-1 |
| ONTAP version | 9.17.1 |
| File system ID | `fs-0123456789abcdef1` (placeholder) |
| Verified on | 2026-07-26 (admin panels), 2026-08-07 (additions from this session) |

## Live E2E

| Feature | What was confirmed | Source |
|---------|-------------------|--------|
| FlexCache create / list / delete | Async creation with progressive refresh, origin display in the list, 3-step delete (unmount → offline → delete) | [admin-resource-management-demo](../../../docs/en/admin-resource-management-demo.md) Scenario 15 |
| AppSync authorization | Admin endpoints allowed and refused by the `storage-admin` Cognito group; working after a password reset | [TROUBLESHOOTING-APPSYNC-AUTH.md](TROUBLESHOOTING-APPSYNC-AUTH.md) |
| File Explorer listing | 29 directories shown from the S3 Access Point | Same guide, results table |
| SMB share encryption toggle | ON / OFF switching and state reflection | Same guide, Scenario 6 |
| Export policy create / delete | Policy creation, rule addition, deletion | Same guide, Scenario 7 |

## Live read (write paths not confirmed)

| Feature | Confirmed | Not confirmed |
|---------|-----------|---------------|
| SnapMirror | Relationship listing, state badges, lag display | sync / break / resync / quiesce / delete / **transfer abort** |
| Volumes | 9 volumes listed with capacity | create / resize / delete |
| Storage Efficiency | 1.21x ratio, 17.7% savings across 9 volumes | (read-only feature) |
| Snapshot management | Policy listing, tamperproof status query | performing a lock |
| ARP/AI | State of 9 volumes (all disabled) | bulk enable, threat containment |
| SnapLock | All volumes non_snaplock | WORM configuration (**irreversible — deliberately not exercised in a verification environment**) |
| Qtrees / Quotas | VolumeSelector integration and listing | create / delete |
| Local Users / Name Mapping | Listing | create / delete |
| FPolicy / Vscan | Three-tab rendering | policy configuration |

> **Why SnapLock is not exercised here**: unexpired WORM files block deletion of the volume, then the SVM, then the **file system**. If an audit log volume is created, the file system cannot be deleted for at least six months. See [Tamperproof Snapshot Design](../../../docs/tamperproof-snapshot-design.md).

## Tests only (no operation confirmed against a real system)

These are the features made reachable in this session (2026-08-07). Handler and component tests pass; none has been driven from a browser against a real system.

| Feature | Tests | What to confirm on real hardware |
|---------|-------|----------------------------------|
| SnapMirror transfer abort | Unit coverage of the `SnapMirrorStatus` path | Whether ONTAP accepts the `state=aborted` PATCH, and the state transition after aborting |
| File rename / trash / restore | `FileLifecycle.test.tsx`, 13 tests | Real CopyObject + DeleteObject behaviour on the S3 AP, and how long it takes for large files |
| Upload link | Same | Whether the presigned PUT URL actually writes through the S3 AP (**signature v4 is required**) |
| Agent and team execution | `functions/agent-chat/tests/`, 21 tests | Bedrock invocation, the tool intersection, authorization of shared agents |
| Editing an agent definition | `AgentDirectory.test.tsx`, 9 tests | The DynamoDB partial update, and refusal for anyone but the creator |
| Glue catalog browser | `CatalogBrowser.test.tsx`, 8 tests | Databases / tables / columns after a Glue Crawler has run |
| Document text extraction and analysis | `DocumentAnalysis.test.tsx`, 8 tests | Real Textract / Comprehend responses, and whether a cross-region call is needed |
| AI metadata badges | `AiMetadataBadges.test.tsx`, 9 tests | Rendering with real rows in the AI metadata table |
| EMS event display | Generated-type agreement only | The real shape of an EMS event response |
| QR code generation | Same | Whether the generated QR reaches the presigned URL |
| Folder watch / event notifications | `functions/list-files/tests/test_notifications.py`, 9 tests | Real delivery from FPolicy through EventBridge to the bridge Lambda, the shape of real events, and the group boundary filter |

### Test totals

| Suite | Count |
|-------|-------|
| Portal components and utilities (vitest) | 177 |
| `functions/resource-management` (pytest) | 213 |
| `functions/list-files` (pytest) | 9 |
| `functions/agent-chat` (pytest) | 21 |
| Dispatch contract checks (`make drift`) | 150 call sites / 155 actions |

## DemoMode only

| Feature | Scope |
|---------|-------|
| Vscan setup guidance | Five-step guidance, six-vendor comparison table, external links |
| S3 Object Lock tab | Renders without an ONTAP connection |
| Admin panels generally (no ONTAP) | Graceful "ONTAP Connection Required" state |

## Recorded deployment times

The recorded deploy times disagree across documents. Rather than averaging them, here is why they differ.

| Item | Recorded | Source | Condition |
|------|----------|--------|-----------|
| `npx ampx sandbox`, first run | 3-5 min | [README](../README.md) | no VPC (DemoMode) |
| `npx ampx sandbox`, first run | 8-12 min | [pr-ephemeral-environments.md](pr-ephemeral-environments.md) | — |
| `make sandbox`, first run | 10-15 min | [cleanup-guide.md](cleanup-guide.md) | includes CDK bootstrap |
| `npx ampx sandbox`, incremental | 2-3 min | [pr-ephemeral-environments.md](pr-ephemeral-environments.md) | — |
| `npm run build` | 0.25-0.51 s | measured in this session | Vite |

> **Why they differ**: a Lambda in a VPC spends time creating and deleting ENIs and is not eligible for hotswap. Adding VPC configuration turns every change into a full deploy and pushes the first run past ten minutes ([amplify-gen2-cdk-patterns.md](amplify-gen2-cdk-patterns.md), case 2). Without a VPC, DemoMode is 3-5 minutes. An unbootstrapped CDK environment adds more on top.

| Item | Behaviour |
|------|-----------|
| Lambda Layer content change | **Skipped by hotswap**. Requires `ampx sandbox delete` then redeploy, or a pipeline deploy |

> **Lambda Layer caveat**: changing `shared/` updates the Lambda by hotswap and skips the LayerVersion content change (there is no flag to disable hotswap). Recreate the sandbox to be certain the change is live.

## Not yet verified

- Throughput sharing under production-like load (concurrent NFS / SMB / S3 AP access)
- Multi-tenancy (per-Cognito-group S3 AP routing) against a real system
- External IdP (SAML / OIDC) federation
- A full SnapMirror DR failover sequence (break → promote → resync)
- S3 AP data operations on an AD-joined SVM, which depend on AD DC reachability

## Related Documents

| Document | Contents |
|----------|----------|
| [Admin Resource Management — Demo Guide](../../../docs/en/admin-resource-management-demo.md) | The 26 scenarios |
| [PoC to Production Guide](../../../docs/en/portal-poc-to-production.md) | Moving from DemoMode to a real connection |
| [ONTAP Connection Guide](ONTAP-CONNECTION-GUIDE.md) | VPC, secret and management LIF configuration |
| [AppSync Authorization Troubleshooting](TROUBLESHOOTING-APPSYNC-AUTH.md) | When group authorization fails |
