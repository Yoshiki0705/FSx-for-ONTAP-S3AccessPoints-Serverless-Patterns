# File portal identity and visibility — measured results

🌐 **Language / 言語**: [日本語](../ja/portal-identity-verification-results.md) | English

> A record of what was measured in a live environment about which files on FSx for ONTAP a signed-in portal user actually reaches. The relationship between the portal's Cognito authentication (Layer 1) and the NAS permissions evaluated against the File System Identity pinned to an S3 Access Point (Layer 2) was settled with controlled experiments in which only the identity varied.
>
> Read this before deciding how to register members from outside your organisation as portal users. It records **what measurement showed**, not a procedure.

## Measurement environment

| Item | Value |
|------|-------|
| Date measured | 2026-08-26 |
| Region | `ap-northeast-1` |
| ONTAP | NetApp Release 9.18.1P3D1 |
| File system | FSx for ONTAP, 128 MBps throughput |
| Volumes | One dedicated verification volume (UNIX security style, 10 GiB), plus an existing NTFS volume |
| S3 Access Points | Internet-origin, **no access point policy attached** |
| IAM caller | A single principal, identical for every column |

**How the control was built**: Layer 1 is held constant. The calling IAM principal is the same for every column and no access point carries a policy. Any difference between columns is therefore Layer 2 alone — **the UNIX or Windows user pinned to the access point, evaluated against the volume's permissions**.

Layout of the verification volume:

| Path | Owner | Mode | Intent |
|------|-------|------|--------|
| `/` | uid 5002 : gid 5000 | 0755 | Root |
| `shared/` | uid 5002 : gid 5000 | 0755 | Owner can write; others read only |
| `shared/preexisting.txt` | uid 5002 : gid 5000 | 0644 | Created beforehand over NFS |
| `private_other/` | uid 2026 : gid 2026 | 0700 | Territory of an unrelated uid |
| `private_other/other.txt` | uid 2026 : gid 2026 | 0600 | Same |

Three access points, differing only in the pinned UNIX user:

| Column | File System Identity |
|--------|---------------------|
| root | `UNIX` / `root` (uid 0) |
| portal_ro | `UNIX` / local UNIX user, uid 5001, gid 5000 |
| portal_rw | `UNIX` / local UNIX user, uid 5002, gid 5000 |

> **`FileSystemIdentity.UnixUser` accepts only `Name`.** There is no `Uid` field (confirmed with `aws fsx create-and-attach-s3-access-point --generate-cli-skeleton`). A non-root identity therefore **requires a named local UNIX user to exist on the SVM**, and the only routes to create one are the ONTAP REST API and the ONTAP CLI. The FSx API cannot do it.

---

## Measurement 1: Layer 2 does stop the portal's data path

| Operation | root (uid 0) | portal_ro (5001) | portal_rw (5002) |
|-----------|-------------|------------------|------------------|
| `HeadBucket` | ok | **ok** | **ok** |
| `ListObjectsV2` `/` (folder names) | ok | **ok** | **ok** |
| `ListObjectsV2` `shared/` | ok, 4 obj | ok, 4 obj | ok, 4 obj |
| `GetObject` `shared/preexisting.txt` | ok, 37 B | ok, 37 B | ok, 37 B |
| `ListObjectsV2` `private_other/` | ok, 1 obj | AccessDenied 403 | AccessDenied 403 |
| `GetObject` `private_other/other.txt` | ok, 22 B | AccessDenied 403 | AccessDenied 403 |
| `PutObject` `shared/` | ok | **AccessDenied 403** | ok |
| `PutObject` `private_other/` | ok | AccessDenied 403 | AccessDenied 403 |
| `DeleteObject` `shared/` | ok | **AccessDenied 403** | ok |

**Pin a read-only identity and writes stop at Layer 2.** Read, write and delete outcomes diverged per identity without a single byte of access point policy. That is a mechanism, not an operational undertaking.

**`root` (uid 0) stops nothing.** It passed everything, including a 0700 directory owned by an unrelated uid. The default in the [deployment runbook](./portal-deployment-runbook.md) is `UnixUser: root`, so **with that default the portal reaches the whole volume**.

**`HeadBucket` succeeded in every column**, including columns where every data operation was refused. Using `HeadBucket` as a reachability check reports a configuration that cannot read one byte as healthy.

**Delete is decided by the directory's write bit**, so each column was given its own delete target. Sharing one target lets the first column's success remove it, and the later columns then return `NoSuchKey`, which reads as a denial it is not.

