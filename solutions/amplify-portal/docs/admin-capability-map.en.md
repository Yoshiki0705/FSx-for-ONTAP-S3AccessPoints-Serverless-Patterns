# Admin capability map — what each interface covers, and what this portal implements

🌐 **Language / 言語**: [日本語](admin-capability-map.md) | **English**

> Purpose: set out which ONTAP management interface owns which area, and record
> how far this portal is implemented today, based on measurement rather than intent.

[日本語](admin-capability-map.md)

---

## Summary

This portal is **a layer that makes operations available through the ONTAP REST API
runnable from a screen behind Cognito authentication**.

For Amazon FSx for NetApp ONTAP (hereafter FSx for ONTAP), the interfaces reachable
without routing through an additional third-party SaaS are three: the AWS Management
Console / FSx API, the ONTAP CLI over SSH, and the ONTAP REST API. ONTAP System Manager
is not among them — see [FSx for ONTAP management interfaces](../../../docs/en/fsx-ontap-management-interfaces.md)
for the sources and the misconceptions. So what this portal should be compared against
is **the ONTAP CLI and the REST API**, not System Manager.

Against those two, it differs in two respects.

- **Delegation**: a specific operation can be given to someone outside storage
  administration (security, compliance, data protection) without handing them
  cluster-administrator SSH.
- **Record**: who ran which operation and when is retained against a Cognito principal.

**Cluster peering and SVM peering** matter in particular: the AWS Management Console
for FSx for ONTAP has no surface for them, so until now they required the ONTAP CLI or
hand-written REST calls. This portal makes that area available from the UI.

The ONTAP version, the nodes and the disks and shelves are **operated by AWS**. They do
not exist as customer operations, so they appear neither in this portal nor in any other
interface.

---

## What each interface covers

Rows marked "ONTAP CLI / REST API" name how the operation is performed without this portal.

| Area | Without this portal | Position of this portal |
|------|--------------------|------------------------|
| ONTAP version, nodes, disks and shelves | Operated by AWS (no customer operation) | Out of scope |
| Creating file systems, SVMs and volumes; backups | AWS Management Console / FSx API | Partial (volume operations implemented) |
| Day-to-day volume, qtree and quota operations | ONTAP CLI / REST API | Implemented |
| NAS access control (export policies, SMB shares) | ONTAP CLI / REST API | Implemented |
| Identity mapping (Windows ↔ UNIX), SMB local users | ONTAP CLI / REST API | Implemented |
| Snapshots, SnapLock, tamperproof snapshots | ONTAP CLI / REST API | Implemented |
| Ransomware detection (ARP/AI) review and response | ONTAP CLI / REST API | Implemented |
| FlexCache, FlexClone | ONTAP CLI / REST API | Implemented |
| Replication (SnapMirror) status and operations | ONTAP CLI / REST API | Implemented |
| Virus scanning (Vscan) and FPolicy configuration | ONTAP CLI / REST API | Implemented |
| Cluster peers, SVM peers | ONTAP CLI / REST API | Implemented (no Management Console surface) |
| Nodes, licences, LIFs, protocol services, DNS, jobs | ONTAP CLI / REST API | Implemented (read) |
| Long-term metric retention, capacity trend analysis | Amazon CloudWatch / ONTAP REST API | The `operations/` patterns in this repository |
| File access audit aggregation and anomaly detection | FPolicy → EventBridge → patterns in this repository | `solutions/event-driven/fpolicy/` |
| End-user file browsing and sharing | This portal | Implemented |

> **Observability and audit note**: vendor observability suites and audit-analytics
> products are a valid option. This repository standardises on AWS-native mechanisms
> (Amazon CloudWatch, ONTAP REST API, FabricPool, AWS DataSync,
> Snapshot / FlexClone / SnapMirror) instead. That choice avoids introducing an
> additional operational platform and keeps the configuration in IaC.
> Which fits better depends on the platform already in operation and on how granular
> the audit requirement is.

---

