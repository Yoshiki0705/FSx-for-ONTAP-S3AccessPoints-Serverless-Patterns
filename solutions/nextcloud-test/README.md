# Nextcloud External Storage — S3 AP Verification Environment

Local Docker setup for verifying Nextcloud's External Storage integration with S3 buckets and FSx for ONTAP S3 Access Points.

## Quick Start

```bash
# 1. Start Nextcloud + MariaDB
make up

# 2. Configure External Storage with your S3 bucket or S3 AP alias
make configure-s3

# 3. Verify connection
make verify

# 4. Open Nextcloud in browser
open http://localhost:8080
# Login: admin / admin123
# Navigate to: Files → FSxONTAP-Data
```

## Prerequisites

- Docker + Docker Compose
- AWS CLI configured with valid credentials
- (Optional) FSx for ONTAP with S3 Access Point attached

## Configuration

Edit `Makefile` variables or set environment variables:

| Variable | Default | Description |
|---|---|---|
| `S3_BUCKET` | (empty) | S3 bucket name or S3 AP alias |
| `S3_REGION` | `ap-northeast-1` | AWS region |
| `S3_HOSTNAME` | `s3.ap-northeast-1.amazonaws.com` | S3 endpoint |
| `MOUNT_NAME` | `FSxONTAP-Data` | Nextcloud folder name |

### For FSx for ONTAP S3 Access Point

```bash
export S3_BUCKET=my-s3-access-point01-abc123-s3alias
make configure-s3
```

### For Regular S3 Bucket (DemoMode)

```bash
export S3_BUCKET=my-test-bucket-name
make configure-s3
```

## Commands

| Command | Description |
|---|---|
| `make up` | Start containers + enable External Storage app |
| `make configure-s3` | Configure S3 backend with current AWS credentials |
| `make verify` | Verify External Storage connection |
| `make list-files` | List files via WebDAV API |
| `make down` | Stop containers (data preserved in volumes) |
| `make clean` | Stop containers + delete volumes (full reset) |

## Key Findings (from verification)

### 1. `use_path_style=true` is REQUIRED

S3 Access Point aliases use path-style addressing. Without this setting, Nextcloud attempts virtual-hosted-style which fails for AP aliases.

### 2. Credentials Must Be Set Individually

`occ files_external:config` requires separate invocations per parameter. Batch configuration fails with "Too many arguments" error.

```bash
# ✅ Correct (one parameter per call)
occ files_external:config 1 bucket my-bucket
occ files_external:config 1 key AKIA...

# ❌ Wrong (multiple -c flags in create)
occ files_external:create ... -c bucket=x -c key=y  # Fails
```

### 3. Empty Credentials → IMDS Fallback

If `key` or `secret` is empty, Nextcloud's AWS SDK falls back to EC2 Instance Metadata Service (169.254.169.254). In Docker, this always times out. Always set credentials explicitly.

### 4. Same Config Works for FSx for ONTAP

Replace `bucket` value with the S3 AP alias — all other settings remain identical. No code changes needed.

### 5. Nextcloud + S3 AP Data Visibility

Files written via NFS/SMB to FSx for ONTAP volumes appear immediately in Nextcloud's file browser (ONTAP provides strong consistency for S3 AP reads).

## Cleanup

```bash
make clean  # Removes containers AND volumes (full reset)
```

## Related Documentation

- [Nextcloud External Storage Setup Guide](../../docs/nextcloud-external-storage-s3ap.md)
- [File Portal UI Options (Amplify / Nextcloud / Custom)](../../docs/file-portal-amplify-gen2.md)
- [S3AP Compatibility Notes](../../docs/s3ap-compatibility-notes.md)