**Folder names cross the boundary.** The contents of `private_other/` were unreadable from `portal_ro` and `portal_rw`, but **the name was visible from all three columns because the parent is 0755**. The portal's path-prefix boundary is therefore not redundant with Layer 2. With only one of the two, other teams' folder names appear in the listing.

---

## Measurement 2: a presigned URL executes as the identity of the access point it was signed against

Fetched with `curl`, holding no AWS credentials.

| Case | Signed against root AP | Signed against portal_ro AP |
|------|-----------------------|----------------------------|
| `GET private_other/other.txt` | **http 200** | http 403 |
| `GET shared/preexisting.txt` | http 200 | http 200 |
| `PUT shared/presigned_w.txt` | **http 200** | http 403 |

**A presigned URL carries the identity of the access point used to sign it.** The holder has no AWS credentials, yet a URL signed against the root access point read the contents of a 0700 directory. The `PUT` also succeeded and landed on the volume owned by uid 0.

This lands directly on the portal's implementation. `functions/presigned-url/index.py` reads only `S3_AP_ALIAS` (the default access point) and never consults `GROUP_AP_MAPPING`. **A user whose group maps to a restrictive access point still receives a download URL signed against the default one.** Where that default is `UnixUser: root`, the isolation is bypassed. The failure is not a 404; it is a request that succeeds.

> The signer was an IAM user rather than the Lambda execution role. Layer 2 is decided by the access point's identity and not by the IAM principal, so the substitution does not affect what is measured. Layer 1 differs only in that the Lambda role is scoped to `accesspoint/*`, which covers both aliases.

---

## Measurement 3: owner and mode when NFS is used alongside

Objects created through the S3 Access Point, seen from a client with the same volume mounted over NFS.

| Created via | Type on NFS | Owner | Mode |
|-------------|-------------|-------|------|
| `PutObject` through root AP | file | uid 0 : gid 1 | 0644 |
| `PutObject` through portal_rw AP | file | uid 5002 : gid 5000 | 0644 |
| Presigned `PUT` signed against root AP | file | uid 0 : gid 1 | 0644 |
| Zero-byte key ending in `/`, root AP | **directory** | uid 0 : gid 1 | **0777** |
| Zero-byte key ending in `/`, portal_rw AP | **directory** | uid 5002 : gid 5000 | **0777** |
| For contrast: created over NFS | file | creating uid | per the creating umask |

**Files are owned by the access point's identity, mode 0644.** NFS and SMB users see them as created by that identity. Which person was signed in to the portal is not visible from the NAS side.

**A zero-byte key ending in `/` becomes a real ONTAP directory, and its mode was 0777.** Five created, five at 0777 (two identities × two, plus one). It is a genuine directory rather than an S3 pseudo-folder, and **every NFS and SMB user on that volume can write into it and delete from it**. The portal's "create folder" writes exactly this key, so **folders created through the portal end up writable by anyone on the NAS side**.

The reverse direction was measured too. A file created over NFS as uid 2026 / gid 2026 / mode 0640 was readable through the root access point (29 B) but returned AccessDenied 403 through the `portal_ro` and `portal_rw` access points. **Layer 2 applies in both directions.**

---

## Measurement 4: WINDOWS-type identity

### 4-1. Access point creation is blocked by an existing S3 server on the SVM

Three WINDOWS-type access points were attempted on an AD-joined SVM. All three reached `FAILED`, with the reason in `LifecycleTransitionReason`:

```
Amazon FSx is unable to create an S3 access point because of an existing
ONTAP object storage server on SVM <svm-id>. Please delete the existing
s3 server and retry.
```

**An SVM that already has ONTAP's native S3 server (object store server) configured cannot host FSx for ONTAP S3 APs.** This is a prerequisite to check before designing access points. Deleting an existing S3 server is a decision only the SVM's users can make.

### 4-2. A domain prefix breaks it — but the symptom differs from expectation

Two access points were created on the same NTFS volume, differing only in `WindowsUser.Name`. Both reached `AVAILABLE`, and the prefixed value was stored as given.

| Operation | `WindowsUser` = `administrator` | `WindowsUser` = `EXAMPLE\administrator` |
|-----------|-------------------------------|----------------------------------------|
| `HeadBucket` | ok | **503** |
| `ListObjectsV2` | ok, 12 obj | ServiceUnavailable 503 |
| `GetObject` | ok, 12 B | ServiceUnavailable 503 |
| `PutObject` | ok | ServiceUnavailable 503 |

Three things are settled:

