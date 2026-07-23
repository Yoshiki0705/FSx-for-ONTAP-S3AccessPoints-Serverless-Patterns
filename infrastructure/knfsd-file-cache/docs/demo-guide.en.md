# KNFSD File Cache Demo Guide — FSx for ONTAP NFS Read Acceleration

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md)

> **Verified**: 2026-07-23, ap-northeast-1, arm64 (Graviton), FSx for ONTAP 9.17.1
> **Measured**: Cache miss 55ms → Cache hit 2ms (**28x speedup**), proxy cache 422 MB/s

---

## Prerequisites

### Required Tools

| Tool | Version | Install | Check |
|------|---------|---------|-------|
| AWS CLI | >= 2.x | `brew install awscli` | `aws --version` |
| Terraform | >= 1.5 | `brew install hashicorp/tap/terraform` | `terraform version` |
| Packer | >= 1.9 | `brew install hashicorp/tap/packer` | `packer version` |
| jq | any | `brew install jq` | `jq --version` |
| Git | any | (pre-installed) | `git --version` |

### Required AWS Resources (must exist beforehand)

| Resource | Check Command | Example |
|----------|--------------|---------|
| FSx for ONTAP (AVAILABLE) | `aws fsx describe-file-systems --query 'FileSystems[?FileSystemType==\`ONTAP\`].{Id:FileSystemId,State:Lifecycle}'` | `fs-0123...` |
| SVM (NFS LIF IP) | `aws fsx describe-storage-virtual-machines --query 'StorageVirtualMachines[].{Name:Name,NFS:Endpoints.Nfs.IpAddresses[0]}'` | `10.0.1.50` |
| Volume (junction path) | `aws fsx describe-volumes --query 'Volumes[].{Name:Name,Path:OntapConfiguration.JunctionPath}'` | `/vol1` |
| VPC + Subnet | `aws ec2 describe-subnets --query 'Subnets[].{Id:SubnetId,AZ:AvailabilityZone}'` | `subnet-0abc...` |

### Network Requirements

```
┌─────────────────────────────────────────────────────┐
│ VPC                                                 │
│                                                     │
│  ┌── Subnet (same AZ as FSx for ONTAP) ─────────┐  │
│  │                                               │  │
│  │  FSx for ONTAP ◄──NFS──► KNFSD Proxy         │  │
│  │  (10.0.1.50)              (Public IP needed)  │  │
│  │                              ▲                │  │
│  │                              │ NFS            │  │
│  │                              ▼                │  │
│  │                           Compute Clients     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Internet Gateway ← KNFSD needs EC2 API access      │
└─────────────────────────────────────────────────────┘
```

> **Important**: KNFSD proxy requires a Public IP (or NAT/EC2 VPC Endpoint).
> `proxy-startup.sh` accesses EC2 API (`ec2.{region}.amazonaws.com`) for status tags.
>
> **Security note**: NFS ports are NOT exposed to the internet even with a Public IP.
> The Security Group restricts NFS access to VPC CIDR only.

### FSx for ONTAP Export-Policy Check

KNFSD needs NFS mount access to FSx for ONTAP. The default export-policy allows all IPs (0.0.0.0/0). No additional configuration needed unless you've customized the export-policy.

---

## Deployment (Total: ~40 min)

### Step 1: Clone KNFSD Repository (2 min)

```bash
git clone https://github.com/awslabs/knfsd-file-cache.git /tmp/knfsd-file-cache
```

### Step 2: Build AMI (~25 min)

```bash
cd /tmp/knfsd-file-cache/image
packer init .
packer build \
  -var 'REGION=ap-northeast-1' \
  -var 'SUBNET=subnet-0123456789abcdef0' \
  -var 'ARCH=["arm64"]' \
  -var 'ASSOCIATE_PUBLIC_IP_ADDRESS=true' \
  .
```

**Note the output AMI ID**: `ami-0xxxxxxxxxxxxxxxxx`

> - `ASSOCIATE_PUBLIC_IP_ADDRESS=true` required for subnets with `MapPublicIpOnLaunch=false`
> - Build uses Spot instance (~$0.30)
> - arm64 (Graviton) recommended for cost efficiency
> - AMI can be reused for multiple deployments

### Step 3: Configure Terraform (3 min)

```bash
cd /path/to/infrastructure/knfsd-file-cache/terraform
cp terraform.tfvars.example terraform.tfvars
```

**Edit `terraform.tfvars`** — minimum changes:

```hcl
vpc_id       = "vpc-0abc..."
subnet_ids   = ["subnet-0def..."]
knfsd_ami_id = "ami-0xxx..."

source_mounts = [
  {
    host   = "10.0.1.50"   # SVM NFS LIF IP
    export = "/vol1"
    mount  = "/vol1"
  }
]
```

