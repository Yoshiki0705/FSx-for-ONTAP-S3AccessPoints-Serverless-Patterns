# AD-Joined SVM: S3 Access Point Prerequisites

> Prerequisites and operational guidance for using FSx for ONTAP S3 Access Points on AD-joined SVMs (CIFS enabled).

## Executive Summary

AD-joined SVMs require Active Directory Domain Controller (AD DC) connectivity for **all** S3 Access Point data operations. Without it, ListObjectsV2, GetObject, and PutObject fail with `AccessDenied` — even though HeadBucket succeeds. This document explains the prerequisites, recommended architecture patterns, and troubleshooting steps.

---

## Table of Contents

1. [AD DC Reachability Requirement](#ad-dc-reachability-requirement)
2. [Internet-Origin AP + VPC-External Lambda Pattern](#internet-origin-ap--vpc-external-lambda-pattern)
3. [Same-Account AP Resource Policy](#same-account-ap-resource-policy)
4. [Pre-Flight Health Check](#pre-flight-health-check)
5. [Troubleshooting](#troubleshooting)
6. [FAQ](#faq)
7. [Related Documents](#related-documents)

---

## AD DC Reachability Requirement

### Why AD DC Is Required

On AD-joined SVMs (CIFS enabled), ONTAP's multiprotocol identity pipeline performs a `unix→win` reverse name-mapping lookup on **every** S3 AP data operation. This lookup requires the SVM to contact its AD Domain Controllers via LDAP/Kerberos.

This applies even for:
- UNIX security style volumes
- S3 AP with UNIX FileSystemUserType
- Volumes with no SMB shares configured

The only condition is that CIFS is **enabled** on the SVM.

### Diagnostic Pattern

| Operation | AD DC Reachable | AD DC Unreachable |
|-----------|:---:|:---:|
| HeadBucket | ✅ | ✅ (false positive) |
| ListObjectsV2 | ✅ | ❌ AccessDenied |
| GetObject | ✅ | ❌ AccessDenied |
| PutObject | ✅ | ❌ AccessDenied |

> **Security note**: HeadBucket validates only at the S3 metadata layer (AP existence and IAM). It does NOT traverse the ONTAP file-system layer. This makes it an unreliable health check for S3 AP data-plane readiness on AD-joined SVMs.

### Required Network Connectivity

SVM ENIs must reach AD DC IPs on these ports:

| Port | Protocol | Service |
|------|----------|---------|
| 53 | TCP/UDP | DNS |
| 88 | TCP/UDP | Kerberos |
| 389 | TCP/UDP | LDAP |
| 445 | TCP | SMB/CIFS |
| 636 | TCP | LDAPS |

Ensure Security Groups on the FSx for ONTAP preferred/standby subnets allow outbound traffic to AD DC IPs on these ports.

---

## Internet-Origin AP + VPC-External Lambda Pattern

### When to Use

For S3 AP **data access** (ListObjectsV2, GetObject, PutObject) from Lambda, use:

- **Internet-origin AP** (`NetworkOrigin: Internet`, no `VpcConfiguration`)
- **VPC-external Lambda** (no `VpcConfig` on the Lambda function)

### Why Not VPC-Origin?

VPC-origin APs require an S3 Gateway or Interface VPC Endpoint. However:

1. S3 **Gateway** VPC Endpoints do NOT support S3 Access Points with Internet-origin
2. S3 **Interface** VPC Endpoints add cost (~$7.20/month per AZ) and complexity
3. A Lambda inside a VPC cannot reach Internet-origin S3 APs without a NAT Gateway

The simplest and most cost-effective pattern is a VPC-external Lambda calling an Internet-origin S3 AP directly.

### Architecture

```
┌─────────────────────┐       ┌──────────────────┐       ┌─────────────────────┐
│ Lambda (no VPC)     │──────▶│ S3 AP (Internet) │──────▶│ FSx for ONTAP Vol   │
│ IAM: s3:GetObject   │       │ NetworkOrigin:   │       │ (ONTAP file-system   │
│      s3:ListBucket  │       │   Internet       │       │  layer auth)         │
└─────────────────────┘       └──────────────────┘       └─────────────────────┘
```

### VPC Split Architecture

If you also need ONTAP REST API access (management LIF is VPC-internal):

| Lambda | Access | VpcConfig |
|--------|--------|-----------|
| Discovery/ONTAP-mgmt Lambda | ONTAP REST API (`/api/...`) | ✅ VPC subnets + SG |
| S3 AP data Lambda | S3 AP (ListObjectsV2/GetObject/PutObject) | ❌ No VPC |

> **Cost note**: Never mix ONTAP management API and Internet-origin S3 AP access in a single Lambda. A VPC-Lambda cannot reach Internet-origin S3 APs without a NAT Gateway ($32+/month).

---

## Same-Account AP Resource Policy

### Key Finding

For **same-account** access (the calling IAM principal and the S3 Access Point are in the same AWS account), an explicit S3 Access Point resource policy (`put_access_point_policy`) is **not required**.

The IAM identity policy alone is sufficient:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:ListBucket",
    "s3:GetObject",
    "s3:PutObject"
  ],
  "Resource": [
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-access-point",
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-access-point/object/*"
  ]
}
```

### When AP Resource Policy IS Required

- **Cross-account access** — caller IAM principal is in a different AWS account
- **Condition key restrictions** — `aws:PrincipalAccount`, `s3:DataAccessPointAccount`, etc.
- **Restricting beyond IAM** — deny specific principals even if IAM allows

### CloudFormation Example (Same-Account, No AP Policy Needed)

```yaml
S3ApDataReaderRole:
  Type: AWS::IAM::Role
  Properties:
    Policies:
      - PolicyName: S3ApAccess
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - s3:ListBucket
                - s3:GetObject
              Resource:
                - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3ApName}"
                - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3ApName}/object/*"
```

---

## Pre-Flight Health Check

### Programmatic Check (Python — for Lambda/Step Functions)

```python
from shared.ad_health_check import require_ad_dc_reachability
from shared.ontap_client import OntapClient, OntapClientConfig

# Initialize ONTAP client
config = OntapClientConfig(management_ip="10.0.1.100", secret_name="fsxn/admin")
client = OntapClient(config)

# Raises AdDcUnreachableError if AD DC is unreachable
status = require_ad_dc_reachability(client, svm_name="svm1")
# status.is_ad_joined, status.dc_reachable, status.discovered_servers
```

### Shell Check (for scripts/automation)

```bash
# Check AD DC discovery from ONTAP REST API
curl -sku "$USER:$PASS" \
  "https://$MGMT_IP/api/protocols/cifs/domains?svm.name=$SVM&fields=discovered_servers" \
  | jq '.records[0].discovered_servers | length'
# Result: 0 = AD DC unreachable, >0 = healthy
```

### Step Functions Integration

Add the AD DC check as the **first state** in any workflow that uses S3 AP data operations on an AD-joined SVM:

```json
{
  "StartAt": "AdDcHealthCheck",
  "States": {
    "AdDcHealthCheck": {
      "Type": "Task",
      "Resource": "${AdDcHealthCheckFunctionArn}",
      "Next": "MainWorkflow",
      "Retry": [{"ErrorEquals": ["States.TaskFailed"], "MaxAttempts": 2, "IntervalSeconds": 30}],
      "Catch": [{"ErrorEquals": ["AdDcUnreachableError"], "Next": "NotifyAdFailure"}]
    }
  }
}
```

---

## Troubleshooting

### Symptom: AccessDenied on ListObjectsV2 but HeadBucket Succeeds

**Root Cause**: AD DC is unreachable from the SVM.

**Verification**:
```bash
curl -sku user:pass \
  "https://<mgmt-ip>/api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers"
```

If `discovered_servers` is `[]` (empty array), the AD DC is unreachable.

**Resolution**:
1. Verify SVM DNS IPs point to active AD DC addresses
2. Check Security Groups allow ports 53/88/389/445/636 from SVM ENI subnets
3. If using AWS Managed AD, confirm the directory status is `Active`
4. If AD was recreated, the SVM may need CIFS force-delete + re-join (new NetBIOS name required)

### Symptom: S3 AP Create Fails for WINDOWS Type

**Root Cause**: SVM is not yet AD-joined.

**Resolution**: Run `scripts/demo-ad-join-svm.sh --stack-name <stack>` first.

### Symptom: AccessDenied Despite Correct IAM Policy

**Checklist**:
1. IAM ARN uses S3 AP format: `arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*`
2. `WindowsUser.Name` is username only (no `DOMAIN\` prefix)
3. AD DC is reachable (see above)
4. File-system identity has appropriate NTFS/UNIX permissions on the target path

---

## FAQ

### Q: Do pure UNIX SVMs (no CIFS) need AD DC?

No. If the SVM has no CIFS service enabled, S3 AP operations do not require AD. The `unix→win` reverse lookup only occurs when CIFS is configured.

### Q: Can I use HeadBucket as a health check?

No. HeadBucket validates only S3-layer metadata. It always succeeds regardless of AD DC status. Use ListObjectsV2 with `MaxKeys=1` as a data-plane health check, or the ONTAP API `/protocols/cifs/domains?fields=discovered_servers`.

### Q: Is `put_access_point_policy` required for same-account access?

No. For same-account access, the IAM identity policy on the calling role is sufficient. An explicit AP resource policy is only needed for cross-account access or condition-key restrictions.

### Q: Why does Internet-origin S3 AP not work from a VPC Lambda?

A VPC Lambda's traffic routes through VPC networking. Internet-origin S3 AP traffic does NOT go through S3 Gateway VPC Endpoints. The Lambda needs either a NAT Gateway (costly) or should be configured without VpcConfig (VPC-external).

### Q: What happens if AD DC becomes unreachable mid-workflow?

S3 AP data operations fail immediately with AccessDenied. Step Functions workflows should include Retry with backoff (AD DC may be temporarily unavailable) and Catch for `AdDcUnreachableError` to alert operators.

---

## Related Documents

- [ONTAP Integration Notes](../ontap-integration-notes.en.md) — NAS coexistence, identity mapping
- [S3AP Compatibility Notes](../s3ap-compatibility-notes.en.md) — Known constraints
- [S3AP Authorization Model](../s3ap-authorization-model.en.md) — Dual-layer auth
- [Incident Response Playbook](../incident-response-playbook.md) — Security incident handling
- [ROADMAP](../../ROADMAP.md) — SnapMirror DR test automation (future)
- Global Steering: `~/.kiro/steering/global-fsx-ontap-ad-integration.md` — Full verified patterns