## Mapping to ONTAP capability areas

The table is organised by ONTAP's capability areas.
"Out of scope" reflects a deliberate split of responsibility, not a missing feature.

The areas follow ONTAP System Manager's screen layout, so that a reader who knows
System Manager can follow the mapping. That is a presentation choice, not a statement
that System Manager is available for FSx for ONTAP — see
[management interfaces](../../../docs/en/fsx-ontap-management-interfaces.md).

| Area | Main features | Coverage in this portal |
|------|--------------|------------------------|
| Dashboard | Capacity, performance and health overview | Partial (capacity, ARP/AI and EMS appear in dedicated panels; performance charts live in CloudWatch) |
| Storage | Volumes, qtrees, quotas, efficiency, LUNs | Implemented (LUNs out of scope; SAN use of FSx for ONTAP is outside this portal) |
| Network | LIFs, ports, routes, broadcast domains | Partial (LIF listing plus enable/disable; ports and routes out of scope) |
| Events | EMS alerts | Implemented |
| Protection | Snapshots, SnapLock, SnapMirror | Implemented |
| Hosts | NFS / SMB clients, iSCSI initiators | Partial (SMB local users and name mapping; iSCSI out of scope) |
| Cluster | Nodes, HA, licences, version | Implemented (read) |
| Cluster | Peering (cluster / SVM) | Implemented (create, accept, delete) |
| Cluster | Name services (DNS) | Implemented |
| Cluster | Protocol services (NFS / SMB / S3) | Implemented (enable/disable) |
| Cluster | Jobs | Implemented (read) |
| Cluster | ONTAP upgrade, disks and shelves | Out of scope (operated by AWS on FSx for ONTAP; no customer operation) |

---

## How destructive operations are handled

Write operations with a wide blast radius are two-step. The UI shows a confirmation
row, and the handler independently refuses to proceed without `confirm=true`.
A direct call that bypasses the UI is rejected the same way.

| Operation | Why confirmation is required |
|-----------|----------------------------|
| SnapMirror break | The destination becomes writable and a resync is needed to restore mirroring |
| SnapMirror resync | Depending on the direction of the delta, updates on the destination are lost |
| SnapMirror delete | The relationship is removed and re-creating it requires a baseline transfer |
| Vscan policy delete | The scope stops being scanned |
| FPolicy event / policy delete | Audit events stop being generated |
| Cluster peer / SVM peer delete | Dependent replication and FlexCache stop |
| LIF disable | The path that LIF carries (management or data) is cut |
| Protocol service disable | Clients using that protocol are disconnected |

Behaviour is also aligned with ONTAP's own constraints.

- Enabling an FPolicy policy requires `priority`; disabling omits it (ONTAP rule).
- An enabled FPolicy policy cannot be deleted, so the delete button is disabled while enabled.
- Name mappings in the `s3_unix` direction cannot be created. FSx for ONTAP manages
  those automatically for S3 Access Points.
- FlexClone creation never sends `nas.security_style`; it is inherited from the parent volume.

---

## Implementation status (measured)

Status of all 20 panels shown under `Resource management`.
Every action is implemented in the Lambda that calls the ONTAP REST API
(`functions/resource-management/handler.py`).

### Storage

| Panel | Read | Create | Modify | Delete |
|-------|:---:|:---:|:---:|:---:|
| Volumes | ○ | ○ | ○ resize | ○ |
| Qtrees | ○ | ○ | — | ○ |
| Quotas | ○ | ○ | — | ○ |
| Storage efficiency | ○ | — | — | — |
| FlexCache | ○ | ○ | — | ○ |
| FlexClone | ○ | ○ | ○ split | — |

### Access control

| Panel | Read | Create | Modify | Delete |
|-------|:---:|:---:|:---:|:---:|
| Export policies | ○ | ○ policy/rule | — | ○ policy/rule |
| SMB shares | ○ | ○ | ○ | ○ |
| QoS policies | ○ | ○ | ○ | ○ |
| Local users | ○ | ○ user/group | ○ add and remove members | ○ user/group |
| Name mapping | ○ | ○ | — | ○ |

