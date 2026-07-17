# Nextcloud External Storage with FSx for ONTAP S3 Access Points

## Executive Summary

Nextcloud's External Storage app can connect to FSx for ONTAP volumes via S3 Access Points, presenting enterprise NAS files in Nextcloud's familiar file browser without data migration. This guide covers the setup procedure, IAM configuration, architecture options, and operational considerations.

**Key outcome**: NFS/SMB users continue working on the same volume while Nextcloud users browse, upload, and download the same files through a web interface — all without copying data.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Options](#architecture-options)
3. [IAM Configuration](#iam-configuration)
4. [Nextcloud External Storage Setup](#nextcloud-external-storage-setup)
5. [Verification Steps](#verification-steps)
6. [Processing Workflow Integration](#processing-workflow-integration)
7. [Production Hardening](#production-hardening)
8. [Constraints and Workarounds](#constraints-and-workarounds)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)
11. [Related Documents](#related-documents)

---

## Prerequisites

| Requirement | Description |
|-------------|-------------|
| FSx for ONTAP file system | Deployed with at least one volume with a junction path |
| S3 Access Point | Attached to the target volume (Internet-origin recommended) |
| Nextcloud instance | v25+ (External Storage app requires admin access) |
| IAM credentials | Access Key / Secret Key with S3 AP permissions |
| Network connectivity | Nextcloud server → S3 AP endpoint (Internet or VPC) |

**Glossary**:
- **S3 AP Alias**: The auto-generated S3 Access Point alias (e.g., `myap-abc123-s3alias`). Used as the "bucket name" in Nextcloud.
- **Internet-origin AP**: S3 AP accessible from anywhere with valid IAM credentials (no VPC binding).
- **External Storage App**: Nextcloud admin plugin that mounts remote storage backends as local folders.

---

## Architecture Options

### Option A: Internet-Origin S3 AP (Recommended for simplicity)

```
┌───────────────────────┐         ┌─────────────────────────────┐
│  Nextcloud Server     │         │  FSx for ONTAP              │
│  (EC2 / ECS / external│  HTTPS  │  ┌───────────────────────┐  │
│   hosting)            │────────▶│  │ S3 Access Point       │  │
│                       │         │  │ (Internet-origin)     │  │
│  External Storage App │         │  └───────────┬───────────┘  │
│  (Amazon S3 backend)  │         │              │              │
└───────────────────────┘         │  ┌───────────▼───────────┐  │
                                  │  │ ONTAP Volume          │  │
                                  │  │ (/vol/data)           │  │
                                  │  │ NFS + SMB + S3        │  │
                                  │  └───────────────────────┘  │
                                  └─────────────────────────────┘
```

- Nextcloud can run anywhere (AWS, on-premises, other cloud)
- No VPC placement requirement for the Nextcloud server
- S3 AP alias is used as the bucket name

### Option B: VPC-Origin S3 AP + Same-VPC Nextcloud

```
┌──────────────── VPC ────────────────────────────────────────┐
│  ┌───────────────────┐      ┌─────────────────────────────┐ │
│  │  Nextcloud (EC2)  │      │  FSx for ONTAP              │ │
│  │  + NFS mount      │──────│  Volume (/vol/data)         │ │
│  │  (optional)       │ NFS  │                             │ │
│  │                   │      │  S3 AP (VPC-origin)         │ │
│  │  External Storage │──────│                             │ │
│  │  (S3 backend)     │ S3   └─────────────────────────────┘ │
│  └───────────────────┘                                      │
│         ▲                                                    │
│         │ S3 Gateway VPC Endpoint                            │
└─────────┼────────────────────────────────────────────────────┘
          │
     (NOT supported with Internet-origin AP)
```

- Lower latency (same VPC)
- Optional NFS mount for fast preview generation
- Requires VPC-origin S3 AP + S3 Gateway VPC Endpoint

> **Important**: S3 Gateway VPC Endpoints do NOT work with Internet-origin S3 APs. If using an Internet-origin AP from within the VPC, traffic must route through NAT Gateway or Internet Gateway.

### Option C: NFS Mount Only (No S3 AP)

For environments where S3 AP is not needed for the file browsing layer:

- Nextcloud EC2 mounts the FSx for ONTAP volume via NFS
- Sub-millisecond latency for file browsing and preview
- Processing workflows still use S3 AP (separate concern)
- Requires same-VPC placement

---

## IAM Configuration

Create a dedicated IAM user (or role, if Nextcloud runs on EC2 with instance profile) with permissions scoped to the S3 Access Point.

### IAM Policy (Minimum Required)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "NextcloudS3APAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>",
        "arn:aws:s3:<REGION>:<ACCOUNT_ID>:accesspoint/<AP_NAME>/object/*"
      ]
    }
  ]
}
```

Replace:
- `<REGION>`: Your AWS region (e.g., `ap-northeast-1`)
- `<ACCOUNT_ID>`: Your 12-digit AWS account ID
- `<AP_NAME>`: Your S3 Access Point name

### Security Notes

- Use a dedicated IAM user for Nextcloud — do not reuse credentials from other applications
- Rotate access keys periodically (consider AWS Secrets Manager for automation)
- If Nextcloud runs on EC2, prefer an IAM instance profile over static access keys
- S3 AP resource policy is NOT required for same-account access (IAM identity policy is sufficient)

---

## Nextcloud External Storage Setup

### Step 1: Enable External Storage App

1. Log in to Nextcloud as administrator
2. Navigate to **Apps** (top-right menu → Apps)
3. Search for "**External storage support**"
4. Click **Enable**

### Step 2: Configure S3 Backend

1. Go to **Settings** → **Administration** → **External storage**
2. Click **Add storage** → Select **Amazon S3**
3. Fill in the configuration:

| Field | Value | Notes |
|-------|-------|-------|
| **Folder name** | `FSxONTAP-Data` (or your choice) | Appears as a folder in Nextcloud Files |
| **Authentication** | Access key | |
| **Bucket** | `<S3-AP-ALIAS>` | The S3 AP alias (e.g., `myap-abc123-s3alias`) |
| **Hostname** | `s3.<REGION>.amazonaws.com` | Regional S3 endpoint |
| **Port** | (leave empty) | Defaults to 443 |
| **Region** | `<REGION>` | e.g., `ap-northeast-1` |
| **Enable SSL** | ✅ Checked | Always use HTTPS |
| **Enable Path Style** | ✅ Checked | **Required for S3 AP aliases** |
| **Access key** | `<IAM_ACCESS_KEY_ID>` | From the dedicated IAM user |
| **Secret key** | `<IAM_SECRET_ACCESS_KEY>` | From the dedicated IAM user |
| **Available for** | (select users/groups) | Scope access as needed |

> **Critical**: **Enable Path Style** must be checked. S3 Access Point aliases use path-style addressing (`https://s3.region.amazonaws.com/ap-alias/key`), not virtual-hosted-style.

### Step 3: Verify Connection

After saving, Nextcloud shows a colored circle next to the mount:
- 🟢 Green: Connected successfully
- 🔴 Red: Connection failed (check credentials, endpoint, or network)
- 🟡 Yellow: Partially configured

Click on **Files** in the top navigation. The configured folder name should appear. Browse into it to see FSx for ONTAP volume contents.

---

## Verification Steps

After configuration, verify the following operations:

```bash
# From Nextcloud UI:
# 1. Browse: Navigate to the external storage folder → see files
# 2. Download: Click a file → download to local machine
# 3. Upload: Drag a file into the folder → verify via NFS/SMB

# From NFS/SMB client (verify multiprotocol visibility):
# 1. Write a file via NFS: echo "test" > /mnt/fsxn/test-from-nfs.txt
# 2. Refresh Nextcloud → file should appear immediately
# 3. Upload via Nextcloud → verify file appears on NFS mount
```

| Test | Expected Result | If Failed |
|------|----------------|-----------|
| List files | FSx for ONTAP volume contents visible | Check IAM policy, bucket name (use AP alias) |
| Download file | File downloads to browser | Check `s3:GetObject` permission |
| Upload file (< 5GB) | File appears on NFS/SMB mount | Check `s3:PutObject` permission |
| Upload file (> 5GB) | Should succeed via multipart | Check multipart permissions |
| Delete file | File removed from volume | Check `s3:DeleteObject` permission |
| NFS write → Nextcloud visible | Immediate visibility | Refresh Nextcloud file listing |

---

## Processing Workflow Integration

Nextcloud file browsing and the serverless processing patterns in this repository can work together. Users browse and tag files in Nextcloud, then processing workflows operate on the same data via S3 AP.

### Option 1: Webhook Trigger (Recommended)

```
User tags file in Nextcloud
  → Nextcloud Flow/Workflow App fires HTTP webhook
    → API Gateway
      → Step Functions StartExecution
        → Processing Lambda reads file via S3 AP
          → Results written back (visible in Nextcloud)
```

**Nextcloud Flow configuration**:
1. Go to **Settings** → **Flow** (or **Workflow** in older versions)
2. Create a rule: "When a file is tagged with `process-ai`"
3. Action: "Send a web request" → `POST https://<api-gw-url>/start`
4. Body: `{"file_path": "{file}", "pattern": "uc1-legal"}`

### Option 2: Scheduled Scan (Existing Pattern)

The existing EventBridge Scheduler pattern scans the volume periodically. No Nextcloud-specific configuration needed — files uploaded via Nextcloud are automatically picked up on the next scan cycle.

### Option 3: Manual API Call

Add a custom Nextcloud app or use the "External sites" app to embed a button that calls the processing API:

```javascript
// Nextcloud custom app (simplified)
async function triggerProcessing(filePath) {
  const response = await fetch('https://<api-gw-url>/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath, pattern: 'uc1-legal' })
  });
  return response.json();
}
```

---

## Production Hardening

### Security Checklist

| Item | Action |
|------|--------|
| HTTPS only | Configure ALB with ACM certificate |
| WAF | Attach AWS WAF to ALB (rate limiting, geo-restriction) |
| IAM key rotation | Automate via Secrets Manager + Nextcloud occ command |
| Nextcloud updates | Schedule regular updates (security patches) |
| Database encryption | Enable RDS encryption at rest |
| Access logging | Enable ALB access logs + Nextcloud audit log app |
| Backup | RDS automated backup + Nextcloud config backup |
| MFA | Enable Nextcloud TOTP or WebAuthn plugin |
| Server disk encryption | Enable EBS/EFS encryption (protects Nextcloud cache/temp files) |

> **Security note**: FSx for ONTAP volumes are protected by NVE (encryption at rest), and S3 AP uses TLS (encryption in transit). However, Nextcloud cache and temporary files are written to the server's local disk. Always enable EBS/EFS encryption to protect this data.

### Recommended Nextcloud Apps

| App | Purpose |
|-----|---------|
| **External storage support** | Core requirement for S3 AP integration |
| **Auditing / Logging** | Compliance audit trail |
| **Flow** | Webhook triggers for processing workflows |
| **Two-Factor TOTP** | MFA for admin and user accounts |
| **LDAP user and group backend** | AD/LDAP integration |
| **Brute-force settings** | Login protection |
| **Files access control** | Fine-grained file access rules |

### Monitoring

```bash
# CloudWatch metrics to monitor:
# - S3 AP: request count, latency (via CloudTrail)
# - EC2: CPU, memory, disk (Nextcloud server)
# - ALB: request count, 5xx errors, latency
# - RDS: connections, CPU, storage

# Nextcloud health endpoint:
curl -s https://nextcloud.example.com/status.php | jq .
# Expected: {"installed":true,"maintenance":false,"needsDbUpgrade":false,...}
```

---

## Constraints and Workarounds

| Constraint | Impact | Workaround |
|-----------|--------|-----------|
| **Presigned URLs not supported** | Nextcloud cannot generate direct download links to S3 AP | Nextcloud proxies all downloads through its server process. This is transparent to users but adds server load. |
| **PutObject max 5 GB** | Large file uploads limited | Nextcloud uses multipart upload for large files. Verify S3 AP multipart support with your ONTAP version (9.15.1+). |
| **ListObjectsV2 max 1000/request** | Large directories need pagination | Nextcloud handles this automatically via its S3 backend library. |
| **No S3 event notifications** | Cannot trigger on S3 AP upload events | Use Nextcloud Flow/Workflow webhook, or FPolicy (ONTAP-native event), or scheduled scan. |
| **AD-joined SVM: DC must be reachable** | If AD DC is down, all S3 AP operations fail (AccessDenied) | Monitor AD DC health. See [AD-Joined SVM S3 AP Prerequisites](./en/ad-joined-svm-s3ap-prerequisites.md). |
| **Nextcloud file locking** | Nextcloud's file locking does not extend to NFS/SMB clients | Concurrent edits from Nextcloud + NFS may conflict. Use ONTAP oplocks/byte-range locks for coordination. |
| **Thumbnail/preview generation** | S3 AP GetObject for every preview adds latency | Option A: Accept the latency. Option B: Use NFS mount for preview generation (same-VPC only). |

### S3 AP vs NFS Mount: When to Use Which in Nextcloud

| Use Case | Recommended Backend | Reason |
|----------|---|---|
| Remote/multi-site access | S3 AP (Internet-origin) | No VPC requirement, accessible from anywhere |
| Same-VPC with low latency needs | NFS mount or VPC-origin S3 AP | Sub-ms latency for browsing |
| Large-scale preview/thumbnail | NFS mount | Avoids S3 API call overhead per file |
| Hybrid (browse + process) | S3 AP for both Nextcloud and Lambda | Consistent access pattern |
| Read-heavy, write-light | S3 AP | Sufficient for typical file portal usage |

---

## Troubleshooting

### Common Issues

**Red circle (connection failed) after configuration:**

1. Verify IAM credentials are correct and active
2. Check that the bucket field contains the **S3 AP alias** (not the volume name or bucket ARN)
3. Ensure **Enable Path Style** is checked
4. Verify the region matches the S3 AP region
5. Test from Nextcloud server: `aws s3 ls s3://<ap-alias>/ --region <region>`

**Files not visible (empty listing):**

1. Verify the S3 AP is attached to a volume with files
2. Check IAM policy includes `s3:ListBucket` on the AP ARN (without `/object/*`)
3. Verify the volume has a junction path (is mounted in the SVM namespace)

**Upload fails:**

1. Check `s3:PutObject` permission on `accesspoint/<name>/object/*`
2. Verify file size < 5 GB for single PutObject (multipart for larger)
3. Check ONTAP volume has available space

**Files uploaded via Nextcloud not visible on NFS:**

1. FSx for ONTAP S3 AP writes are immediately visible on NFS — no delay expected
2. Check if the NFS client has a stale cache: `ls -la` or remount with `noac` option
3. Verify the file was written to the correct path (S3 AP root = volume junction path)

**AccessDenied on AD-joined SVM:**

1. This is likely an AD DC connectivity issue, not an IAM issue
2. Check: `HeadBucket` succeeds but `ListObjectsV2` fails = AD DC unreachable
3. Verify AD DC is running and reachable from FSx SVM ENIs
4. See [AD-Joined SVM S3 AP Prerequisites](./en/ad-joined-svm-s3ap-prerequisites.md)

---

## FAQ

**Q: Can Nextcloud users edit files directly on the FSx for ONTAP volume?**
A: Yes. PutObject (via S3 AP) writes directly to the ONTAP volume. The file is immediately visible to NFS/SMB users. However, Nextcloud's collaborative editing (e.g., Collabora/OnlyOffice) requires a temporary copy, which is then written back.

**Q: Does Nextcloud Desktop Client sync work with External Storage?**
A: Yes, with caveats. External storage folders can be synced by the desktop client, but performance depends on file count and network latency to the S3 AP endpoint. For large volumes (100K+ files), consider selective sync.

**Q: Can I restrict which Nextcloud users see the FSx for ONTAP files?**
A: Yes. The "Available for" field in External Storage configuration restricts access to specific users or groups. Combined with Nextcloud's "Files access control" app, you can apply granular rules.

**Q: What happens if the S3 AP is detached or the volume is unmounted?**
A: Nextcloud shows an error when accessing the external storage folder. Other Nextcloud functionality is unaffected. Re-attaching the AP restores access.

**Q: Can I use multiple S3 APs (different volumes) in one Nextcloud instance?**
A: Yes. Add multiple External Storage entries, each pointing to a different S3 AP alias. They appear as separate folders in Nextcloud.

**Q: Is there a file size limit for uploads through Nextcloud?**
A: FSx for ONTAP S3 AP supports PutObject up to 5 GB and multipart upload for larger files. Nextcloud's PHP upload limit (`upload_max_filesize`, `post_max_size`) may also apply — adjust in `php.ini` as needed.

---

## Related Documents

- [File Portal UI Options (Amplify Gen2 / Nextcloud / Custom)](./file-portal-amplify-gen2.en.md) — Architecture comparison and selection guide
- [S3AP Compatibility Notes](./s3ap-compatibility-notes.en.md) — Known S3 AP constraints including Presigned URL limitation
- [AD-Joined SVM S3 AP Prerequisites](./en/ad-joined-svm-s3ap-prerequisites.md) — AD DC reachability requirements
- [S3AP Performance Considerations](./s3ap-performance-considerations.en.md) — Throughput design guidance
- [Comparison Alternatives](./comparison-alternatives.md) — S3 AP vs EFS vs NFS vs DataSync
- [AWS Blog: Scale your Nextcloud with Storage on Amazon S3](https://aws.amazon.com/blogs/opensource/scale-your-nextcloud-with-storage-on-amazon-simple-storage-service-amazon-s3/) — Reference architecture for Nextcloud + S3
- [Nextcloud Admin Manual: Amazon S3 External Storage](https://docs.nextcloud.com/server/stable/admin_manual/configuration_files/external_storage/amazons3.html) — Official Nextcloud S3 configuration docs

---

*Last updated: 2025-07 | Applies to: Nextcloud 25+ / FSx for ONTAP S3 AP (ONTAP 9.14.1+)*
