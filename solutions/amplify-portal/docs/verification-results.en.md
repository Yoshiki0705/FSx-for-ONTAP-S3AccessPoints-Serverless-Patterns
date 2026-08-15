# File Portal — Verification Results

🌐 **Language / 言語**: [日本語](verification-results.md) | English

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

**A3, A2, A5, A7, A4 and A1** of the verification plan (A6 is on hold; the reason is in the
[plan](write-verification-plan.en.md)). Every group, user, share, qtree, quota rule, QoS
policy, FlexClone and S3 object created for it was deleted afterwards, along with the working
volume `zz_probe_a`, and the environment is back as it was.

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
| FlexClone creation (A4) | **Worked only after a fix.** Without `clone.is_flexclone: true` ONTAP reads the POST as an ordinary volume create and stops at 787140, asking for `aggregates` or `style`. **Satisfying that 787140 with an aggregate returns success and produces a 20 MB ordinary volume** with no clone relationship and no entry in the clone listing -- the clone block it ignored is where the size would have come from | [Volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| FlexClone split (A4) | On a nearly empty clone it finishes in seconds, and the volume **leaves the clone listing** as it does, so the `n% split` progress is only observable while it runs. A 20 GiB clone used 348 KB afterwards: **the space does not double** (9.4 and later preserve storage efficiency; the handler's docstring said the opposite and is corrected). The base snapshot ONTAP took **stays on the parent**, and removing it is the operator's | Same |
| Volume pinning in the data-protection handler (found during A4) | The nine actions in `functions/data-protection` (`createSnapshot`, `deleteSnapshot`, `updateArpState`, `updateRetentionPolicy` and the rest) were pinned to the volume in the environment. No UI call site reaches them, so nothing was broken in practice -- but wiring one up from a scoped screen would have acted on the configured volume. They now honour `volumeName` and `svm`, verified live by deleting a snapshot on `zz_probe_a` and confirming `vol1` was untouched | Same |
| QoS policy round trip (A1) | Create, assign, change the limits while assigned, release with `none`, delete -- the whole cycle. The release keeps the policy and returns the volume to 0, meaning no limit | [Demo guide](resource-management-demo-guide.en.md) |
| Deleting an assigned QoS policy (A1) | **The plan's premise did not hold.** The CLI reference says the delete is refused while a storage object is assigned unless `-force` is given; on 9.18.1P3D1 through REST it is **accepted, and the volume is detached silently** (every limit back to 0, meaning unlimited). So the dead end the plan was written around does not exist -- and in its place, **deleting a policy lifts the limit from every volume using it**. The panel's confirmation now says so | [qos policy-group delete](https://docs.netapp.com/us-en/ontap-cli-9171/qos-policy-group-delete.html) |
| SnapMirror update-now (A6) | Run against an existing relationship (its source is on another cluster) with the account owner's approval. The transfer history went 4 → 5, and the new transfer was caught `transferring` before finishing: 12 seconds, 27,888 bytes, success. Lag went 14h59m → 1m8s, `lastTransferType` resync → update, and the relationship stayed snapmirrored and healthy. The destination gained a new `snapmirror.<uuid>_<ts>` plus seven hourly snapshots from the source (older ones aged out, so the count stayed at 14) | [Demo guide](resource-management-demo-guide.en.md) |
| Transfer history ordering (found during A6) | ONTAP does not order these, and the transfer that had just run came back third of five. On a screen that presents them as a history, the top row was not the operation the reader had just caused, so the handler sorts newest first (a running transfer has no end time and goes to the top) | Same |
| Every S3 client that presigns (sweep) | After the upload link defect, all seven functions that presign were checked. **Only `list-files` was broken**; the other six each named a regional `endpoint_url` beside `s3v4`. Measured that **both** shapes return 200 against an Access Point alias -- path-style with an explicit endpoint, and virtual addressing. Only the combination left to the defaults fails, which is now a `make drift` rule | [S3 AP pitfalls](../../../docs/agent/pitfalls-s3ap-ontap.md) |
| Deleting the parent of a deleted clone (found while re-checking) | Right after a clone is deleted, **its parent cannot be**. The clone is invisible to the API (`entry doesn't exist`, absent from the clone listing) and the parent still refuses with "has one or more clones". The delete job for the `clone_<name>.<ts>` snapshot left on the parent does not finish within 10 seconds either. ONTAP's recovery queue (12 hours by default) is the likely mechanism, but confirming it needs the ONTAP CLI, so it stays a hypothesis | [Volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| Waiting for the snapshot delete's 202 (same run) | `functions/data-protection` had no job handling at all and reported a 202 as success. The snapshot above was **reported deleted twice and stayed in the listing both times**. The job is now followed and its failure reported | Same |
| A failed delete leaves the volume offline (same run) | The delete's second step (offline) succeeds, so a volume whose delete job then fails is left offline. Nothing in the portal could reverse it, so `bringVolumeOnline` was added | Same |
| Splitting before deleting a clone frees the parent at once (measured A/B) | The same environment, the same steps, only the split differing. Delete an unsplit clone → the parent's delete fails (`has one or more clones`, still after 7 and 15 minutes). Split → delete → the parent deletes seconds later. The cause is ONTAP's volume recovery queue: a deleted RW/DP volume is held for 12 hours by default, keeps consuming aggregate space, and still counts as a clone from the parent's side | [Volume Recovery Queue (KB)](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/How_to_use_the_Volume_Recovery_Queue) |
| The recovery queue is readable over REST and `purge` works as `fsxadmin` (**correcting what was written here**) | This said that `purge` needs diag privilege, that fsxadmin cannot reach it, and that waiting is the only option. All three are wrong. `GET /api/private/cli/volume/recovery-queue` lists the queue, and `POST /api/private/cli/volume/recovery-queue/purge` returns 202 and clears the entry in about 20 seconds. Purging the clone that was blocking made the parent (`zz_recheck_src`) deletable immediately. Queued names carry a suffix (`zz_recheck_clone_1106`), so matching on the original name finds nothing; `DELETE` on the collection is 405 and `fields=*` is refused. A purge cannot be undone, so it is only for a volume you know you deleted | [Volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| Split guidance in the UI (added here) | The FlexClone panel carries a collapsed guide: four cases for when to split and six properties of a split (9.4 and later update metadata only and copy no data / it cannot be undone / progress counts inodes / no new snapshot on the clone while it runs / offline interrupts and online resumes / the aggregate is not selectable and a clone in a data protection relationship cannot be split). The confirmation's "consumes full capacity" was wrong from 9.4 and is corrected. When a delete fails with "has one or more clones", the error now carries the recovery-queue explanation and points at the split | [ONTAP docs](https://docs.netapp.com/us-en/ontap/volumes/split-flexclone-from-parent-task.html) / [KB](https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/FAQ_-_FlexClone_split) |

### Added 2026-08-15 (capacity and volume style, ONTAP 9.17.1P6)

What the volume list's used figure counts and does not count, and how FlexVol and
FlexGroup differ, confirmed against the live file system. The FlexGroup created for the
purpose, `zz_fg_probe`, has been deleted.

| Feature | What was confirmed | Source |
|---------|-------------------|--------|
| What the used figure counts (read) | `space.used` **means a different quantity on different volumes**: snapshot data inside the Snapshot reserve is excluded, data past the reserve included. Measured: a 100 GiB volume reported 18.1 MiB used while holding 77.3 MiB of snapshots (inside a 5% = 5 GiB reserve). A volume with a 0% reserve reported 83,677 MiB used = 81,934 MiB live + 1,743 MiB snapshots. **On 8 of 11 volumes the snapshots held more than the live data**, so the list now separates live data, snapshots and spill | [Snapshot reserve](https://docs.netapp.com/us-en/ontap/data-protection/manage-snapshot-copy-reserve-concept.html) / [spill (KB)](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_can_impact_snapshot_size_and_cause_snapshot_spill) |
| Volume style (read) | `style` was already fetched and never shown. Both exist here, including the FlexCache pair — **a FlexVol origin (vol1) and a FlexGroup cache (flexcache_eda_tokyo)**, the cache side always being a FlexGroup | [FlexCache REST overview](https://docs.netapp.com/us-en/ontap-restapi-9171/manage_flexcache_volumes.html) |
| Creating a FlexGroup | **Working for the first time after a fix.** ONTAP's automatic placement always fails on FSx for ONTAP (`Aggregates not matching FabricPool requirements: aggr1`); naming the aggregate succeeds. The default four-constituent geometry refuses anything under 400 GB. **The same root cause was already known on the FlexCache path (`use_tiered_aggregate`) and had not reached the volume path** | [Volume lifecycle](../../../docs/agent/pitfalls-volume-lifecycle.md) |
| Reading rebalance state | `rebalancing` is an explicit-request field, and **some volumes do not return it even with `fields=**`** (56 keys). An ONTAP S3 bucket's backing volume (`is_object_store: true`) and a FlexCache cache are both FlexGroups and return nothing. An ordinary FlexGroup returns it, with defaults matching the documentation (`PT6H` / 100 MB / 20% / 5% / 25 / exclude_snapshots true, `granular_data: false`). **Collapsing an absent object into `state: unknown` would look like a balanced volume**, so a separate flag distinguishes them | [Rebalancing](https://docs.netapp.com/us-en/ontap/flexgroup/manage-flexgroup-rebalance-task.html) / [not supported for S3 buckets (KB)](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_it_necessary_to_manually_balance_constituents_of_an_S3_bucket_hosting_flexgroup%3F) |
| Four refusals on start | Missing acknowledgement, a FlexVol, an object-store backing volume, and a `maxRuntime` that is not an ISO-8601 duration — all four confirmed live | Same |
| Starting, stopping and scheduling a rebalance (run with the account owner's approval) | An end-to-end run pinned **two runtime constraints absent from the API reference**: `max_runtime` must be at least 30 minutes (`144182221`) and shorter than the time to the next scheduled snapshot (`13107433`), so **ONTAP's own 6 hour default always fails**. With the default policy (hourly at :05) a start is only possible between :05 and :35. The boundary was pinned by a 60/30 minute A/B one second apart. Two undocumented volume states came back — `idle` (running with nothing to move) and `scheduled` — and a running rebalance had been rendering as "unknown". A run with nothing to move emits no notice and only `runtime` advances. `granular_data` stays `true` after stopping, confirming the irreversibility. A cancelled schedule leaves `start_time` behind | [FlexGroup rebalance measurements](flexgroup-rebalance-verification.en.md) |
| The double-start guard (found above) | The portal tested `starting` / `rebalancing` only and let the states a real volume returns — `idle` and `scheduled` — straight through. ONTAP refuses with `144182216`, so nothing was harmed, but the condition is now inverted to treat anything but `not_running` / `unknown` as in progress | Same |
| A new FlexGroup is not empty (same run) | On 400 GiB across four constituents, each member already holds about 537 MB of metadata, roughly 2.1 GB in total, and the members differ by at most about 12 KB | Same |
| FlexVol to FlexGroup conversion | **Not in the REST API** (`volume conversion start` is advanced-privilege CLI only). AWS recommends copying to a new FlexGroup with AWS DataSync rather than converting in place, and deleting FSx backups first. No button; the preconditions, irreversibility and snapshot consequences are in the panel's guidance instead | [AWS docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html) |
| Hour durations (found here) | `durationLabel` understood days only and returns unknown values unchanged, so the rebalance runtime select displayed ONTAP's own default as the string `PT6H` | — |

### Added 2026-08-15 (SnapLock and snapshot locking, ONTAP 9.18.1P3D1)

**Group C, previously "irreversible, so not run", was run after the account owner approved
the retention values by name.** What made it possible is that ONTAP accepts a retention period
in seconds (0 to 65535). A five-minute retention expires in minutes, and the volume can then be
deleted.

The volumes created for this (`zz_sl_ent`, `zz_sl_comp`, `zz_lock_probe`) were all deleted; the
file system is back to its original 10.

| Feature | What was confirmed | Source |
|------|---------|------|
| Creating a SnapLock enterprise / compliance volume | Created with `snaplockType` plus `retentionMin` / `retentionDefault` / `retentionMax`, then read back with `getSnaplockConfig`. **ONTAP accepted `PT5M`** (min `PT0S`, default `PT5M`, max `P1D`), and reports `complianceClockTime` | [Set the retention period](https://docs.netapp.com/us-en/ontap/snaplock/set-retention-period-task.html) |
| The acknowledgement is enforced | A create without `acknowledgeIrreversible` is refused for both types | as above |
| Changing the retention | `updateSnaplockRetention` with `days=1` moved the volume default from `PT5M` to `P1D`. **A volume's default and a committed file's retention are different things**; only the latter is extend-only | as above |
| **An empty SnapLock volume can be deleted** | Even in compliance mode, `deleteVolume` completed within 90 seconds and the volume left the listing. With no WORM file ever committed it stays deletable, which is what the UI text says | — |
| Enabling snapshot locking | Refused without the acknowledgement. After enabling, `snapshotLockingEnabled: true` (irreversible) | [Tamperproof snapshot design](../../../docs/tamperproof-snapshot-design.md) |
| Locking a snapshot | `lockSnapshot` returns an `expiryTime`, and `getSnapshotLockingStatus` counts `lockedSnapshotCount: 1` | as above |
| **A locked snapshot does not stop the volume being deleted** | A volume holding a locked snapshot was deleted and left the listing 20 seconds later. The blast radius differs from a SnapLock WORM file, and this matches the portal's own wording (`slcSnapshotScope`: it does not affect other snapshots or the volume itself) | — |
| **The snapshot list reported locks incorrectly (fixed)** | ONTAP carries two expiry fields on a snapshot: `expiry_time` for snapshot locking, `snaplock_expiry_time` for the expiry a SnapLock volume gives its snapshots. `lockSnapshot` writes the former, but the listing in `_get_snapshots` **requested and read only the latter**, so **every snapshot the portal locked itself displayed as not locked**. Found because two panels disagreed about the same snapshot. Both fields are read now, with four tests that fail against the old code | — |

> **This procedure cannot be reproduced from the UI.** The portal's `asIsoDuration` accepts only
> date components (Y/M/W/D) and `updateSnaplockRetention` takes `days`. ONTAP accepts seconds, so
> the limitation is the UI's. **A user cannot currently choose a retention below one day.**

### Still unconfirmed (SnapLock)

| Item | Why |
|------|------------|
| Committing a file to WORM, and the deletion block that follows | Making a file read-only needs an NFS or SMB client; it cannot be committed through the S3 Access Point. Waiting on a client inside the VPC |
| Privileged delete on an enterprise volume | It requires an audit log volume, and that blocks deletion of the volume, then the SVM, then the file system for **at least six months**. The AWS API has no field for the audit log's retention, so the six-month default applies. **There is no way to shorten it, so it is not run** |

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
| **A. Safe to run** | **A1 through A8 all run on 2026-08-15.** Two items remain: the SnapMirror **transfer abort** and a **copy over 5 GiB** | The abort is reachable — the measured transfer window is 12 seconds — but it leaves a relationship we do not own unhealthy, so it needs the owner's approval. The 5 GiB case has no precondition to create: exceeding it needs the multipart upload that fails on this Access Point |
| **B. No external prerequisite** | Vscan ×4, FPolicy ×5, cluster peer ×3, SVM peer accept and delete | An external scan engine, an FPolicy engine, or an accept on the remote cluster is required. FPolicy may be reachable with `engine: native` |
| **C. Irreversible, run with short values** | SnapLock retention, snapshot locking, performing a lock | **Run on 2026-08-15** (see the 08-15 table below). ONTAP accepts a retention in seconds, so a five-minute retention expired and the volumes were then deleted. What remains is committing a file to WORM (waiting on an NFS/SMB client) and privileged delete (not run: its audit log volume locks the file system for at least six months) |
| **D. Affects the shared environment** | Disabling a LIF, disabling a protocol service, DNS update, SnapMirror break / resync, the six containment actions | These cut a path, a session or a replication relationship. Decide the target and the window first |
| **E. Not ONTAP** | Agents / teams / sessions, portal settings, thumbnails | Bedrock, DynamoDB and S3. Not real-hardware ONTAP verification |

> **The two findings the documentation review produced were both overturned by measurement.**
> The predictions are kept, because the next person reading the same references will reach them.
>
> - Predicted: **an in-use QoS policy cannot be deleted, so the cycle cannot complete** (CLI
>   reference). Measured: on 9.18.1P3D1 through REST it **is** deleted, and the volume is
>   detached silently. The cycle completes; what is true instead is that a delete lifts the limit
>   from every volume using the policy. The `none` release is still needed, as the way to lift
>   one volume's limit while keeping the policy.
> - Predicted: **deleting a quota rule leaves it enforced** until enforcement is cycled (REST
>   reference). Measured: the deleted rule's limits leave the usage report immediately. Whether
>   enforcement itself continues is not observable through these two reads, so the reference
>   stands as the source and the portal now points at the off → on step after a delete.

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

### How to count the automated tests

What is recorded here is how to count, not the counts. This table used to carry a frozen
number per suite, and five of the six had gone stale: resource-management said 258 against
an actual 300, vitest said 321 across 24 files against 337 across 26, and the dispatch
contract said 173/170 against 180/174. A number nobody updates is correct only on the day
it is written.

| Suite | Command that reports the count |
|-------|-------------------------------|
| Portal components and utilities (vitest) | `cd solutions/amplify-portal && npx vitest run` |
| `functions/*` (pytest) | `python3 -m pytest solutions/amplify-portal/functions/<name>/tests/ -q` |
| Dispatch contract (call sites and actions) | `python3 scripts/check_portal_action_params.py` |
| Dispatch action types | `python3 scripts/portal_action_types.py --check` |

Rounded totals live in [AGENTS.md](../../../AGENTS.md). The file counts there are compared
against the tree by `make drift`, so they fail once they age. **The test counts are not
compared**, which is why the commands above are the only source for them.

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