1. **The domain prefix is accepted at the API layer.** The access point reaches `AVAILABLE` and `describe` still shows the prefixed value. A successful creation is not evidence that it works.
2. **The failure is `503 ServiceUnavailable`, not `AccessDenied`.** Looking for a 403 sends you to the wrong layer.
3. **`HeadBucket` fails here too.** For this failure mode `HeadBucket` is not a false positive. "`HeadBucket` always passes" from Measurement 1 is about Layer 2 permission denial, which is a different thing from identity resolution being broken.

### 4-3. Data operations succeeded on an SVM with no discovered AD DCs

On an access point over an SVM that is domain-joined but where **no domain controller is discovered** (`WindowsUser` = `administrator`, NTFS volume), `HeadBucket`, `ListObjectsV2`, `GetObject`, `PutObject` and `DeleteObject` all succeeded. An access point on a non-domain-joined workgroup SVM behaved the same.

That zero DCs are discovered was confirmed through the ONTAP CLI (see below).

It was later confirmed that **this SVM does have a local SMB user of the same name as `administrator`** (the `name` returned by `/api/protocols/cifs/local-users` takes the form `<CIFS server name>\Administrator`). And Measurement 4-4 below shows that **an access point pinned to a newly created local SMB user works with no DC present**.

The reading that follows is that an identity resolving locally needs no DC. **Whether a domain account requires DC reachability remains undetermined.** This environment's domain has no reachable controller, so "it failed because the name is domain-qualified" cannot be separated from "it failed because no DC was there."

### 4-4. NTFS ACLs discriminate per identity

The symmetric counterpart to the UNIX mode-bit experiment. One dedicated NTFS volume, one IAM caller, no access point policy. `Everyone / full_control` remains inherited from the volume root, and **the difference is made by explicit deny ACEs alone**.

| Path | Explicit ACE |
|------|-------------|
| `shared/` | Write rights denied for the identity to be read-only |
| `private_other/` | `full_control` denied for both non-privileged identities |

Results across four access points differing only in the pinned identity. The fourth uses the local user name with the **CIFS server name as a prefix**.

| Operation | administrator | portalro | portalrw | `<CIFS server>\portalro` |
|-----------|--------------|----------|----------|-------------------------|
| `HeadBucket` | ok | ok | ok | ok |
| `ListObjectsV2` `/` | ok | ok | ok | ok |
| `ListObjectsV2` `shared/` | ok, 6 obj | ok, 6 obj | ok, 6 obj | ok, 6 obj |
| `GetObject` `shared/preexisting.txt` | ok, 37 B | ok, 37 B | ok, 37 B | ok, 37 B |
| `ListObjectsV2` `private_other/` | ok, 2 obj | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `GetObject` `private_other/other.txt` | ok, 42 B | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `PutObject` `shared/` | ok | **AccessDenied 403** | ok | **AccessDenied 403** |
| `PutObject` `private_other/` | ok | AccessDenied 403 | AccessDenied 403 | AccessDenied 403 |
| `DeleteObject` `shared/` | ok | **AccessDenied 403** | ok | **AccessDenied 403** |

**NTFS ACLs discriminate as strongly as UNIX mode bits.** The read-only identity is stopped on write and delete with `AccessDenied 403`, and the directory carrying a deny can be neither listed nor read. **Pinning a read-only identity for external users is a mechanism on NTFS volumes too, not an undertaking.**

**The CIFS-server-prefixed form behaved identically to the bare name.** That changes how Measurement 4-2 should be read. **What breaks is not "a form containing a backslash."** A prefix naming the local account namespace works; a prefix naming the domain returned 503. The distinction is not the prefix but **which namespace the name is resolved in**.

Ownership of the written objects was checked too.

| Written through | Owner |
|-----------------|-------|
| An AP pinned to a non-privileged local SMB user | That user |
| An AP pinned to a privileged account | `BUILTIN\Administrators` (the usual Windows normalisation) |

The parent directory's ACEs were inherited by the files. **As on the UNIX side, the NAS sees a file created by the identity pinned to the access point; which person was signed in to the portal is not visible.**

> **There is a 0777 equivalent on NTFS.** A new volume's root carries `Everyone / full_control`, and directories created through an access point inherited it. Same consequence as directories becoming 0777 on the UNIX side: **with the defaults, everyone on the NAS side can write.**

---

## Settled as a by-product

### ONTAP returns "User is not authorized" for a wrong password and for a locked account alike

Confirmed with a control that sent a deliberately wrong password once.

