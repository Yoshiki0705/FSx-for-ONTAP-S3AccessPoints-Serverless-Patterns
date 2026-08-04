# ARP/AI Isolation Demo Guide

> Demonstrates the portal's incident response capabilities: detecting ransomware activity via ARP/AI, then isolating compromised users/IPs directly from the browser — without external tools.

## Prerequisites

| Requirement | How to verify |
|---|---|
| Amplify Gen2 portal deployed | `make sandbox` completed, http://localhost:5173 accessible |
| VPC Lambda configured with ONTAP management LIF access | `ONTAP_MGMT_IP` env var set, SG allows TCP/443 outbound |
| Cognito user in `storage-admin` group | AWS Console → Cognito → User Pool → Groups → storage-admin → add user |
| FSx for ONTAP with ARP enabled (or SimulationMode) | System Manager → Volume → Anti-Ransomware → Enabled/Learning |
| ONTAP 9.14.1+ | `system image show` via CLI |

> **SimulationMode**: Without a real FSx for ONTAP, the Lambda returns mock responses. The UI workflow is fully exercisable — only the ONTAP REST API calls are skipped. Set `ONTAP_MGMT_IP=""` to enter SimulationMode.

## Architecture

```
Browser (storage-admin user)
    │
    ▼
Amplify Portal → AppSync (containThreat mutation)
    │                        │
    │                        ▼ (storage-admin group check)
    │
    ▼
ArpResponseLambdaDataSource
    │
    ▼
VPC Lambda (functions/data-protection/handler.py)
    │
    ▼
ONTAP REST API (management LIF, TCP/443)
    │
    ├─ POST /name-services/name-mappings       → Block SMB user
    ├─ POST /export-policies/{id}/rules        → Block NFS IP
    ├─ POST /storage/volumes/{id}/snapshots    → Evidence snapshot
    └─ DELETE /protocols/cifs/sessions/{...}   → Disconnect sessions
```

## Demo Walkthrough (5 minutes)

### Step 1: View ARP Status

1. Open the portal at http://localhost:5173
2. Sign in with a user in the `storage-admin` Cognito group
3. Navigate to **Data Protection → 🛡️ ARP/AI** in the sidebar
4. Verify the status shows:
   - State: **Active Protection** (enabled) or **Learning Mode** (dry_run)
   - Threat Assessment: color-coded banner (green = none, red = high)

### Step 2: Simulate a Threat Detection

If you have a live environment with ARP enabled, trigger test activity:

```bash
# On an NFS client connected to the same volume:
# Rapidly rename many files with ransomware-like extensions
for i in $(seq 1 50); do
  touch /mnt/fsxn/test_file_$i.docx
  mv /mnt/fsxn/test_file_$i.docx /mnt/fsxn/test_file_$i.docx.encrypted
done
```

After a few minutes, ARP should detect the pattern and the threat level will change to `moderate` or `high`.

> **Without live ARP**: Skip to Step 3 — the containment actions work regardless of threat level. The UI shows them below the status section.

### Step 3: Execute Containment from the Portal

