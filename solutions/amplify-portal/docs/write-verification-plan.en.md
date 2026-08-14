# Write Verification Plan

🌐 **Language / 言語**: [日本語](write-verification-plan.md) | **English**

> Purpose: for the write operations [Verification Results](verification-results.en.md) groups as
> not yet run, settle the prerequisites, the impact and the rollback **before running them**. The
> order of execution is decided here too.
>
> This is a plan, not a record. An operation once executed moves to "Live E2E" in
> [Verification Results](verification-results.en.md), and what was observed goes into
> `docs/agent/pitfalls-*.md`.

---

## Ground rules

1. **Create the resources the verification acts on.** Do not point it at an existing volume,
   share or policy. The exception is something that can only be established on an existing
   resource: state the impact first, then restore the original state immediately afterwards.
2. **State the impact before running.** Which resource, in what state, until when. Anything
   irreversible needs approval.
3. **A success response is not evidence of success.** A 202 is a queued job, and ONTAP
   acknowledges a change before the listing reflects it. Judge by the state some seconds later.
4. **One operation, one observation.** Running a batch and checking at the end loses which
   operation caused what.
5. **Record the failures too.** A refusal's error code and message are what the next reader will
   be holding, which sometimes makes them worth more than the success.

---

## Group A: safe to run (not yet done)

The suggested order is A8 → A3 → A2 → A5 → A7 → A4 → A6 → A1: fewest prerequisites, smallest
impact and easiest rollback first. A1 (QoS) is last because, as below, **the round trip cannot
currently complete**.

### A1. QoS policies — the round trip does not complete (needs work first)

| Item | Detail |
|------|--------|
| Operations | `createQosPolicy` / `updateQosPolicy` / `assignQosToVolume` / `deleteQosPolicy` |
| Prerequisites | None (this environment has no policies) |
| Impact | A volume the policy is assigned to **is actually throttled** to the IOPS / MBps ceiling. Assign it to a probe volume |
| Confirm | The limits appear in the listing, and the volume's `qos.policy` changes |
| Rollback | **The portal has no way to unassign it** (below) |