### Step 4: Deploy (~3 min)

```bash
terraform init
terraform plan
terraform apply   # type "yes"
```

### Step 5: Verify (~2 min)

```bash
./scripts/validate.sh
```

### Step 6: Mount from Client

```bash
# From any EC2 in the same VPC (NFSv4.1 REQUIRED for FSx for ONTAP source)
sudo mkdir -p /mnt/knfsd
sudo mount -t nfs -o vers=4.1 <KNFSD_IP>:/vol1 /mnt/knfsd
ls /mnt/knfsd/
```

> **Critical**: Use `vers=4.1` (not `vers=3`). NFSv3 causes Stale file handle on file creation due to filehandle size overflow. See [Issue #40](https://github.com/awslabs/knfsd-file-cache/issues/40).

### Step 7: Cache Test

```bash
# Create 10 MB test file
dd if=/dev/urandom of=/mnt/knfsd/cache_test.dat bs=1M count=10; sync

# Cache MISS (1st read — fetched from FSx for ONTAP)
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
time cat /mnt/knfsd/cache_test.dat > /dev/null   # ~55-64ms

# Cache HIT (2nd read — served from KNFSD cache)
time cat /mnt/knfsd/cache_test.dat > /dev/null   # ~2ms (32x faster)

rm /mnt/knfsd/cache_test.dat
sudo umount /mnt/knfsd
```

---

## Cleanup

```bash
cd infrastructure/knfsd-file-cache/terraform
terraform destroy   # type "yes" — removes all KNFSD resources

# Optionally deregister AMI (if you don't plan to redeploy)
AMI_ID="ami-0xxx..."
SNAP_ID=$(aws ec2 describe-images --image-ids $AMI_ID --query 'Images[0].BlockDeviceMappings[0].Ebs.SnapshotId' --output text --region ap-northeast-1)
aws ec2 deregister-image --image-id $AMI_ID --region ap-northeast-1
aws ec2 delete-snapshot --snapshot-id $SNAP_ID --region ap-northeast-1
```

---

## Optional: Dual-Path Test (S3 AP + KNFSD)

If you have an S3 Access Point on the same FSx for ONTAP volume, test bidirectional data flow:

```bash
# 1. Write via S3 AP
echo "dual-path-test-$(date +%s)" > /tmp/s3ap-test.txt
aws s3 cp /tmp/s3ap-test.txt "s3://arn:aws:s3:ap-northeast-1:$(aws sts get-caller-identity --query Account --output text):accesspoint/YOUR-AP-NAME/dual-path-test.txt"

# 2. Read via KNFSD NFS (should be immediate)
cat /mnt/knfsd/dual-path-test.txt
# → Should show same content ✅

# 3. Write via NFS, read via S3 AP
echo "nfs-write-$(date +%s)" > /mnt/knfsd/nfs-roundtrip.txt
aws s3 cp "s3://arn:aws:s3:ap-northeast-1:ACCOUNT:accesspoint/YOUR-AP-NAME/nfs-roundtrip.txt" -
# → Should show same content ✅
```

> Create S3 AP: `aws fsx create-and-attach-s3-access-point --name my-ap --type ONTAP --ontap-configuration '{"VolumeId":"fsvol-xxx","FileSystemIdentity":{"Type":"UNIX","UnixUser":{"Name":"root"}}}'`

---

## Lessons Learned (from 2026-07-22~23 Verification)

### Critical

| Finding | Impact | Action |
|---------|--------|--------|
| **NFSv4.1 required** for FSx for ONTAP | NFSv3 write = Stale file handle | Set `nfs_version = "4.1"` |
| **Public IP or NAT required** | proxy-startup.sh fails silently | `assign_public_ip = true` |
| **IAM needs path-level ARN** | GetParametersByPath denied | Include ARN with and without `/*` |
| **`FSID_MODE=static` is broken** | All writes fail | Use `local` or `external` |

### Performance

| Finding | Numbers |
|---------|---------|
| KNFSD L1 (RAM) cache | 5.0-9.1 GB/s |
| KNFSD proxy → client (L1 serve) | 422-619 MB/s |
| FS-Cache L2 (NVMe) after reboot | 106 MB/s (5.6x faster than source) |
| Source FSx for ONTAP NFS fetch | 18-19 MB/s |
| nconnect=16 on small instances | Counterproductive (619 → 184 MB/s) |
| S3 AP batch 50 files → NFS read | 107ms (2.1ms/file) |
| Multipart upload → NFS read | MD5 verified, immediate |

### Operations

| Finding | Detail |
|---------|--------|
| Proxy restart: client unaffected | NFSv4.1 grace period handles recovery |
| FS-Cache survives reboot | NVMe data preserved, `CaRdOps` active post-boot |
| SQLite on FSx for ONTAP persists | No FSID loss across restarts |
| `CACHEFILESD_DISK_TYPE` | Must be `local-nvme` (hyphen), not `local_nvme` |

---

## Cost Estimate

| Phase | Resource | Cost |
|-------|----------|------|
| AMI build | Spot c6g.16xlarge × 25min | ~$0.30 |
| Test (1hr) | m6gd.xlarge | ~$0.29 |
| **Total** | | **< $1 (KNFSD incremental only)** |

> **Prerequisite costs**: The above assumes an existing FSx for ONTAP environment (~$194/month) + VPC is already running. Building a verification environment from scratch requires FSx for ONTAP minimum configuration (128 MBps / 1 TB SSD) at ~$194/month additionally.
| Production (monthly) | im4gn.16xlarge × 24/7 | ~$4,190 |

---

## When to Choose KNFSD

| Current Situation | What KNFSD Solves |
|-------------------|-------------------|
| Approaching FSx for ONTAP throughput limits | Cache multiplies effective bandwidth |
| Many nodes read the same files repeatedly | 2nd+ reads served from NVMe (zero FSx bandwidth) |
| Want to use Spot for HPC burst | Spot reclamation doesn't affect warm cache |
| Using both on-premises NFS and FSx for ONTAP | Unified cache layer across multiple sources |
| Need read optimization without FlexCache write-back | Read-only caching without ONTAP capacity consumption |

For a detailed comparison with FlexCache / Amazon File Cache / EFS, see the [Comparison Document](../../../docs/comparison-alternatives.md).

---

## FAQ

**Q: Does KNFSD duplicate data from FSx for ONTAP?**
A: No. KNFSD is a transparent NFS protocol-level cache. The single source of truth remains on FSx for ONTAP. KNFSD only accelerates reads.

**Q: Can I write through KNFSD?**
A: Yes. Writes are forwarded immediately to the source (write-through). However, write data is not cached. KNFSD is optimized for read-heavy workloads.

**Q: Can I use multiple KNFSD proxies?**
A: Yes. Set `cluster_size=2+` and use DNS round-robin or NLB for load balancing. 2+ proxies recommended for production availability.

**Q: What happens if KNFSD goes down?**
A: NFS mounts hang (with `hard` mount option). They auto-recover when the proxy returns. For availability, use 2+ proxies.

**Q: How do I roll back if KNFSD doesn't work?**
A: Point clients back to FSx for ONTAP's NFS LIF IP directly. Data is always on FSx for ONTAP — removing KNFSD loses nothing. `terraform destroy` removes all resources.

**Q: How do I auto-mount on render farm nodes?**
A: Add to `/etc/fstab` in your golden AMI:
```
<KNFSD_IP>:/vol1  /mnt/assets  nfs  vers=4.1,hard,bg  0  0
```
The `bg` option prevents boot from blocking if KNFSD isn't ready yet.

**Q: Should KNFSD proxies use Spot instances?**
A: No. Keep proxies On-Demand to preserve the warm cache. Use Spot for compute clients that mount from KNFSD — if Spot reclaims a client, the cache stays warm for the replacement.

---

## NFS Re-export Limitations (Linux Kernel 7.1)

Based on [official kernel documentation](https://docs.kernel.org/7.1/filesystems/nfs/reexport.html):

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| File locks not supported | Advisory locks fail with "operation not supported" | Use application-level locking or avoid concurrent writers |
| Delegations not available | No NFSv4 delegations from re-export server | Not an issue for NFSv3 (no delegations) |
| Filehandle size +22 bytes | Limits re-export depth (no cascading proxies) | Single proxy tier is sufficient |
| Stale handles on proxy restart | All clients must remount | Use rolling updates for proxy maintenance |
| crossmnt doesn't propagate fsid | Sub-mounts need explicit export + unique fsid | KNFSD's proxy-startup.sh handles this |

---

## Related Documentation

- [KNFSD + S3 AP Dual-Path Architecture](../../../docs/knfsd-s3ap-dual-path-architecture.md)
- [Comparison: FlexCache / KNFSD / Amazon File Cache](../../../docs/comparison-alternatives.md)
- [Troubleshooting](troubleshooting.md)
- [KNFSD File Cache Official Repository](https://github.com/awslabs/knfsd-file-cache)
- [AWS Solutions Guidance](https://docs.aws.amazon.com/solutions/knfsd-file-cache-on-aws/)
