# Resource management demo guide

🌐 **Language / 言語**: [日本語](resource-management-demo-guide.md) | English

> Steps for driving the 20 panels under `Admin → Resource management`.
> For each panel: which ONTAP REST API it calls, and what confirms success.

[日本語](resource-management-demo-guide.md)

---

## Prerequisites

| Requirement | How to check |
|-------------|-------------|
| Member of the `storage-admin` Cognito group | After signing in, the `Admin` section appears in the left menu |
| ONTAP management endpoint reachable | A panel opens without staying on `Connecting...` |
| ONTAP credentials in Secrets Manager | `ONTAP_SECRET_NAME` is set |
| CIFS enabled on the SVM (SMB panels only) | Needed for SMB shares, local users and name mapping |
| Intercluster LIF (peering only) | The `Peering → intercluster LIF` tab lists a LIF in `up` state |

When ONTAP is not connected, each panel shows an empty state and setup guidance.
No error dialog appears. For connection setup, start with the
[ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md).

---

## Demo scenarios

### Scenario 1: Check the panel list

1. Open `Admin → Resource management` in the left menu
2. Cards are grouped by category

Success criterion: **5 categories and 20 cards** are shown.

| Category | Cards | Contents |
|----------|:-----:|----------|
| Storage | 6 | Volumes / Qtrees / Quotas / Storage efficiency / FlexCache / FlexClone |
| Access control | 5 | Export policies / SMB shares / QoS policies / Local users / Name mapping |
| Data protection | 6 | ARP/AI protection / Snapshot management / SnapLock / SnapMirror / Virus scanning / FPolicy |
| Cluster | 2 | Peering / Cluster information |
| AI services | 1 | AI settings |

Four storage-health cards sit above them (volume count, ARP protection, locked
snapshots, storage efficiency). Clicking a card jumps to the matching panel.

**SVM scope**: when the file system holds more than one SVM, an `SVM scope` selector
appears at the right of the header. The selection is supplied to every action that reads an
`svm`, so switching it changes what the admin listings show. With a single SVM there is
nothing to choose and the control stays hidden.

Success criterion: the volume list changes after switching. A volume created on another SVM
not appearing under the default scope is correct -- switching is how you see it.

---

### Scenario 2: SMB local users and groups

`Access control → Local users`

ONTAP REST: `/protocols/cifs/local-users`, `/protocols/cifs/local-groups`

**Create a user**

1. On the `👤 Users` tab, choose `+ Create user`
2. Enter user name, password, full name and description
3. `Create`

Success criterion: the row appears with a `Member of` column and a `State`
(enabled/disabled) badge.

> **Security note**: the password is never written to the Lambda log.
> The audit log records only the user name and the operator.

**Create a group and manage members**

1. On the `👥 Groups` tab, choose `+ Create group`
2. Enter group name and description, then `Create`
3. Expand `▶ Members` on the new group
4. Enter a member name and add it

Success criterion: `✅ Group created` appears and the count increases.

Member names may include the domain (`DEMO\alice`). On delete the name is
URL-encoded as a path segment.

**Delete**

`Delete user` / `Delete group` operate by SID. The SVM UUID is resolved automatically.

---

### Scenario 3: Name mapping (Windows ↔ UNIX)

`Access control → Name mapping`

ONTAP REST: `/name-services/name-mappings`

1. `+ Create mapping`
2. Choose the direction (`Windows → UNIX` or `UNIX → Windows`)
3. Enter index, pattern (regular expression) and replacement
4. `Create`

Success criterion: the direction renders as `Windows → UNIX` and rows are ordered by index.

> **S3 Access Point note**: mappings in the `S3 → UNIX` direction are created and
> removed automatically by FSx for ONTAP when an S3 Access Point is attached.
> Attempting to create one from the portal returns a message and stops.
> No manual management is needed.