| Sent | Response |
|------|----------|
| A wrong password | HTTP 401, `code 6691623`, `"User is not authorized."` |
| The correct stored credential, account locked | HTTP 401, `code 6691623`, `"User is not authorized."` |

**The bodies are identical, so the cause cannot be read from this message.** A wrong password, an absent user, and a locked-out account all produce the same string. It cannot be used to separate layers.

That ambiguity produced a real misdiagnosis here. Endpoints called during the lockout described below were nearly recorded as "endpoints `fsxadmin` is not authorized for". **After the lockout was cleared, the same endpoints with the same credential all answered `http=200`.**

| Endpoint | While locked | After clearing |
|----------|-------------|----------------|
| `/api/protocols/cifs/local-users` | 401 / 6691623 | 200 |
| `/api/private/cli/vserver/cifs/users-and-groups/local-user` | 401 / 6691623 | 200 |
| `/api/private/cli/vserver/cifs/users-and-groups/local-group` | 401 / 6691623 | 200 |
| `/api/protocols/file-security/permissions/{svm}/{path}` | 401 / 6691623 | 200 |
| `/api/storage/volumes` | 401 / 6691623 | 200 |

**No per-endpoint authorization restriction existed.** `file-security/permissions`, which the portal's `getFilePermissions` depends on, is callable as `fsxadmin`.

**The shape of this misdiagnosis is what is worth keeping.** Because a different endpoint had been succeeding moments earlier, a newly appearing failure was read as a property of the endpoint. It was a change of state in the account. **A control on an endpoint that should succeed, held in the same session, would have separated the two on the first attempt.**

### `discovered_servers` is omitted entirely when empty

The behaviour of the field used to judge AD DC reachability was settled using field-name validation as the control.

| `fields=` requested | Response |
|--------------------|----------|
| A non-existent field name | `code 262197`, "invalid for field `fields`" |
| `discovered_servers` | **no error**, but the field is absent from the response |
| `discovered_servers` (collection GET) | absent from all 6 records |

No error means the field name is valid. Therefore **ONTAP 9.18.1P3D1 omits `discovered_servers` when it is empty rather than returning `[]`**. That the actual DC count was zero was confirmed separately: `/api/private/cli/vserver/cifs/domain/discovered-servers` returned `num_records: 0`.

As a result, the "empty list means DC unreachable" branch in `shared/ad_health_check.py` is never reached. Even on an SVM with zero DCs, execution falls into the `discovered is None` branch and proceeds optimistically with `dc_reachable=None` → `is_healthy=True`. **It cannot detect the failure it was built to detect.**

---

## What needs correcting in existing documentation and code

| Target | Current text / implementation | Measured |
|--------|------------------------------|----------|
| `docs/agent/pitfalls-ad-smb.md` | `WindowsUser.Name` must be the username only; `DOMAIN\user` gives `AccessDenied` on the data plane | The symptom is `503 ServiceUnavailable` and `HeadBucket` fails too. Also **a backslash is not itself forbidden** — the CIFS-server-prefixed form works. The distinction is the namespace resolved in |
| `docs/agent/pitfalls-ad-smb.md` | AD-joined SVMs need DC reachability for every data operation; `HeadBucket` is a false positive | A locally resolving identity succeeds at every operation with zero DCs. The premise should be stated for domain accounts only |
| `shared/ad_health_check.py` | Treats `discovered_servers == []` as DC unreachable | The field is omitted when empty, so that branch is unreachable |
| ONTAP connection diagnosis | No settled reading for `6691623` | Identical string for a wrong password, an absent user and a lockout. A lock does not self-clear at `lockout-duration = 0` |
| `functions/presigned-url/index.py` | Fixed to `S3_AP_ALIAS`, no prefix check | Signs with the default AP's identity, allowing the isolation to be bypassed |
| Listing in `functions/list-files/index.py` | Root listing does not filter `CommonPrefixes` against the boundary | Layer 2 also leaves folder names visible, so both paths have the gap |
| `docs/en/portal-deployment-runbook.md` | Default is `UnixUser: root` | root is subject to no NAS permission at all |
| The portal authorization model document | Says nothing about how a portal user relates to an ONTAP identity | Identity is decided per access point, not per user |

---

## Not verified

**A list kept so that unmeasured things are not reported as measured.**

