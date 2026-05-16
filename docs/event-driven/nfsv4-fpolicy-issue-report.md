# NFSv4.2 FPolicy External Server Mode — Event Notification Not Sent

**Date**: 2026-05-14
**Environment**: Amazon FSx for NetApp ONTAP (ONTAP 9.17.1P6)
**Status**: Resolved — Expected behavior (NFSv4.2 not supported by FPolicy)

---

## Summary

When using FPolicy external engine in asynchronous mode on FSx for NetApp ONTAP 9.17.1,
NOTI_REQ (file event notifications) are **not sent** for NFSv4.2 client access.

The root cause is that `mount -o vers=4` on Linux clients negotiates to NFSv4.2,
which is not supported by ONTAP FPolicy monitoring.

NFSv3, NFSv4.0, and NFSv4.1 all work correctly with the same policy, volume,
and FPolicy server configuration.

This is **expected behavior** per ONTAP documentation.

---

## Root Cause

**`mount -o vers=4` causes Linux clients to negotiate NFSv4.2.**

ONTAP FPolicy supports the following protocols:
- SMB (CIFS) ✅
- NFSv3 ✅
- NFSv4.0 ✅
- NFSv4.1 ✅ (ONTAP 9.15.1+)
- **NFSv4.2 ❌ Not supported**

References:
- [NetApp KB: FPolicy supported protocols](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing)
- [ONTAP NFS Management: FPolicy monitoring of NFSv4.2 not supported](https://docs.netapp.com/us-en/ontap/nfs-admin/index.html)

---

## Verification Results

| NFS Version | Mount Option | Actual vers | FPolicy NOTI_REQ | Result |
|---|---|---|---|---|
| NFSv3 | `vers=3` | 3 | ✅ Received immediately | Works |
| NFSv4.0 | `vers=4.0` | 4.0 | ✅ Received immediately | **Works** |
| NFSv4.1 | `vers=4.1` | 4.1 | ✅ Received immediately | **Works** |
| NFSv4.2 | `vers=4.2` | 4.2 | ❌ Not sent | **Not supported (expected)** |
| NFSv4 (auto) | `vers=4` | 4.2 | ❌ Not sent | Negotiates to 4.2 |
| SMB | — | — | ✅ Received immediately | Works |

---

## Recommended Configuration

### NFS Mount Options When Using FPolicy

```bash
# Recommended: Explicitly pin to NFSv4.1
sudo mount -t nfs -o vers=4.1 <SVM_NFS_LIF_IP>:/<volume_path> /mnt/fsxn

# Alternative: NFSv3
sudo mount -t nfs -o vers=3 <SVM_NFS_LIF_IP>:/<volume_path> /mnt/fsxn

# DO NOT USE: vers=4 may negotiate to NFSv4.2
# sudo mount -t nfs -o vers=4 <SVM_NFS_LIF_IP>:/<path> /mnt/fsxn
```

### Disable NFSv4.2 on the SVM (Optional)

ONTAP documentation recommends disabling NFSv4.2 when configuring FPolicy monitoring.

```bash
# ONTAP CLI
vserver nfs modify -vserver <SVM_NAME> -v4.2 disabled

# ONTAP REST API
curl -sk -u fsxadmin:<PASSWORD> -X PATCH \
  'https://<ONTAP_MGMT_IP>/api/protocols/nfs/services/<SVM_UUID>' \
  -H 'Content-Type: application/json' \
  -d '{"protocol":{"v42_enabled":false}}'
```

---

## FPolicy Event Configuration for Multiple Protocols

FPolicy events must be created per protocol. To support both SMB and NFS:

```bash
# Note: ONTAP 9.11+ では `vserver` プレフィックスは非推奨（後方互換性あり）

# CIFS (SMB) events
fpolicy policy event create \
  -vserver <SVM_NAME> -event-name fpolicy_cifs_events \
  -protocol cifs -file-operations create,write,delete,rename

# NFSv3 events
fpolicy policy event create \
  -vserver <SVM_NAME> -event-name fpolicy_nfsv3_events \
  -protocol nfsv3 -file-operations create,write,delete,rename

# NFSv4 events (covers NFSv4.0 and NFSv4.1)
fpolicy policy event create \
  -vserver <SVM_NAME> -event-name fpolicy_nfsv4_events \
  -protocol nfsv4 -file-operations create,write,delete,rename
```

> **Note**: Do NOT include `open` or `close` in `-file-operations` for NFSv4.
> These operations can cause NFS hangs even in asynchronous mode with `mandatory=false`.

---

## Key Findings from E2E Testing

### 1. NLB Incompatibility with FPolicy Protocol

ONTAP FPolicy uses a binary framing protocol (`"` + 4-byte big-endian length + `"` + payload).
Network Load Balancers (NLB) cannot correctly relay this framing after TCP connection establishment.

**Solution**: Use the Fargate task's direct Private IP as the FPolicy external engine primary server.
NLB is used only for health checks and service discovery.

### 2. Timeout Configuration

The FPolicy server's socket timeout must be **greater than** ONTAP's `keep_alive_interval` (default: 120 seconds).
Set `conn.settimeout(300)` or higher to avoid premature disconnection.

### 3. NFSv4 open/close Event Hang

Setting `open: true` or `close: true` in FPolicy events for NFSv4 can cause NFS operations to hang,
even with `mandatory: false` and asynchronous mode. Only use `create`, `write`, `delete`, `rename`.

### 4. VPC Endpoints Required for Fargate

ECS Fargate in Private Subnets requires the following VPC Endpoints for FPolicy Server operation:

| Endpoint | Type | Purpose |
|----------|------|---------|
| `com.amazonaws.<region>.ecr.dkr` | Interface | Container image pull |
| `com.amazonaws.<region>.ecr.api` | Interface | ECR auth token |
| `com.amazonaws.<region>.s3` | Gateway | ECR image layers |
| `com.amazonaws.<region>.logs` | Interface | CloudWatch Logs |
| `com.amazonaws.<region>.sts` | Interface | IAM role authentication |
| `com.amazonaws.<region>.sqs` | Interface | SQS message sending |

---

## Timeline

1. Initial test: `mount -o vers=4` → Negotiated to NFSv4.2 → No NOTI_REQ → Misidentified as "NFSv4 doesn't work"
2. Feedback from NetApp SME: Pointed out NFSv4.2 non-support possibility
3. Re-verification: Explicitly pinned `vers=4.1` and `vers=4.0` → **Both work correctly**
4. Conclusion: Expected behavior due to NFSv4.2 non-support. Documented as guidance for users.

---

## References

- [NetApp KB: FPolicy Auditing FAQ](https://kb.netapp.com/onprem/ontap/da/NAS/FAQ:_FPolicy:_Auditing)
- [ONTAP NFS Management](https://docs.netapp.com/us-en/ontap/nfs-admin/index.html)
- [FPolicy event configuration](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-event-task.html)
- [vserver fpolicy policy event create (CLI Reference)](https://docs.netapp.com/us-en/ontap-cli-991/vserver-fpolicy-policy-event-create.html)
- [FPolicy External Server communication](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-external-fpolicy-servers-concept.html)
- [Persistent Store (ONTAP 9.14.1+)](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)

---

## Related Documents

- [FPolicy Setup Guide](../guides/fpolicy-setup-guide.md)
- [FPolicy Configuration Reference](fpolicy-configuration-reference.md)
- [FPolicy Server Deployment Architecture](fpolicy-server-deployment-architecture.md)
- [Event-Driven Architecture Design](architecture-design.md)