Leaving the replacement empty means, per ONTAP's definition, an explicit denial of the
mapping for that user. The list shows it as `" " (deny)`.

**Moving the evaluation order (index)**

`Edit` rewrites the pattern and the replacement. Changing the evaluation order is a
separate button.

1. `Move` on the row
2. Enter the target index (`Execute` stays disabled at the position it already holds)
3. `Execute`

Success criterion: the row appears at the index given, **and the rules in between are
renumbered too**. ONTAP evaluates in index order and stops at the first match, so moving a
rule changes which rule wins. A delete does not renumber, but this move does (measured:
moving `win_unix` index 2 to 1 leaves the rule that was 1 at index 2).

---

### Scenario 4: FlexCache

`Storage → FlexCache`

ONTAP REST: `/storage/flexcache/flexcaches`

1. `+ Create FlexCache`
2. Enter cache name, origin volume, origin SVM (leave empty for the same SVM), size
   and junction path
3. Optionally list directories to prepopulate, comma-separated
4. `Create`

Success criterion: the `origin → cache` relationship renders with an arrow, together
with size, path and Global File Locking state. Creation is asynchronous, so a job ID
is returned.

Around 10% of the origin volume is a reasonable size, but that is guidance, not the floor.
A FlexCache is a FlexGroup, so the floor is the per-constituent minimum times the number of
constituents ONTAP chose, and it differs between clusters (measured at 50 GB on the
validation file system). A smaller request is refused inside the ONTAP job, and the message
carries the floor for that file system.

**Resize**

A cache is not fixed at the size it was created with. `Resize` on the row opens the panel.

1. `Resize` on the row
2. Enter the size in GiB (`Apply` stays disabled at the current value)
3. `Apply`

This is independent of the origin: growing the cache does not change the origin.

The creation floor does not apply to shrinking an existing cache (measured: on a file system
that refuses a create below 50 GB, an existing 100 GiB cache shrank to 20 GiB). Do not assume
a size you cannot create is a size you cannot shrink to.

Success criterion: a FlexGroup resize continues as an ONTAP job, so right after
`The resize was accepted` the listing can still show the old size (measured: both growing
and shrinking ran past 10s). The panel re-reads once more after 20 seconds.

**Write modes**

A FlexCache is not read-only. Writes at the cache are served, and ONTAP keeps the cache
and the origin coherent in either mode. What differs is where the write is acknowledged.

| Mode | Behaviour | Requirement |
|------|-----------|-------------|
| write-around (default) | The write is forwarded to the origin and acknowledged once the origin has committed it | None |
| write-back | The write is committed at the cache and acknowledged immediately, then flushed to the origin asynchronously | ONTAP 9.15.1 or later on **both** the cache and the origin |

`Enable write-back` in the create form selects it at creation time. An existing cache is
switched with `Enable write-back` / `Disable write-back` on its row. Disabling flushes
what is only at the cache to the origin, which makes it **a prerequisite for deleting
the cache**.

Success criterion: every row always carries a `✍️ write-around` or `✍️ write-back` badge,
and the listing reflects a switch.

**Delete**

The row's `Delete` → `Really delete?` → `Execute` is two-step by design.
The first click does not delete. ONTAP refuses to delete a cache with write-back
enabled, and the error carries the reason and the fix (disable write-back first).

---

### Scenario 5: FlexClone

`Storage → FlexClone`

ONTAP REST: `/storage/volumes` (POST with a `clone` block; the list filters on
`clone.is_flexclone=true`)

1. `+ Create FlexClone`
2. Enter clone name, parent volume and parent snapshot
3. `Create`

Success criterion: the row shows parent volume, parent snapshot, size and used space.

> **Security style note**: the clone's security style and export policy are inherited
> from the parent volume. They cannot be set at creation, so the portal does not send them.

**Split**

Clicking `Split` starts the split after confirmation, and the row changes to
`Splitting n%`.

After a split the clone no longer shares blocks with the parent and consumes the full
data footprint. The confirmation states this.