- **Whether DC reachability is required when a domain account is the identity.** That a locally resolving identity works without a DC is settled in 4-4, but this environment's domain has no reachable controller, so "domain-qualified name" cannot be separated from "no DC present". **A re-measurement in an environment with a reachable DC is needed.**
- **Whether the `0777` / `Everyone` defaults can be changed.** Both the UNIX 0777 and the NTFS `Everyone / full_control` reproductions are settled; whether an access point or volume setting alters them was not investigated.
- **Whether ONTAP's failed-login counter resets on a successful login.** The lockout threshold and its lack of self-recovery are settled; the path to five attempts is not.
- **Behaviour on other ONTAP releases.** Everything here is one cluster on 9.18.1P3D1.

## What happened during the measurement — `fsxadmin` locked out

Part-way through, ONTAP REST calls that had been succeeding began returning 401. A record of the diagnosis and the recovery.

| Checked | Result |
|---------|--------|
| When the stored credential was last changed | A week before the measurement; unchanged during it |
| Whether the request carries Basic auth | It does; `WWW-Authenticate: Basic realm="ONTAP"` received |
| Cluster management LIF / SVM management LIF | Both 401 |
| Retry after 20 minutes | Still 401 |
| Recovery | Reset `FsxAdminPassword` via `aws fsx update-file-system` → back to 200 immediately |

Reading the account configuration after recovery **settled why waiting does not help.**

| `security login role config` (role = `fsxadmin`) | Value |
|---|---|
| `max-failed-login-attempts` | **5** |
| `lockout-duration` | **0** |
| `delay-after-failed-login` | 4 |
| `passwd-expiry-warn-time` | `unlimited` |
| `passwd-minlength` | 8 |
| `disallowed-reuse` | 6 |

**With `lockout-duration = 0`, a lock reached after five failures does not clear on its own.** An administrator has to intervene, by resetting the password or unlocking the account. `passwd-expiry-warn-time` of `unlimited` rules out password expiry as the cause.

**What is settled in this environment is the threshold and the fact that it does not self-clear; the path to five was not identified.** Only one deliberately wrong credential was sent to this cluster during the measurement, and successes continued after it, so the counter may have carried failures from before the session. Whether ONTAP's failure counter resets on a successful login was not checked.

**The operational lesson is the combination of a low threshold and no self-recovery.** Sending a wrong value to separate a credential problem **spends part of a five-attempt budget belonging to a shared resource**, and where `lockout-duration = 0` that budget does not come back. Controls of this kind are necessary, but their target should be a disposable account.

The FSx API is unaffected by the lockout, so volume and access point creation and deletion continued. Only work requiring ONTAP REST — local UNIX user administration and the like — stops.

---

## Reproduction steps

1. Create one volume with UNIX security style.
2. Through the ONTAP REST API, create one local UNIX group and two local UNIX users. `FileSystemIdentity` accepts only a name, so this step cannot be skipped.
3. Mount over NFS and set owners and modes as in "Layout of the verification volume" above.
   - **Do not let the read-only identity's primary group match the group of a writable directory.** If it does, the group write bit lets it write, and you are not measuring "read-only".
4. Create three access points differing only in identity. Attach no access point policy.
5. Run every read operation for all columns before running any write operation.
   - **Do not interleave them.** An earlier column's successful `PutObject` contaminates later columns' object counts and looks like a difference between identities.
6. Give each column its own delete target.
7. Presign the same key against both a restrictive and a permissive access point, and fetch with a client that holds no AWS credentials.

To measure the NTFS side, replace steps 1-3 with the following.

1. Create one volume with NTFS security style and two local SMB users (in `<CIFS server name>\<username>` form).
2. Create one access point pinned to a privileged account first, and **create the directories and files through that access point**. A new volume has no share, so a Windows client cannot write to it.
3. Make the difference with **explicit deny ACEs** added through the ACL endpoint of `file-security/permissions`. Removing the `Everyone / full_control` inherited from the root requires a separate privilege to break inheritance.
   - Applying an ACE is asynchronous and returns a job. **Do not treat the response as evidence; read the descriptor back and confirm the ACE landed.**

## Related documents

| Document | Content |
|----------|---------|
| [Portal authorization model](./portal-authorization-model.md) | Per-feature authorization by Cognito group |
| [Multi-tenant design](./multi-tenant-design.md) | Splitting access points per group |
| [Deployment runbook](./portal-deployment-runbook.md) | Access point creation and configuration steps |
| [S3 Access Point authorization model](../s3ap-authorization-model.en.md) | The two-layer model in detail |
| [Design considerations](../design-considerations-en.md) | Layer 1 / Layer 2 separation and `FileSystemIdentity` immutability |