ONTAP refuses to delete a policy group that a storage object is assigned to, unless `-force` is
used — which deletes the associated workloads with it. Source:
[qos policy-group delete](https://docs.netapp.com/us-en/ontap-cli-9171/qos-policy-group-delete.html).

`assignQosToVolume`, meanwhile, requires a `policyName`, so there is no path back to "none". So
**create → assign → delete cannot complete through the portal as it stands**, and verifying it
would leave one undeletable policy behind.

Do first: let `assignQosToVolume` accept an empty `policyName` (or an explicit clear) and send the
equivalent of `{"qos": {"policy": {"name": "none"}}}` to `PATCH /storage/volumes/{uuid}`. Put
"remove QoS" next to the assign control in the UI. Verify after that ships.

### A2. SMB share create and delete — **Done (2026-08-15)**

| Item | Detail |
|------|--------|
| Operations | `createCifsShare` / `deleteCifsShare` |
| Prerequisites | CIFS enabled on the SVM (it is here). The share path has to exist |
| Impact | Creation only adds. **Deletion takes away the endpoint any client using that share is connected to.** Delete only a share you created |
| Confirm | It appears in the listing with the `path` and encryption state given |
| Rollback | Delete the share created (no data is lost — a share is a doorway to a volume, not the data) |

Create a probe qtree or directory and share that. The existing `c$` and `ipc$` are ONTAP's
administrative shares; leave them alone.

### A3. Local groups and members — **Done (2026-08-15)**

| Item | Detail |
|------|--------|
| Operations | `createLocalGroup` / `deleteLocalGroup` / `addGroupMember` / `removeGroupMember` |
| Prerequisites | CIFS enabled. **To add a domain user, ONTAP has to be able to resolve the name to a SID** (AD DC reachability). Adding a local user does not need that |
| Impact | Group membership feeds NTFS ACL evaluation. Use only a probe group and probe users |
| Confirm | The group is listed, the member appears in the member listing, and removal takes it away |
| Rollback | Remove the member, delete the group |

Sources: [Manage local SMB group membership](https://docs.netapp.com/us-en/ontap/smb-admin/manage-local-group-membership-task.html),
[Adding local users to the local group (FSx for ONTAP)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/smb-workgroup-add-users-to-group.html).

Local user create / edit / delete was confirmed on 2026-08-14, so make one throwaway user of that
same shape and use it as the member. **The SID not changing** is already established.

### A4. FlexClone create and split (the split is irreversible) — **Done (2026-08-15)**

| Item | Detail |
|------|--------|
| Operations | `createFlexClone` / `splitFlexClone` |
| Prerequisites | A snapshot of the parent (one is taken at creation time if omitted) |
| Impact (create) | Thin: capacity is shared with the parent. One parent snapshot becomes locked |
| Impact (split) | **Irreversible.** A split clone cannot be re-attached to its parent. **Snapshots on the clone are deleted**, and no new snapshot can be taken on it until the split finishes. A low-priority background scanner does the work, so it takes a while |
| Confirm | Split progress (the portal shows `Splitting n%`), and the parent relationship gone afterwards |
| Rollback | A split clone can only be **deleted**. Do this on a throwaway clone |

**The capacity story is easy to get wrong**: since ONTAP 9.4 a clone split preserves space
efficiency, updating metadata rather than copying data blocks. "Splitting consumes as much space
as the parent uses" does not hold from 9.4 on. Sources:
[Split a FlexClone volume from its parent](https://docs.netapp.com/us-en/ontap/volumes/split-flexclone-from-parent-task.html),
[FlexClone split FAQ](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/FAQ_-_FlexClone_split).

This environment already holds `clone01`, `clone02` and `clone03`. **Do not split those** — who
created them and why is unknown, and a split cannot be undone. Verify on a clone created for it.

Measured: `createFlexClone` was not sending `clone.is_flexclone: true`, so ONTAP read it as an ordinary
volume create and answered 787140. **Clearing that 787140 by adding an aggregate returns success and
produces a 20 MB ordinary volume** with no clone relationship. After the fix a 20 GiB clone is created
from the parent's `clone_<name>.<timestamp>`. The split took seconds on a nearly empty clone and left it
using 348 KB, so the space does not double; the volume leaves the clone listing as the split completes,
which is why the progress figure is only visible while it runs, and the parent keeps the base snapshot.

### A5. Quota rule delete — it stays enforced after deletion — **Done (2026-08-15)**

| Item | Detail |
|------|--------|
| Operation | `deleteQuotaRule` |
| Prerequisites | Create a probe rule and delete that (leave the existing `projects` rule alone) |
| Impact | **The delete succeeds and the rule keeps being enforced** until enforcement is switched off and on again for that volume |
| Confirm | It leaves the listing; then switch enforcement off and on and confirm it leaves the usage report |
| Rollback | Delete the probe rule; do not touch the pre-existing one |

ONTAP's REST reference states, as a DELETE response, that the delete succeeded while the rule is
still being enforced, and that stopping enforcement means disabling quotas and enabling them again
for the volume. Sources:
[Delete a quota policy rule](https://docs.netapp.com/us-en/ontap-restapi-9171/delete-storage-quota-rules-.html),
[volume quota policy rule delete](https://docs.netapp.com/us-en/ontap-cli/volume-quota-policy-rule-delete.html).

The portal reports only success and does not point at the next step. **The enforcement toggle now
exists**, so it can: adding that hint alongside the verification is the natural pairing.

Changing the limits (`updateQuotaRule`) does apply over REST without a resize, which matches the
2026-08-14 measurement.

Measured: creating a tree rule for a qtree makes ONTAP create the volume's default tree rule too, and
deleting only the qtree rule leaves that default behind -- so the qtree keeps appearing in the usage
report, which looks like the deleted rule persisting. The deleted rule's own limits left the report
immediately. Whether enforcement continues is not observable through these reads, so the reference
above stands as the source and the portal now points at the off → on step after a delete.

### A6. SnapMirror update-now and transfer abort

| Item | Detail |
|------|--------|
| Operations | `updateSnapmirrorNow` / `abortSnapmirrorTransfer` |
| Prerequisite (update) | The relationship is `snapmirrored` and idle |
| Prerequisite (abort) | **A transfer is in flight.** An abort fails otherwise |
| Impact | A new snapshot is taken at the destination and occupies space. An aborted relationship becomes unhealthy and returns to idle. A restart checkpoint may remain, from which the next transfer continues (`hard_aborted` discards it) |
| Confirm | One more entry in the transfer history; the state transition and the `healthy` value after an abort |
| Rollback | Run update again after an abort to bring the relationship back into step |

**Verifying the abort needs a transfer long enough to catch.** On an empty probe volume the
transfer finishes instantly and there is nothing to abort. Write some data at the source, start an
update, and abort while it runs. Sources:
[Cancel an ongoing SnapMirror transfer (REST)](https://docs.netapp.com/us-en/ontap-restapi-9111/patch-snapmirror-relationships-transfers-.html),
[SnapMirror status and state meanings](https://kb.netapp.com/onprem/ontap/dp/SnapMirror/What_are_the_Ontap_SnapMirror_relationship_status_and_SnapMirror_State_meanings%3F).
That an abort fails unless the relationship is transferring is stated in
[the upgrade preparation steps](https://docs.netapp.com/us-en/ontap-systems-upgrade/upgrade-arl-auto-app-9151/complete-preparation-for-upgrade.html).

### A7. File operations (through the S3 Access Point) — **Done (2026-08-15; only the over-5-GiB case is unverified, for want of a precondition)**

| Item | Detail |
|------|--------|
| Operations | `createFolder` / `copyFile` / `moveFile` / `renameFile` / `trashFile` / `restoreFromTrash` / `deleteFileForever` / `createUploadLink` |
| Prerequisites | S3 AP reachable (confirmed). Upload the probe files yourself |
| Impact | `deleteFileForever` cannot be undone. The trash route (`trashFile`) is a key move and is reversible |
| Confirm | The same result is visible from NFS / SMB (the S3 AP and the file protocols see one volume) |
| Rollback | Delete the probe files |

**The 5 GB ceiling**: rename, move, copy, trash and restore are all implemented with `copy_object`
(`functions/list-files/index.py`). A single `CopyObject` handles up to 5 GB; beyond that
`UploadPartCopy` is required. Source:
[copy-object (AWS CLI reference)](https://docs.aws.amazon.com/cli/latest/reference/s3api/copy-object.html).
But `UploadPartCopy` on the FSx for ONTAP S3 AP, though documented as supported, answers
`NoSuchKey` in measurement ([S3 AP pitfalls](../../../docs/agent/pitfalls-s3ap-ontap.md)).

So **an object over 5 GB is expected to be unrenamable and unmovable from the portal**. Two things
to verify:

1. All eight operations succeed on a file under 5 GB
2. **How** a rename fails on a file over 5 GB — read the message, then decide whether to refuse
   client-side or explain

**Upload links**: a presigned PUT URL has to name SigV4 explicitly (there is a boto3 path where
presign defaults to v2, and ONTAP-side v2 support starts at 9.16.1). AWS's compatibility table
lists presigned URLs as unsupported while they are observed working; AWS Support has submitted a
documentation correction that is **not yet published**, so continue not to depend on it in
production ([S3 AP compatibility notes](../../../docs/s3ap-compatibility-notes.en.md)).

Measured: `createUploadLink` presigned with SigV2 against the global endpoint, so the PUT failed with 301
(the signature covers `host`, so the redirect cannot be followed). Fixed by naming both
`signature_version="s3v4"` and `addressing_style="virtual"`; the PUT returns HTTP 200 after it. An object
over 5 GiB cannot be created here at all -- it needs a multipart upload, which is the very call that fails
on this Access Point -- so a size check before the copy was added instead, refusing with the reason.
Also found: **a folder cannot be deleted from the UI** (`trashFile` refuses folders and `deleteFileForever`
is confined to `.trash/`).

### A8. ARP state change — **the premise did not survive measurement (2026-08-15)**

| Item | Detail |
|------|--------|
| Operations | `updateArpStateAdmin`, `enableArpBulk`, `clearArpSuspects` |
| Prerequisites | ONTAP 9.10.1 or later (this environment is 9.18.1P3D1) |
| Impact | **`dry_run` is not available.** Asking for it leaves the volume `enabled`, which is active protection: snapshots are created automatically on a suspicion |
| Confirm | The `state` in the response -- read back, not echoed -- agrees with what the UI shows |
| Rollback | Set it back to `disabled`, but it stays `disable_in_progress` for over ten minutes |

This step led group A on the premise that dry_run only observes, and is therefore safe.
Measured, **ARP/AI has no learning period and a request for `dry_run` silently becomes
`enabled`** -- no error, no warning. See
[ARP/AI and EMS pitfalls](../../../docs/agent/pitfalls-arp-ems.md).

So this operation is not "try the observing mode", it is "turn protection on". Whether to
run it is a decision about whether that volume may have snapshots created for it. Verify on
a throwaway volume and delete the volume afterwards, which is the surest cleanup: turning it
off takes a long time, and deleting the volume takes the ARP configuration with it.

Source: [Enable ARP on a volume](https://docs.netapp.com/us-en/ontap/anti-ransomware/enable-task.html).

`clearArpSuspects` cannot be confirmed with no suspects recorded, so run it only if one appears.

> **The general lesson from this entry**: "there is a safe observing mode" was a premise, not
> a fact. The documentation was read at planning time and still did not say whether that mode
> exists on the version in use. A premise that makes something safe is the one most worth
> checking first.

---

## Group B: no external prerequisite

These stay unverified because they cannot be run. What would have to exist is stated instead.

| Operations | What has to be in place |
|-----------|------------------------|
| Vscan ×4 (`setVscanEnabled`, policy create / enable / delete) | An external scan engine and a Vscan connector. Policy definition alone is possible from the portal, so **definition without an engine** may belong in group A (check first whether ONTAP refuses to enable the policy) |
| FPolicy ×5 | An external FPolicy engine. With `engine: native` a definition can likely be created and enabled without one, so **native-only may belong in group A** |
| Cluster peer ×3 (create / accept / delete) | A remote cluster with intercluster LIFs, TCP 11104 / 11105 and ICMP allowed, and **an accept on the far side**. One side cannot finish it |
| SVM peer accept / delete | The same. Changing an existing peer's `applications` was confirmed on 2026-08-14 |

> Whether Vscan and FPolicy are reachable with `native` can be settled without changing the
> environment: try creating a policy and enabling it, and delete it on the spot if refused.
> Safest placed at the end of group A.

---

## Group C: not to be run

| Operation | Reason |
|-----------|--------|
| `updateSnaplockRetention` | Needs a SnapLock volume. Unexpired WORM blocks deletion of the volume, then the SVM, then the file system |
| `enableSnapshotLocking` | Cannot be disabled once enabled |
| `lockSnapshot` (both implementations) | Retention can only be extended, never shortened or released |
| `putS3ObjectLockRetention` (COMPLIANCE) | Retention cannot be shortened or removed |
| `createSnapshotPolicy` / `assignSnapshotPolicy` | Assigning a policy requires `acknowledgeIrreversible`. It is the doorway to lock-bearing configuration, so it is deliberately not run |

This follows [Tamperproof Snapshot Design](../../../docs/tamperproof-snapshot-design.md) and the
irreversible-operations section of `AGENTS.md`. **A verification environment is the worst place to
put an irreversible operation**: an undeletable resource becomes a long-running bill and holds
everything sharing the file system in place with it.

---

## Group D: reaches the shared environment (the list that must not lose entries)

Whether to run these is a separate decision. Every one is listed so **none falls off the list**.
"What it cuts" is the path or session that actually stops when the operation succeeds.

| Operation | What it cuts | Scope | Rollback | Conditions for running |
|-----------|-------------|-------|----------|----------------------|
| `setNetworkInterfaceEnabled` (disable) | The path that LIF carries. For a management LIF, **the portal itself loses its route to ONTAP** | Per LIF. For a data LIF, NFS / SMB / S3 over it | The same operation, enabled. But a management LIF cannot be brought back from the portal — that needs the AWS console or another route | Confirm the target is not the management LIF. For a data LIF, a window with no users |
| `setProtocolServiceEnabled` (disable) | That protocol's service (NFS / CIFS / S3) | The whole SVM. Clients in use are disconnected | The same operation, enabled. CIFS may need a re-join after re-enabling | On a probe SVM if one exists. Not on the default SVM |
| `updateDnsConfig` | Name resolution. On an AD-joined SVM **the domain controllers become unresolvable and SMB and AD authentication stop** | The whole SVM | Restore the original domains / servers (**record the current values before running**) | Only after recording the current values. Avoid on an AD-joined SVM |
| `breakSnapmirror` | The replication relationship; the destination becomes read-write | That relationship | `resyncSnapmirror` (which discards changes made at the destination) | As a DR exercise, on a probe relationship |
| `resyncSnapmirror` | The destination's divergence | That relationship | None — the divergence is discarded | Only as the follow-up to a break |
| `blockNfsIp` / `unblockNfsIp` | NFS access from the given IP | Per export-policy rule. With `allSvms`, **every SVM** | `unblockNfsIp`, or TTL expiry (**which does not happen** without `vpcRouteTableIds`) | Restrict the IP to your own probe client. Do not use `allSvms` |
| `blockSmbUser` / `unblockSmbUser` | SMB access for the given user | Per user. As above | `unblockSmbUser`, or TTL expiry | With a probe local user |
| `containThreat` | The above combined (IP + user + session disconnect) | Up to the whole SVM depending on the arguments | The individual unblocks | Only after the individual blocks are confirmed |
| `disconnectSessions` | The target client's SMB sessions | Per session | The client reconnects | Only your own probe client |

> **When the TTL does not expire**: containment expiry depends on an EventBridge schedule. With
> `vpcId` set and `vpcRouteTableIds` absent, blocks never expire and the response reports
> `expiryTracked: false`. **Containment run in that state stays until it is removed by hand.**
> Check the flag before verifying.

### Decide before running anything in D

1. Is the target something created for this, with no existing users?
2. Was the pre-change state recorded (current DNS values, LIF state, the relationship's `healthy`)?
3. Can the reversing operation be run from the portal? If not, is the alternative route (AWS
   console, ONTAP CLI) ready?
4. Is any **scope-widening flag** such as `allSvms` in use?

---

## Related Documents

| Document | Contents |
|----------|----------|
| [Verification Results](verification-results.en.md) | The record of how far each feature is verified |
| [Admin Capability Map](admin-capability-map.en.md) | Per-panel implementation status |
| [Resource Management Demo Guide](resource-management-demo-guide.en.md) | The procedures |
| [S3 AP pitfalls](../../../docs/agent/pitfalls-s3ap-ontap.md) | Supported operations and measured size limits |
| [Tamperproof Snapshot Design](../../../docs/tamperproof-snapshot-design.md) | Design of irreversible retention |