---

### Scenario 6: SnapMirror operations

`Data protection → SnapMirror`

ONTAP REST: `/snapmirror/relationships`, `/snapmirror/relationships/{uuid}/transfers`

1. Opening the panel lists relationships whose destination is on this cluster
2. Expanding `▶ Transfer history` shows recent transfers

Success criterion: `source → destination`, policy name, lag and a health badge
(healthy/unhealthy) are shown.

`+ Create replication` establishes a new relationship. ONTAP provisions the destination
volume, so there is no need to run `volume create -type DP` first.

| Field | Meaning |
|-------|---------|
| SVM peer | Only peers that are `peered` and list `snapmirror` among their applications are offered. The source SVM, the source cluster and the destination SVM all come from the peer |
| Source volume name | The volume name on the other file system |
| Destination volume name | A name not already in use on this file system |
| Initialize after creating | Includes `state: snapmirrored` in the POST, running the baseline transfer |

Success criterion: right after creation the state is `uninitialized`; once the baseline
transfer finishes it becomes `snapmirrored` and the first entry appears in the transfer
history. Creating and initializing both outlive the Lambda invocation, so a job still
running is treated as accepted. The list refetches on its own only while a relationship
is mid-flight.

If no peer permits `snapmirror`, the reason is shown in place of the choices. Add it
through `Change applications` under `Peering → SVM peers`; the peer does not have to be
recreated.

The row's action buttons run the following.

| Operation | Call | Confirmation |
|-----------|------|:------------:|
| Update now | `POST /snapmirror/relationships/{uuid}/transfers` | — |
| Quiesce | `PATCH state=paused` | — |
| Resume | `PATCH state=snapmirrored` | — |
| Break | `PATCH state=broken_off` | Required |
| Resync | `PATCH state=snapmirrored` (from broken_off) | Required |
| Abort transfer | `PATCH transfers/{uuid} state=aborted` | — |
| Delete relationship | `DELETE /snapmirror/relationships/{uuid}` | Required |
| Create | `POST /snapmirror/relationships` (`create_destination` + `state`) | — |

Operations marked "Required" show a confirmation row and are not sent until `Execute`
is pressed. The handler independently refuses without `confirm=true`, so a direct call
that bypasses the UI is rejected the same way.

> **Failover procedure note**: break makes the destination writable. Depending on the
> direction of the subsequent resync, updates on the destination are lost. A real DR
> failover should run alongside a runbook covering application shutdown, DNS cutover
> and consistency checks. The portal covers only the ONTAP-side operation.

---

### Scenario 7: Virus scanning (Vscan)

`Data protection → Virus scanning`

ONTAP REST: `/protocols/vscan/{svm.uuid}`,
`/protocols/vscan/{svm.uuid}/on-access-policies`

1. Use the toggle at the top of the panel to enable or disable Vscan on the SVM
2. `+ Create policy` creates an on-access policy
   (name, whether scanning is mandatory, max file size, excluded paths, excluded extensions)
3. Use the row toggle to enable or disable a policy
4. `Delete` → confirm → `Execute` removes a policy

Success criterion: the enabled state updates in the list immediately, and excluded
paths and extensions render comma-separated.

`📖 Show setup guide` in the toolbar opens the setup steps, including the list of
interoperable products, where to obtain the connector, and example ONTAP CLI commands.
It appears automatically while Vscan is disabled, and the same content stays reachable
from that button once Vscan is on.

> **Prerequisite note**: policy definitions can be created from this portal, but actual
> scanning requires an external scan engine and a Vscan connector. The scanner side is
> configured with the scanner product's own management tool.

---

### Scenario 8: FPolicy

`Data protection → FPolicy`

ONTAP REST: `/protocols/fpolicy/{svm.uuid}/events`,
`/protocols/fpolicy/{svm.uuid}/policies`

There are three tabs.