### Data protection

| Panel | Read | Create | Modify | Delete |
|-------|:---:|:---:|:---:|:---:|
| ARP/AI protection | ○ | — | ○ state change, bulk enable | ○ clear suspects |
| Snapshot management | ○ | ○ policy | ○ enable locking | — |
| SnapLock | ○ | — | ○ retention | — |
| SnapMirror | ○ | — | ○ update now, quiesce, resume, break, resync, abort transfer | ○ delete relationship |
| Virus scanning | ○ | ○ on-access policy | ○ Vscan enable/disable, policy enable/disable | ○ policy |
| FPolicy | ○ | ○ event/policy | ○ policy enable/disable | ○ event/policy |

### Cluster

| Panel | Read | Create | Modify | Delete |
|-------|:---:|:---:|:---:|:---:|
| Peering | ○ cluster peers/SVM peers/intercluster LIFs | ○ cluster peer/SVM peer | ○ accept (passphrase / state) | ○ cluster peer/SVM peer |
| Cluster information | ○ nodes/licences/LIFs/protocols/DNS/jobs | — | ○ LIF enable/disable, protocol enable/disable, DNS update | — |

### AI services

| Panel | Read | Modify |
|-------|:---:|:---:|
| AI settings | ○ | ○ enable/disable |

---

## ONTAP REST API endpoints used

| Feature | Endpoint |
|---------|----------|
| Volumes, FlexClone | `/storage/volumes` |
| Qtrees | `/storage/qtrees` |
| Quotas | `/storage/quota/rules`, `/storage/quota/reports` |
| Export policies | `/protocols/nfs/export-policies` |
| SMB shares | `/protocols/cifs/shares` |
| QoS policies | `/storage/qos/policies` |
| SMB local users | `/protocols/cifs/local-users` |
| SMB local groups | `/protocols/cifs/local-groups` |
| Group members | `/protocols/cifs/local-groups/{svm.uuid}/{sid}/members` |
| Name mapping | `/name-services/name-mappings` |
| FlexCache | `/storage/flexcache/flexcaches` |
| SnapMirror relationships | `/snapmirror/relationships` |
| SnapMirror transfers | `/snapmirror/relationships/{uuid}/transfers` |
| Vscan | `/protocols/vscan/{svm.uuid}`, `/protocols/vscan/{svm.uuid}/on-access-policies` |
| FPolicy | `/protocols/fpolicy/{svm.uuid}/events`, `/protocols/fpolicy/{svm.uuid}/policies` |
| Snapshot policies | `/storage/snapshot-policies` |
| EMS events | `/support/ems/events` |
| Cluster peers | `/cluster/peers` |
| SVM peers | `/svm/peers` |
| Cluster information | `/cluster` |
| Nodes | `/cluster/nodes` |
| Licences | `/cluster/licensing/licenses` |
| LIFs (including intercluster) | `/network/ip/interfaces` |
| DNS | `/name-services/dns` |
| Protocol services | `/protocols/{nfs,cifs,s3}/services` |
| Asynchronous jobs | `/cluster/jobs` |

All of them connect to the management endpoint over HTTPS with the same
Secrets Manager credential. No additional AWS permissions are required.

---

## Differences caused by prerequisites

| Operation | Additional prerequisite |
|-----------|------------------------|
| SMB shares, local users, name mapping | CIFS enabled on the SVM |
| FlexCache | A peer relationship with the cluster holding the origin volume |
| FlexClone | A snapshot of the parent volume (if omitted, a snapshot is taken at creation) |
| SnapMirror operations | Only relationships whose destination is on this cluster are listed and operable |
| Vscan | An external scan engine and Vscan connector (policy definitions can be created from this portal) |
| FPolicy | An external FPolicy engine (choosing `engine: native` allows definitions without one) |
| Cluster peer | An intercluster LIF in `up` state on both clusters, and TCP 11104, 11105 plus ICMP allowed between them |
| SVM peer | The cluster peer must be `available`. After creation the remote side must accept it |

