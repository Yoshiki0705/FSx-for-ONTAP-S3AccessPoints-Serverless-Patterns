# KNFSD File Cache — Troubleshooting

🌐 **Language / 言語**: [日本語](troubleshooting.md) | [English](troubleshooting.en.md)

> All issues below were encountered during real testing in ap-northeast-1 + FSx for ONTAP + arm64 (2026-07-22).

---

## Deployment Issues

### proxy-startup.sh fails with "Connect timeout on endpoint URL"

| Cause | KNFSD instance cannot reach EC2 API |
|-------|------|
| Fix | Assign Public IP (`assign_public_ip = true`), add NAT Gateway, or add EC2 VPC Interface Endpoint |

### "Detected 0 devices: ERROR: No storage devices found"

| Cause | `CACHEFILESD_DISK_TYPE` SSM param is missing or wrong value |
|-------|------|
| Fix | Set `CACHEFILESD_DISK_TYPE = "local-nvme"` (with **hyphen**, not underscore) |

Valid values: `local-nvme` (instance store NVMe) or `ebs` (attached EBS volumes)

### "mount.nfs: an incorrect mount option was specified"

| Cause | SSM parameters for NFS mount options have empty values |
|-------|------|
| Fix | Ensure `NCONNECT`, `ACDIRMIN/MAX`, `ACREGMIN/MAX`, `RSIZE`, `WSIZE` have numeric values. Terraform creates these automatically. |

### Packer build SSH timeout

| Cause | Subnet has `MapPublicIpOnLaunch=false` |
|-------|------|
| Fix | Add `-var 'ASSOCIATE_PUBLIC_IP_ADDRESS=true'` to packer build command |

---

## NFS Mount Issues

### "No such file or directory" when client mounts

| Cause | `knfsd-fsidd` not running (FSID daemon required for NFS re-export) |
|-------|------|
| Fix | Let `proxy-startup.sh` complete fully. Check: `systemctl status knfsd-fsidd` |

### "access denied by server"

| Possible Cause | Fix |
|----------------|-----|
| Missing UDP SG rules | Add UDP 111, 2049, 20048 to Security Group |
| Export CIDR mismatch | Check `EXPORT_CIDR` SSM parameter matches client subnet |
| `secure` option blocking | Terraform sets `insecure` by default |

Required ports (TCP **and** UDP): 111 (portmapper), 2049 (NFS), 20048 (mountd)

### "Stale file handle"

| Cause | KNFSD proxy NFS server was restarted, invalidating file handles |
|-------|------|
| Fix | `sudo umount -l /mnt/knfsd && sudo mount -t nfs -o vers=3 <IP>:/vol1 /mnt/knfsd` |

> Stale handles do NOT occur during normal operation. Only when proxy is reconfigured/restarted.

---

## Cache Issues

### No speedup on repeated reads

Check in order:
1. Instance type has NVMe? (`lsblk | grep nvme`)
2. NVMe mounted at `/var/cache/fscache`? (`mount | grep fscache`)
3. Source mount has `fsc` option? (`mount | grep fsc`)
4. Client page cache dropped before test? (`echo 3 > /proc/sys/vm/drop_caches`)

> Even without FS-Cache (L2 NVMe), **L1 Page Cache (RAM) provides 32x speedup** for files that fit in memory.

### FS-Cache stats all zeros

| Cause | Source NFS mount missing `fsc` option |
|-------|------|
| Fix | `proxy-startup.sh` adds `fsc` automatically. For manual mount: `mount -o vers=3,fsc ...` |

---

## Dual-Path (KNFSD + S3 AP)

### S3 AP-written files not visible via KNFSD

| Cause | NFS attribute cache delay (acregmax, default 60s) |
|-------|------|
| Fix | Set `acregmax = 10` in terraform.tfvars for faster S3 AP → NFS visibility |

### KNFSD-written files not visible via S3 AP

| Cause | Write-through sync timing |
|-------|------|
| Fix | Run `sync` after NFS write, wait 2-3 seconds, then S3 AP GetObject |

---

## Performance Tuning

| Bottleneck | Check | Fix |
|-----------|-------|-----|
| FSx throughput saturated | CloudWatch `DataReadBytes` | Increase throughput capacity or improve cache hit ratio |
| NFS thread exhaustion | `cat /proc/fs/nfsd/threads` | Increase `nfs_threads` (64-128 for production) |
| Client network bandwidth | Instance type | Use higher-bandwidth compute instances |

---

## Known Limitations (Preview)

| Item | Details |
|------|---------|
| SLA | No SLA during Preview |
| File locks | Not supported on re-exported NFS (kernel limitation) |
| NVMe encryption | Hardware-level only. Instance termination triggers wipe |
| Stale handles | Proxy restart requires all clients to remount |
| NFS version | v3 recommended. v4.x works but less tested for re-export |

---

## NFS Version Selection

| Aspect | NFSv3 | NFSv4.1 |
|--------|-------|---------|
| Re-export stability | ✅ Mature | △ Edge cases |
| File locking | statd/lockd (separate daemon) | Built-in |
| Ports needed | 111 + 2049 + 20048 (TCP+UDP) | 2049 only (TCP) |
| Encryption | None | krb5p (Kerberos) available |

**Recommendation**: Use NFSv3 for KNFSD re-export. For environments requiring encryption, deploy within VPC only and consider NFSv4.1 + krb5p.