| Tab | Contents |
|-----|----------|
| 📋 Policies | Policy name, enabled state, priority, engine type, subscribed events |
| 📡 Events | Event definition name, protocol, monitored operations |
| 🔌 Connections | Node, policy, external server, connection state |

![The Policies tab of the FPolicy panel. One row shows the audit_all policy as enabled with priority 1, engine external and the file_ops_cifs event set, alongside Disable and Delete actions. Delete is not clickable because the policy is enabled](../../../docs/screenshots/fpolicy-manager.png)

1. On the `📡 Events` tab choose `+ Create event`
   (name, protocol, operations to monitor)
2. On the `📋 Policies` tab choose `+ Create policy`
   (name, events to subscribe, engine type)
3. Enable the policy with the row toggle. Priority is required when enabling
4. When no longer needed, disable it, then `Delete` → confirm → `Execute`

Success criterion: the delete button is not clickable while the policy is enabled
(ONTAP rejects it). Disabling makes deletion possible.

> **ONTAP behaviour note**: an enable request requires `priority`, and a disable
> request must not send it. The portal handles the difference internally.

The `📡 Events` tab lists event **definitions**. To process the actual file access
stream, use the pattern in `solutions/event-driven/fpolicy/`.

---

### Scenario 9: Cluster peering

`Cluster → Peering`

ONTAP REST: `/cluster/peers`, `/network/ip/interfaces?services=intercluster_core`

The AWS Management Console has no surface for this. Until now it required the ONTAP
CLI or hand-written REST calls.

**Check the prerequisites**

1. Open the `🌐 intercluster LIF` tab
2. Confirm at least one LIF is in `up` state
   (a `Ready for peering` badge means the condition is met)
3. In the security group, allow TCP 11104, 11105 and ICMP between the intercluster
   LIFs of both clusters

**Create on one side**

1. On the `🔗 Cluster peers` tab choose `+ Create cluster peer`
2. Enter the remote cluster's intercluster LIF addresses, comma-separated
3. Turn on `Generate passphrase` and choose `Create`

Success criterion: the generated passphrase appears at the top of the panel.
**It is shown once only.** Once dismissed it cannot be shown again.

**Accept on the remote side**

1. Open the `🔗 Cluster peers` tab in the remote cluster's portal
2. Click `Accept` on the row, enter the same passphrase and choose `Execute`

Success criterion: the state moves from `pending` to `available` and authentication
becomes `ok`.

**Delete**

`Delete` → confirm → `Execute`. Dependent SVM peers and replication relationships must
be removed first; ONTAP rejects the delete while they exist.

---

### Scenario 10: SVM peering

`Cluster → Peering → 🗂️ SVM peers`

ONTAP REST: `/svm/peers`

Run this after the cluster peer has become `available`.

1. `+ Create SVM peer`
2. Enter peer SVM name, peer cluster name and applications (`snapmirror` / `flexcache`)
3. `Create`
4. Click `Accept` on the row in the remote portal (no passphrase is needed)

Success criterion: the state moves from `pending` to `peered` and the `Applications`
column lists what was specified.

> **Relationship to SnapMirror**: an SVM-level SnapMirror additionally requires the
> source subtype to be `default` and the destination to be `dp_destination`, on top of
> the SVM peer being `peered`. When creating a new destination SVM, do not forget the
> subtype.

---

### Scenario 11: Cluster information

`Cluster → Cluster information`

There are four tabs.

| Tab | ONTAP REST | Contents |
|-----|-----------|----------|
| 🖥️ Overview | `/cluster`, `/cluster/nodes`, `/cluster/licensing/licenses` | Cluster name and ONTAP version, nodes and HA partners, licences |
| 🌐 Interfaces | `/network/ip/interfaces` | LIF list with enable/disable |
| ⚙️ Services | `/protocols/{nfs,cifs,s3}/services`, `/name-services/dns` | Protocol enable/disable, DNS domains and servers |
| 📜 Jobs | `/cluster/jobs` | State and message of asynchronous jobs |

