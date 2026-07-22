# KNFSD File Cache — FSID Backend Selection Guide

🌐 **Language / 言語**: [日本語](fsid-backend-options.md) | [English](fsid-backend-options.en.md)

## Background

When KNFSD performs NFS re-export, each export path requires a unique FSID (File System Identifier). Incorrect or unstable FSIDs cause `Stale file handle` errors on clients.

There are 4 FSID management options. This project assumes FSx for ONTAP as the source, so we leverage FSx for ONTAP's built-in high availability for FSID persistence.

---

## Comparison

| Option | FSID Manager | Backend | Monthly Cost | HA/Persistence | Multi-Node | Use Case |
|:---:|------|------|:---:|:---:|:---:|------|
| **A** | knfsd-fsidd (Go) | RDS PostgreSQL (db.t4g.micro) | ~$15 | ✅ RDS Multi-AZ | ✅ | Production multi-node |
| **B** | knfsd-fsidd (Go) | Aurora Serverless v2 (0.5 ACU) | ~$5-15 | ✅ Aurora HA | ✅ | Cost-optimized production |
| **C** | Official Terraform module | RDS (built-in) | ~$15 | ✅ | ✅ | Fully managed (recommended if path issue resolved) |
| **D** | kernel fsidd | SQLite on FSx for ONTAP (NFS) | **$0** | ✅ FSx for ONTAP HA | △ Single-node | Test/PoC/Single-node production |

---

## Option D: SQLite on FSx for ONTAP (Recommended for this project)

```
KNFSD Proxy → kernel fsidd → SQLite on /srv/nfs/vol1/.knfsd/fsids.sqlite
                                            ↑
                                    FSx for ONTAP (NFS mount, 99.99% SLA)
```

- `FSID_MODE=local` in Terraform
- Linux kernel's built-in `fsidd` service
- SQLite file stored on FSx for ONTAP volume
- **$0 additional cost**
- Proxy replacement reuses same FSID mappings (persistence via FSx for ONTAP)

**Terraform config**:
```hcl
fsid_mode        = "local"
fsid_sqlite_path = "/srv/nfs/vol1/.knfsd/fsids.sqlite"
```

**Boot sequence** (managed by proxy-startup.sh):
1. Mount FSx for ONTAP via NFS → `/srv/nfs/vol1/`
2. Configure `/etc/nfs.conf` with SQLite path
3. Start fsidd (reads/creates SQLite on NFS mount)
4. Start NFS re-export
5. Clients can mount

**Limitations**:
- SQLite has weak concurrent write support → single-node only recommended
- If FSx for ONTAP is unreachable → fsidd cannot start (but cache is useless without source anyway)

---

## Decision Flowchart

```
Multi-node (2+ proxies)?
├── Yes → Option A or B
│         ├── Minimize cost → B (Aurora Serverless v2)
│         └── Simplicity → A (RDS db.t4g.micro)
└── No (single-node)
    └── Option D (SQLite on FSx for ONTAP, $0)
```

---

## Related

- [Demo Guide](demo-guide.en.md)
- [Troubleshooting](troubleshooting.en.md)
- [KNFSD kernel fsidd source](https://docs.kernel.org/7.1/filesystems/nfs/reexport.html)
