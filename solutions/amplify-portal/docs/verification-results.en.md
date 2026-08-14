# File Portal — Verification Results

🌐 **Language / 言語**: [日本語](verification-results.md) | **English**

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
| ONTAP version | 9.17.1 (for the 2026-07-26 and 08-07 checks), 9.18.1P3D1 (for the 2026-08-14 checks) |
| File system ID | `fs-0123456789abcdef1` (placeholder) |
| Verified on | 2026-07-26 (admin panels), 2026-08-07 (reads and reachability), 2026-08-14 (writes) |

> **Why there are two versions**: the verification environment's ONTAP was updated after 07-26.
> Entries that record an error code or a field behaviour name the version they were observed on
> ([volume lifecycle pitfalls](../../../docs/agent/pitfalls-volume-lifecycle.md),
> [FlexCache / SnapMirror pitfalls](../../../docs/agent/pitfalls-flexcache-snapmirror.md)).

## Live E2E

| Feature | What was confirmed | Source |
|---------|-------------------|--------|
| FlexCache create / list / delete | Async creation with progressive refresh, origin display in the list, 3-step delete (unmount → offline → delete) | [admin-resource-management-demo](../../../docs/en/admin-resource-management-demo.md) Scenario 15 |
| AppSync authorization | Admin endpoints allowed and refused by the `storage-admin` Cognito group; working after a password reset | [TROUBLESHOOTING-APPSYNC-AUTH.md](TROUBLESHOOTING-APPSYNC-AUTH.en.md) |
| File Explorer listing | 29 directories shown from the S3 Access Point | Same guide, results table |
| SMB share encryption toggle | ON / OFF switching and state reflection | Same guide, Scenario 6 |
| Export policy create / delete | Policy creation, rule addition, deletion | Same guide, Scenario 7 |
| ONTAP failure classification | On a real environment whose credentials were refused, confirmed the UI shows `CREDENTIALS_REJECTED`, HTTP 401 and the ONTAP error code. After bringing the two passwords into agreement, confirmed the same panel lists 13 snapshots (both states captured as screenshots) | [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md#what-the-screen-shows) |
| `make ontap-preflight` | All six stages run against a real environment: stages 1-5 PASS and stage 6 FAIL before the repair, every stage PASS after. Verified on **the case it exists for** — only stage 6 failing | Same guide |

### Added 2026-08-14 (write paths, ONTAP 9.18.1P3D1)

Each was executed against the real system, and every probe resource created for it was removed
afterwards. The observed error codes and field values are recorded in the pitfalls documents.

| Feature | What was confirmed | Source |
|---------|-------------------|--------|
| Volume create / resize / delete | Creation asks for placement in two steps, `style` and an aggregate (787140 / 918242). Deletion is unmount → offline → delete, and both the offline and the delete jobs have to be waited on (524546). **All three were listed as unconfirmed before this** | [volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| FlexCache write-back on / off | At creation and switched on an existing cache. Deleting a cache with write-back still on is refused synchronously on the DELETE (66846980) | [FlexCache / SnapMirror](../../../docs/agent/pitfalls-flexcache-snapmirror.md) |
| FlexCache resize | 100 → 50 → 100 GiB. Being a FlexGroup, both directions run past a 10s job wait. The creation floor does not bound a shrink | Same, and [demo guide](resource-management-demo-guide.en.md) Scenario 4 |
| SnapMirror relationship create / delete | Destination volume provisioned and initialized in one POST. `create_destination.tiering.supported` and `state: snapmirrored` are both required | [FlexCache / SnapMirror](../../../docs/agent/pitfalls-flexcache-snapmirror.md) |
| SnapMirror quiesce / resume | Both returned a real job UUID and answered after the job succeeded; the relationship returned to `snapmirrored` / healthy | Same |
| SVM peer create attempt / change applications | `applications` is per-use: a `peered` peer without `snapmirror` is refused (`SVM peer permission not found.`), and `PATCH /svm/peers/{uuid}` resolves it | Same |
| Qtree create / edit / rename / delete | Security style change, rename (the id does not change, `confirm` required), create and delete, all from the UI | [demo guide](resource-management-demo-guide.en.md) Scenario 14 |
| Quota rule limit change | All three limits on a tree quota changed and restored. Over REST this applies without a resize | [admin-capability-map](admin-capability-map.en.md) |
| Quota enforcement on / off (per volume) | The field written is `quota.enabled`, the field read is `quota.state`. ONTAP refuses to switch it on for a volume with no rules | [volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| Local user create / edit / delete | Password change and enable/disable (`account_disabled`, 262179). Confirmed **the SID does not change** | Same |
| Name mapping create / edit / delete / move | `new_index` renumbers the rules in between; DELETE does not | Same |
| EMS event retrieval | **Worked only after a fix**: both `fields=severity` and the `severity=` filter are refused with 262197, and `message.severity` is what ONTAP takes. Every call had failed before this | [ARP/AI and EMS](../../../docs/agent/pitfalls-arp-ems.md) |
| ARP/AI state change | Asking for `dry_run` leaves the volume `enabled` -- ARP/AI has no learning period. Turning it off stayed `disable_in_progress` for over ten minutes. The response now carries the state read back, not the request | Same |
| Scope on the data-protection pages (SVM → volume) | The ARP, Lock and Snapshot pages were pinned to the one volume in an environment variable. The storage-admin group now gets a two-step `SVM › volume` selector; everyone else keeps the default. Verified live that the listing changes for a volume on fsxsvm02, and that changing SVM voids the selection. The badge beside the heading distinguishes a picked volume from the configured default | Same |

### Added 2026-08-15 (write paths, group A, ONTAP 9.18.1P3D1)

A3, A2 and A5 of the verification plan. Every group, user, share, qtree and quota rule
created for it was deleted afterwards and the environment is back as it was.

| Feature | Confirmed | Source |
|---------|-----------|--------|
| Local group create / delete (A3) | The SID is allocated from the SVM's local domain (ending -1001). A delete without `sid` is refused by the handler | [Demo guide](resource-management-demo-guide.en.md) |
| Group member add / remove (A3) | Adding accepts the bare name `zz_verify_usr`, while the listing returns the CIFS-server-qualified `FSXSVM01\zz_verify_usr`. Removal accepts **either form** (the handler percent-encodes the backslash) | Same |
| Name resolution failure (A3) | An unresolvable name gives the same message whether it is an AD user with no reachable DC or a local name that does not exist: `Failed to resolve name "X".` (655673 / 400). **The message alone cannot distinguish a typo from DC reachability** | Same |
| SMB share create / delete (A2) | A path that does not exist is refused with 655551, naming the SVM. A created share carries one default ACL. Deletion requires `confirm=true` on the portal side. **The volume stays online after the share is deleted** -- a share is only an entry point | Same |
| SMB share encryption toggle (A2) | `updateCifsShare` on and off, reflected in the listing immediately | Same |
| Quota rule deletion (A5) | Creating a tree rule for a qtree makes ONTAP **also create the volume's default tree rule** (empty qtree name). Deleting only the qtree rule leaves that default behind, so the qtree keeps appearing in the usage report and the deleted rule looks like it is still there. The deleted rule's limits leave the report immediately, without waiting for enforcement to be switched off and on. **Whether enforcement itself continues is not observable through these two reads** | [Delete a quota policy rule](https://docs.netapp.com/us-en/ontap-restapi-9171/delete-storage-quota-rules-.html) |
| Quota enforcement and the usage report (A5) | Switching enforcement off empties the report; switching it back on repopulates it | Same |
| Eight file operations (A7) | `createFolder`, `createUploadLink`, `copyFile`, `renameFile`, `moveFile`, `trashFile`, `restoreFromTrash`, `deleteFileForever` run end to end, along with the refusals: silent overwrite, permanent delete outside the trash, and the missing acknowledgement | [S3 AP pitfalls](../../../docs/agent/pitfalls-s3ap-ontap.md) |
| Upload link (A7) | **Worked only after a fix.** `generate_presigned_url` defaults to SigV2 for presigning (`AWSAccessKeyId`, `Signature`) and signs against the global endpoint, so the PUT failed with 301 PermanentRedirect naming the regional one -- which the signature cannot follow, because it covers `host`. Both `signature_version="s3v4"` and `addressing_style="virtual"` are needed; v4 alone leaves the host global. After the fix: HTTP 200, and the 27-byte object appears in the listing | Same |
| Copies over 5 GiB (A7) | **Not verified, because the precondition cannot be created here**: exceeding 5 GB requires a multipart upload, which is the very call that fails on this Access Point. A guard was added instead -- the size is read before copying and the refusal names it and the reason (unit tests only; not confirmed against a real object over 5 GiB) | Same |
| Deleting a folder (A7) | **Not possible.** `createFolder` exists, but `trashFile` refuses folders (copying the marker would orphan the contents) and `deleteFileForever` is confined to `.trash/`. A folder created through the UI cannot be removed through it | Same |

## Live read (write paths not confirmed)

| Feature | Confirmed | Not confirmed |
|---------|-----------|---------------|
| SnapMirror | Relationship listing, state badges, lag display (create, delete, quiesce and resume are in the table above) | update now / break / resync / transfer abort |
| Storage Efficiency | 1.21x ratio, 17.7% savings across 9 volumes | (read-only feature) |
| Snapshot management | Policy listing, tamperproof status query | performing a lock; creating, assigning and deleting policies |
| ARP/AI | State of 9 volumes (all disabled) | state change / bulk enable / clear suspects / threat containment |
| SnapLock | All volumes non_snaplock | WORM configuration (**irreversible — deliberately not exercised in a verification environment**) |
| QoS | Policy listing (none exist in this environment) | create / update / delete / assign to a volume |
| SMB shares | Four shares listed, encryption toggle | creating and deleting a share |
| Local groups | Listing | create / delete / add and remove members |
| FlexClone | Listing | create / split |
| FPolicy / Vscan | Three-tab rendering | policy configuration (an external engine is a prerequisite) |
| Cluster peers | Peer listing, intercluster LIF listing | create / accept / delete (work on the remote cluster is required) |
| Cluster information | Nodes, licences, LIFs, protocols, DNS and jobs listed | disabling a LIF or a protocol, updating DNS |

> **Why SnapLock is not exercised here**: unexpired WORM files block deletion of the volume, then the SVM, then the **file system**. If an audit log volume is created, the file system cannot be deleted for at least six months. See [Tamperproof Snapshot Design](../../../docs/tamperproof-snapshot-design.md).

## Writes not yet run, grouped by reason

Kept as one list, "not yet run" mixes work that only needs doing in order with work that cannot
be done for want of a prerequisite and work that is deliberately never done. This splits it by
whether it can be run at all. The prerequisites, procedure, impact and rollback for each
operation are in the [write verification plan](write-verification-plan.en.md).

| Group | Operations | Decision |
|-------|-----------|----------|
| **A. Safe to run (not yet done)** | QoS ×4, SMB share create and delete, local groups and members ×4, FlexClone create and split, quota rule delete, SnapMirror update-now and transfer abort, file operations ×8, ARP dry_run | Work through them in order. Split and transfer abort have prerequisites of their own (see the plan) |
| **B. No external prerequisite** | Vscan ×4, FPolicy ×5, cluster peer ×3, SVM peer accept and delete | An external scan engine, an FPolicy engine, or an accept on the remote cluster is required. FPolicy may be reachable with `engine: native` |
| **C. Irreversible, so not run** | SnapLock retention, snapshot locking, performing a lock, S3 Object Lock retention, snapshot policy create and assign | Unexpired WORM blocks deletion of the volume, then the SVM, then the **file system**. This stays as it is |
| **D. Affects the shared environment** | Disabling a LIF, disabling a protocol service, DNS update, SnapMirror break / resync, the six containment actions | These cut a path, a session or a replication relationship. Decide the target and the window first |
| **E. Not ONTAP** | Agents / teams / sessions, portal settings, thumbnails | Bedrock, DynamoDB and S3. Not real-hardware ONTAP verification |

> **Two findings the documentation review produced before anything was run** (recorded here so
> they are not a surprise during execution)
>
> - **The portal has no way to unassign a QoS policy.** ONTAP refuses to delete a policy group
>   that is in use unless `-force` is given, and `assignQosToVolume` requires a `policyName`, so
>   there is no "set it to none". Create → assign → delete therefore cannot complete.
> - **Deleting a quota rule leaves it enforced** until enforcement is switched off and on again
>   for that volume — stated in ONTAP's REST reference as the DELETE response. The portal reports
>   only success and does not point at the next step, which it now could: the enforcement toggle
>   exists.

## Tests only (no operation confirmed against a real system)

These are the features made reachable as of 2026-08-07. Handler and component tests pass; none has been driven from a browser against a real system.

| Feature | Tests | What to confirm on real hardware |
|---------|-------|----------------------------------|
| SnapMirror transfer abort | Unit coverage of the `SnapMirrorStatus` path | Whether ONTAP accepts the `state=aborted` PATCH, and the state transition after aborting. **An abort fails unless a transfer is in flight**, so a transfer long enough to catch has to be arranged first |
| File rename / trash / restore | `FileLifecycle.test.tsx`, 13 tests | Real CopyObject + DeleteObject behaviour on the S3 AP, and how long it takes for large files. **An object over 5 GB cannot be copied in a single CopyObject**, and the alternative, `UploadPartCopy`, answers `NoSuchKey` in this environment |
| Upload link | Same | Whether the presigned PUT URL actually writes through the S3 AP (**signature v4 is required**) |
| Agent and team execution | `functions/agent-chat/tests/`, 21 tests | Bedrock invocation, the tool intersection, authorization of shared agents |
| Editing an agent definition | `AgentDirectory.test.tsx`, 9 tests | The DynamoDB partial update, and refusal for anyone but the creator |
| Glue catalog browser | `CatalogBrowser.test.tsx`, 8 tests | Databases / tables / columns after a Glue Crawler has run |
| Document text extraction and analysis | `DocumentAnalysis.test.tsx`, 8 tests | Real Textract / Comprehend responses, and whether a cross-region call is needed |
| AI metadata badges | `AiMetadataBadges.test.tsx`, 9 tests | Rendering with real rows in the AI metadata table |
| QR code generation | Same | Whether the generated QR reaches the presigned URL |
| Folder watch / event notifications | `functions/list-files/tests/test_notifications.py`, 9 tests | Real delivery from FPolicy through EventBridge to the bridge Lambda, the shape of real events, and the group boundary filter |

### Test totals

| Suite | Count |
|-------|-------|
| Portal components and utilities (vitest) | 321 (24 files) |
| `functions/resource-management` (pytest) | 258 |
| `functions/data-protection` (pytest) | 104 |
| `functions/list-files` (pytest) | 48 |
| `functions/thumbnails` (pytest) | 37 |
| `functions/agent-chat` (pytest) | 21 |
| Dispatch contract checks (`make drift`) | 173 call sites / 170 actions |

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
| `npx ampx sandbox`, first run | 8-12 min | [pr-ephemeral-environments.md](pr-ephemeral-environments.en.md) | — |
| `make sandbox`, first run | 10-15 min | [cleanup-guide.md](cleanup-guide.en.md) | includes CDK bootstrap |
| `npx ampx sandbox`, incremental | 2-3 min | [pr-ephemeral-environments.md](pr-ephemeral-environments.en.md) | — |
| `npm run build` | 0.25-0.51 s | measured in this session | Vite |

> **Why they differ**: a Lambda in a VPC spends time creating and deleting ENIs and is not eligible for hotswap. Adding VPC configuration turns every change into a full deploy and pushes the first run past ten minutes ([amplify-gen2-cdk-patterns.md](amplify-gen2-cdk-patterns.en.md), case 2). Without a VPC, DemoMode is 3-5 minutes. An unbootstrapped CDK environment adds more on top.

| Item | Behaviour |
|------|-----------|
| Lambda Layer content change | **Skipped by hotswap**. Requires `ampx sandbox delete` then redeploy, or a pipeline deploy |

> **Lambda Layer caveat**: changing `shared/` updates the Lambda by hotswap and skips the LayerVersion content change (there is no flag to disable hotswap). Recreate the sandbox to be certain the change is live.

## Verified under browser emulation only

Checked under Chrome device emulation at 390×844, not on physical hardware. A real
handset's browser chrome — address bar height and so on — differs, so this is kept apart
from the "real system" sections above.

| Item | What was checked |
|------|------------------|
| Phone-width layout | Measured that every control is inside the viewport and every tap target is at least 44px. Steps in the [phone walkthrough](../../../docs/en/portal-mobile-guide.md) |
| Row menu (⋮) | Fixed actions that rendered off the screen; as a bottom sheet all five are reachable (measured 400px → inside the viewport) |
| Snapshot list | Fixed the browse and lock buttons that rendered off the screen (measured: table 585px → 358px, all 26 controls inside) |

## Not yet verified

- **Phone use on a physical iPhone or Android handset** (currently emulation only)
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
| [ONTAP Connection Guide](ONTAP-CONNECTION-GUIDE.en.md) | VPC, secret and management LIF configuration |
| [AppSync Authorization Troubleshooting](TROUBLESHOOTING-APPSYNC-AUTH.en.md) | When group authorization fails |
| [Write Verification Plan](write-verification-plan.en.md) | Prerequisites, procedure, impact and rollback for the writes not yet run |