> **When nodes and licences come back empty**: on FSx for ONTAP, AWS manages the
> cluster, so `/cluster/nodes` and `/cluster/licensing/licenses` can return zero
> records. Measured on ONTAP 9.17.1P7D1: both returned zero records with no error.
> The panel shows a note to the same effect. Cluster name and ONTAP version
> (`/cluster`) are still available.

**Enable or disable a LIF**

Use `Enable` / `Disable` on the row. Disabling requires confirmation.

> **Path note**: disabling a management or data LIF cuts that path. Disabling the
> management LIF the portal itself uses makes further operations impossible.

**Enable or disable a protocol service**

The state of NFS, CIFS and S3 is shown and can be toggled. Disabling requires
confirmation. The CIFS `Detail` column shows the AD domain name; empty means the SVM
is not AD-joined.

**Update DNS**

Enter domains and servers comma-separated, then `Apply`.

> **AD note**: an AD-joined SVM resolves domain controllers through the servers set
> here. A wrong value breaks SMB, and on an AD-joined SVM it also makes S3 Access Point
> data operations return `AccessDenied`.

**Jobs**

FlexCache creation, FlexClone split, SnapMirror transfers and peering all run as
asynchronous jobs. Their progress and failure reasons appear on this tab.

---

### Scenario 12: File operations (the `All files` view)

Separate from resource management, these are available from the files view.

**Folder favourites**

1. Click ☆ on any folder row (it becomes ★)
2. Open `Favourites` in the left menu
3. `📁 folder name` appears with a trailing-slash key
4. Clicking it opens that folder

Clicking the same favourite again returns to that folder even if you had navigated
elsewhere.

**ZIP download**

1. Enter any folder (nothing is shown at the root)
2. Click `📦 Download as ZIP` in the header
3. Completion shows the file count and size, plus `Open download link`

Success criterion: when a limit (file count or total size) is exceeded, an error is
returned without building the ZIP.

**File tags**

1. Click 🏷️ on a file row to open the editor
2. Enter a tag name and press `+`
3. It appears as a badge on the row

Success criterion: the row badge refreshes immediately after adding. Tags are stored
per user.

**Share link**

1. Click 🔗 on a file row
2. Choose the expiry (5 minutes / 15 minutes / 1 hour)
3. `Generate link` → `Copy`

Success criterion: the labels render in the currently selected language (8 supported).

**Inline PDF / Office preview**

Clicking the file name renders a preview inside the portal using a presigned URL.
PDFs use an iframe; Office documents are rendered client-side.

**Snapshot comparison**

1. Click `🔍 Compare with snapshot` in the header
2. Enter the clone's S3 AP alias (visible in the `📸 Restore from Snapshot` job result)
3. Click `Compare with snapshot`

Success criterion: counts of added, removed and unchanged files appear, with the
current and clone size and timestamp side by side.

---

### Scenario 13: Regression check on existing panels

Confirms the new panels did not break existing behaviour.

| Panel | Action | Expected result |
|-------|--------|----------------|
| Volumes | List → resize | The capacity changes |
| Quotas | Create rule → report | Usage is shown |
| Export policies | Add rule | The client match clause takes effect |
| ARP/AI protection | Change state | Learning/enabled can be switched |
| SnapLock | Update retention | The change takes effect |

---

### Scenario 14: Renaming a qtree, and quota enforcement

Two operations kept apart from editing. In both cases what happens behind the button is not
a settings change, so each has its own button and states its effect before it runs.

**Renaming a qtree** — `Storage → Qtrees`
ONTAP REST: `name` on `PATCH /storage/qtrees/{volume.uuid}/{id}`

1. Select the volume
2. `Rename` on the row (`Edit` is for the security style and the export policy)
3. Enter the new name and `Execute`