### Peering procedure

A cluster peer requires action on both sides. The portal drives one side at a time.

1. Open `Peering` → `intercluster LIF` and confirm both clusters have a LIF in `up` state.
2. In the security group, allow TCP 11104, 11105 and ICMP between the intercluster
   LIFs of both clusters.
3. On one cluster, run `Create cluster peer` and select `Generate passphrase`.
   The generated passphrase is shown **once only**.
4. On the other cluster, enter the same passphrase under `Accept`.
5. Once the state becomes `available`, create the SVM peer on the `SVM peer` tab and
   accept it on the remote side.

> **Network note**: an FSx for ONTAP file system has several ENIs. Intercluster
> traffic uses the intercluster LIF addresses, so the security group rules must be
> written against the intercluster LIF addresses, not the management LIF.

> **AD note**: when the SVM is AD-joined, every S3 Access Point data operation
> (ListObjectsV2 / GetObject / PutObject) requires reachability to the AD domain
> controllers. `HeadBucket` succeeds even when AD is unreachable, so always use a
> data operation to check connectivity. See
> [AD-joined SVM S3 AP prerequisites](../../../docs/en/ad-joined-svm-s3ap-prerequisites.md)
> for details.

---

## File operation features

Separate from the resource management panels, these are available from the
`All files` view.

| Feature | Location | Implementation |
|---------|----------|----------------|
| Folder favourites | ☆ on the row / `Favourites` | `Favorite` table. A trailing slash marks a folder |
| File favourites | ☆ on the row | As above |
| ZIP download | `📦 Download as ZIP` in the header inside a folder | `folderMutation` → dedicated Lambda → read via S3 AP → ZIP → presigned URL |
| File tags | 🏷️ on the row | `FileTag` table. Badges on the row, expand to edit |
| Inline PDF preview | Click the file name | Presigned URL rendered in an iframe |
| Office preview | Click the file name | Rendered client-side with docx-preview |
| Snapshot comparison | `🔍 Compare with snapshot` in the header | Shows the current volume and a clone side by side through their S3 APs |
| Share link | 🔗 on the row | Presigned URL. Expiry is 5 minutes, 15 minutes or 1 hour |
| Restore from snapshot | `📸 Restore from Snapshot` in the header | Creates a FlexClone through Step Functions |

ZIP download appears only inside a folder, not at the root. Limits apply to both the
file count and the total size, and are checked before generation starts.

> **Capacity note**: the ZIP is written to a temporary bucket and removed the next day
> by a lifecycle rule. The presigned URL has its own, separate expiry; after it lapses
> the archive must be regenerated.

---

## How this was verified

Implementation status is checked at two levels.

1. **Handler unit tests**: `functions/resource-management/tests/test_handler.py`
   (asserts the request path and response shaping against mocked ONTAP REST responses)

   ```bash
   cd solutions/amplify-portal/functions/resource-management
   python3 -m pytest tests/test_handler.py -q
   ```

2. **UI**: each panel is driven in the development server to confirm that real handler
   output renders correctly and that write operations are called with the expected
   parameters (`confirm=true` for destructive operations)
   (steps in the [resource management demo guide](resource-management-demo-guide.en.md))

To check connectivity against a real FSx for ONTAP file system, deploy the backend with
`npx ampx sandbox` in a VPC configuration that can reach the management endpoint.
The single hop from the deployed Lambda to a real ONTAP cluster is not covered by the
two levels above.

---

## Related documents

- [Resource management demo guide](resource-management-demo-guide.en.md) — per-panel steps
- [Implementation guide](IMPLEMENTATION.en.md) — architecture and configuration
- [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md) — connecting to the management endpoint
- [AI agent demo guide](ai-agent-demo-guide.en.md)
- [Operations optimisation patterns](../../../operations/README.md) — metric retention and capacity analysis