1. In the ARP/AI section, scroll to **Incident Response Actions**
2. Select the **Contain** tab
3. Fill in the threat details:
   - **Domain**: `CORP` (or your AD domain)
   - **Username**: `testuser` (the compromised account)
   - **Client IP**: `10.0.5.99` (the attacker's workstation IP)
   - **Reason**: "ARP/AI detected high-probability ransomware"
4. Click **🛡️ Contain Threat**
5. A confirmation row appears stating what the action will do — it creates a snapshot, blocks the targets and disconnects their SMB sessions, across the whole SVM. Click **Run** to proceed, or **Cancel** to go back.

![The containment form in the portal with domain, username, client IP and reason filled in. Below the four action buttons, a confirmation row explains that the action creates a snapshot, blocks the targets and disconnects their SMB sessions across the whole SVM, with Run and Cancel buttons](../screenshots/arp-containment-confirm.png)

> **Why two steps**: a block removes a principal's data access SVM-wide. The Lambda enforces the same gate independently — a call arriving at AppSync without `confirm: true` is refused, so bypassing the browser does not bypass the check.

**Expected result**: The portal executes all steps in sequence:
- ✅ Creates an `incident_response_YYYYMMDD_HHMMSS` snapshot
- ✅ Blocks the SMB user via name-mapping deny rule
- ✅ Blocks the NFS IP via export-policy deny rule
- ✅ Disconnects active CIFS sessions for the user

A success message appears: "Containment complete — user blocked + snapshot created"

### Step 4: Verify Active Blocks

1. Switch to the **Active Blocks** tab
2. You should see:
   - **SMB User Blocks**: `CORP\\testuser` (position 1)
   - **NFS IP Blocks**: `10.0.5.99` (policy: default)

### Step 5: Verify from ONTAP (Optional)

```bash
# Verify name-mapping block
curl -sk -u fsxadmin:<password> \
  "https://<mgmt-ip>/api/name-services/name-mappings?svm.name=<svm>&direction=win_unix" | jq .

# Verify export-policy rule
curl -sk -u fsxadmin:<password> \
  "https://<mgmt-ip>/api/protocols/nfs/export-policies?svm.name=<svm>&name=default" | jq .

# Verify the blocked user cannot access files
# (from the user's workstation — should get Access Denied)
```

### Step 6: Unblock After Investigation

1. In the **Active Blocks** tab, click **Unblock** next to the entry
2. The block is removed and access is restored

### Step 7: Individual Actions

You can also use the individual buttons. Each one asks for confirmation, with wording specific to what it does:

| Button | Requires | What to know |
|---|---|---|
| 🚫 Block SMB User | domain + username | Denies the next authentication. An already-open session keeps working until it is dropped. |
| 🚫 Block NFS IP | IP address | Effective at the ONTAP layer immediately, but client-side attribute caching can let an existing mount read and write for up to 60 seconds. |
| 🔌 Disconnect SMB sessions | domain + username, or IP | Drops live sessions. On its own it does not stop the next login — pair it with a block. |

These are useful when you want to act on one protocol without affecting the other, or when a block is already in place and you now need to cut the sessions that survived it.

> **Ordering note**: block first, then disconnect. Disconnecting before the block is in place invites the client to reconnect successfully.

## Where the portal is self-contained, and where it needs something else

The containment primitives here are a port of `ontap_response.py` from
[fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations)
(the module docstring records this). The ONTAP mechanisms are identical —
name-mapping deny, export-policy deny rule, protective snapshot, CIFS session
disconnect. What differs is the trigger and the layers around it.

### Self-contained in the portal

| Capability | Requires |
|---|---|
| Review ARP/AI state, attack probability and suspect files | The portal reaching the ONTAP REST API |
| Block and unblock an SMB user or an NFS client IP | `storage-admin` group |
| Create a protective snapshot; lock a snapshot (WORM) | Same |
| Disconnect CIFS sessions | An AD-joined SVM |
| List active blocks and lift them individually | — |
| Audit file access that went through the S3 Access Point | CloudTrail data events + Athena |
| FlexClone a snapshot to browse it; diff two generations | — |

Every one of these runs **only when a person clicks**. Nothing in the portal
contains a threat unattended.

### Needs something outside the portal

| Goal | What it takes |
|---|---|
| Contain without waiting for a human | An SNS topic plus a response Lambda |
| Be told about a detection instead of finding it | EMS → webhook → SIEM or an observability platform |
| Cut NFS off immediately, without the client cache window | A VPC NACL deny rule (network layer) |
| Avoid leaving a false-positive block in place indefinitely | TTL auto-unblock (EventBridge Scheduler) |
| Apply the same block across several SVMs at once | A multi-SVM fan-out |
| Judge a recovery point before restoring from it | A verification workflow (FlexClone + isolated scan) |
| Detect anomalies against a per-user ML baseline | A SIEM with anomaly detection, or a dedicated storage security product |
| Trace file access that arrived over NFS or SMB directly | An ONTAP audit log / FPolicy delivery pipeline |

> **Audit scope note**: the portal's audit trail reads CloudTrail S3 data events
> for the S3 Access Point. Access that arrived over NFS or SMB does not appear
> there — that requires ONTAP's own audit log or FPolicy events. The two are
> complementary, not substitutes, and it is easy to assume the portal shows both.

So the portal is the **hands** of incident response: it puts the ONTAP
containment actions in a browser, behind Cognito groups, with confirmation and
an audit trail. If you need something watching around the clock and moving those
hands for you, detection and response belong in a pipeline. Conversely, if you
already detect in a SIEM and only lack a way to stop it at the storage layer, an
SNS-triggered response Lambda fits that shape better than a portal button.

## Parameter Reference

### Environment Variables (Lambda)

| Variable | Description | Example |
|---|---|---|
| `ONTAP_MGMT_IP` | FSx for ONTAP management endpoint | `10.0.1.100` |
| `ONTAP_SECRET_NAME` | Secrets Manager secret with username/password | `fsxn/ontap-creds` |
| `VOLUME_NAME` | Target volume name | `vol1` |
| `SVM_NAME` | Storage Virtual Machine name | `svm-prod` |

### Secrets Manager Format

```json
{
  "username": "fsxadmin",
  "password": "<your-password>"
}
```

### Cognito Group Requirement

ARP response mutations require the calling user to be in the `storage-admin` Cognito group. Regular authenticated users can view ARP status (read-only) but cannot execute containment actions.

To add a user to the group:
```bash
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <pool-id> \
  --username <email> \
  --group-name storage-admin
```

## Protected Accounts

The following accounts cannot be blocked (safeguard against accidental lockout):
- `fsxadmin`, `administrator`, `admin`, `vsadmin`, `system`

To add custom protected accounts (e.g., service accounts):
```bash
# Lambda environment variable
PROTECTED_ACCOUNTS_EXTRA="svc-backup,svc-ml-pipeline,app-service"
```

## Cooldown Logic

Snapshot creation includes a 15-minute cooldown to prevent snapshot storms during sustained attacks. If a snapshot with the `incident_response_` prefix was created within the last 15 minutes, a new one is not created. Set `cooldown_minutes=0` to disable.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "ONTAP connection not configured" | `ONTAP_MGMT_IP` or `ONTAP_SECRET_NAME` not set | Check Lambda env vars in portal-config.ts |
| "SVM not found" | SVM name doesn't match | Verify `SVM_NAME` matches `aws fsx describe-storage-virtual-machines` |
| "Cannot block protected account" | Attempting to block fsxadmin/admin | Use a non-protected username |
| "Export policy not found" | Policy name mismatch | Check `policyName` param (default: "default") |
| Mutations return "Not Authorized" | User not in storage-admin group | Add user to Cognito `storage-admin` group |
| Block succeeds but user still has access | NTFS security style volume | Name-mapping blocks only work on UNIX/MIXED volumes |

## Security Considerations

- **All containment actions are logged** in CloudTrail (AppSync data events + Lambda execution)
- **Confirmation is enforced in the Lambda**, not only in the browser — `blockSmbUser`, `blockNfsIp`, `containThreat` and `disconnectSessions` refuse a call without `confirm: true`. Unblocking is deliberately not gated.
- **Blocks expire.** The default is 24 hours, and the operator can choose 1 hour to 7 days, or "indefinite", at the point of blocking. A scheduled sweep lifts blocks whose expiry has passed, so a false positive becomes an indefinite lockout only when someone explicitly chooses indefinite.
  - The lift can be later than the expiry by up to one sweep interval (15 minutes by default). The expiry is a lower bound on when access returns, not an exact time.
  - The sweep only lifts blocks this portal created. A block placed elsewhere — at the ONTAP CLI, by another automation — is shown as "Not portal-managed" and left alone. The portal cannot know the intent behind it, and lifting it would be a silent loss of containment.
  - To lift a block before its expiry, or to lift an indefinite one, use the Active Blocks tab.
- **Protected accounts** prevent accidental lockout of admin credentials
- **Input validation** blocks injection attempts (`;`, `|`, `&`, `` ` `` in usernames)
- **Cognito group authorization** ensures only designated admins can execute response actions
- **Cooldown prevents snapshot storms** during sustained attacks
- **AD-joined SVMs use `nobody` replacement** instead of space (verified to persist on ONTAP 9.17.1+)

## Related Resources

- [ARP/AI Documentation — AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)
- [ONTAP Anti-Ransomware REST API](https://docs.netapp.com/us-en/ontap-restapi/)
- [fsxn-observability-integrations (source implementation)](https://github.com/Yoshiki0705/fsxn-observability-integrations)
- [DII Storage Workload Security reference](https://docs.netapp.com/us-en/cloudinsights/cs_restrict_user_access.html)
- [日本語版](../ja/arp-ai-isolation-demo-guide.md)