Success criterion: the name changes and **the id does not**. The name is part of the
`/vol/qtree` path, so clients mounted or mapped on the old name need to remount. The
operation requires `confirm`, so there is no route that runs it without that being stated --
including a direct API call. The volume-root row offers no rename.

**Quota enforcement** — `Storage → Quotas`
ONTAP REST: `quota.enabled` on `PATCH /storage/volumes/{uuid}`

1. Select the volume
2. Read the current state on the row above the rule table (`In force` / `Not in force` /
   `Initializing`)
3. `Turn on` or `Turn off`

Success criterion: the state switches, and turning it off keeps the rules. ONTAP refuses to
turn it on for a volume that has no rules, and says so. Just after turning it on the state
can be `Initializing` -- ONTAP scans the volume first, and no limit applies until it
finishes. `↻` re-reads the state.

> **Why the state needs showing**: a rule existing and a rule being applied are different
> things. Limits created on a volume whose enforcement was off did nothing, and the UI gave
> no way to tell. The field to read is `quota.state`. The field written is `quota.enabled`,
> which reports `false` even while enforcement is on.

---

## Checklist

- [ ] Resource management shows 20 cards in 5 categories
- [ ] With ONTAP unconnected, an empty state and setup guidance appear instead of an error
- [ ] Creating a group yields `✅ Group created` and refreshes the list
- [ ] A FlexClone split reflects as `Splitting n%`
- [ ] Deleting a FlexCache goes through the two-step confirmation
- [ ] Creating an `S3 → UNIX` mapping is explicitly refused
- [ ] Moving a name mapping renumbers the rules in between
- [ ] A FlexCache resize whose job is still running is not reported as a failure
- [ ] Renaming a qtree is a separate button from `Edit` and cannot run unconfirmed
- [ ] Quota enforcement state shows above the rule table, and switching it keeps the rules
- [ ] SnapMirror break / resync / delete run only after the confirmation row
- [ ] A Vscan policy can be created, enabled and deleted
- [ ] The delete button for an enabled FPolicy policy is not clickable
- [ ] Creating a cluster peer shows the passphrase once
- [ ] Accepting an SVM peer moves the state to `peered`
- [ ] Disabling a LIF or protocol runs only after the confirmation row
- [ ] The jobs tab lists the FlexCache / SnapMirror asynchronous jobs

---

## Troubleshooting

| Symptom | Cause and action |
|---------|-----------------|
| `Unknown action: <name>` | The backend is not deployed. Deploy with `npx ampx sandbox` |
| `ONTAP connection not configured` | `ONTAP_MGMT_IP` / `ONTAP_SECRET_NAME` is unset |
| A panel stays on `Connecting...` | The management endpoint is unreachable. Check the Lambda VPC configuration and security group |
| SMB panels are empty | CIFS is disabled on the SVM. An AD join is a prerequisite |
| FlexCache creation fails | Check the peer relationship with the origin cluster |
| Name mapping creation is refused | Expected when `S3 → UNIX` is selected; FSx for ONTAP manages those automatically |
| SnapMirror is empty | Only relationships whose destination is on this cluster are listed |
| `confirm=true is required` | A destructive operation was called without the confirmation row. From the UI, press `Execute` on that row |
| Cluster peer creation fails | Check the intercluster LIF is `up` and that TCP 11104, 11105 and ICMP are allowed |
| A cluster peer stays `pending` | The remote side has not accepted. The passphrase is shown once, so if it is lost, delete and re-create |
| SVM peer creation fails | Check the cluster peer has become `available` |
| An FPolicy policy cannot be deleted | It cannot be deleted while enabled. Disable it first |

---

## Related documents

- [Admin capability map](admin-capability-map.en.md) — interface ownership and implementation status
- [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md)
- [Implementation guide](IMPLEMENTATION.en.md)
- [AI agent demo guide](ai-agent-demo-guide.en.md)
