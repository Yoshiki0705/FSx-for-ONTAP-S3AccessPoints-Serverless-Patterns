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

You can also use the individual buttons:
- **🚫 Block SMB User** — blocks only the SMB user (requires domain + username)
- **🚫 Block NFS IP** — blocks only the NFS IP (requires IP address)

These are useful when you want to block one protocol without affecting the other.

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
