####################################################################
# General
####################################################################

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "ap-northeast-1"
}

variable "environment" {
  description = "Environment name (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Prefix for resource naming. Also used as CLUSTER_NAME for SSM Parameter Store path (/knfsd/{name_prefix}/...)"
  type        = string
  default     = "fsxn-knfsd"
}

####################################################################
# Network
####################################################################

variable "vpc_id" {
  description = "VPC ID where FSx for ONTAP is deployed"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for KNFSD instances (same AZ as FSx for ONTAP recommended)"
  type        = list(string)
}

variable "assign_public_ip" {
  description = <<-EOT
    Assign public IP to KNFSD instances. REQUIRED if:
    - Subnet does not have NAT Gateway
    - No EC2 VPC Endpoint exists
    proxy-startup.sh needs EC2 API access for status tags.

    Security note: NFS ports are NOT exposed to internet.
    The Security Group restricts all NFS ingress to VPC CIDR only.
    Public IP is used solely for outbound EC2 API access.

    For production in restricted environments:
    - Set assign_public_ip = false
    - Add EC2 Interface VPC Endpoint (com.amazonaws.{region}.ec2)
    - Add SSM VPC Endpoints (ssm, ssmmessages, ec2messages)
  EOT
  type        = bool
  default     = true
}

variable "export_cidrs" {
  description = "CIDR blocks allowed to mount NFS re-exports (default: VPC CIDR via 10.0.0.0/8)"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

####################################################################
# KNFSD Instance
####################################################################

variable "knfsd_ami_id" {
  description = "AMI ID built by Packer (from KNFSD File Cache repo). Build with: packer build -var 'REGION=ap-northeast-1' -var 'ARCH=[\"arm64\"]' ."
  type        = string
}

variable "instance_type" {
  description = <<-EOT
    EC2 instance type. Must have local NVMe for FS-Cache (L2):
    - Test:  m6gd.xlarge   (4 vCPU, 16 GB RAM, 237 GB NVMe, ~$0.29/hr)
    - Small: im4gn.4xlarge (16 vCPU, 64 GB RAM, 7.5 TB NVMe)
    - Prod:  im4gn.16xlarge (64 vCPU, 256 GB RAM, 30 TB NVMe, ~$5.82/hr)
  EOT
  type        = string
  default     = "m6gd.xlarge"
}

variable "key_pair_name" {
  description = "EC2 key pair for SSH access (optional, SSM recommended instead)"
  type        = string
  default     = ""
}

####################################################################
# NFS Source Configuration
####################################################################

variable "source_mounts" {
  description = <<-EOT
    NFS exports to cache from FSx for ONTAP.
    Each entry: { host = "NFS LIF IP", export = "/junction-path", mount = "/junction-path" }
    Find NFS LIF: aws fsx describe-storage-virtual-machines --query 'StorageVirtualMachines[].Endpoints.Nfs.IpAddresses[0]'
    Find junction: aws fsx describe-volumes --query 'Volumes[].OntapConfiguration.JunctionPath'
  EOT
  type = list(object({
    host   = string
    export = string
    mount  = string
  }))
}

variable "nfs_version" {
  description = "NFS version for source mount. MUST be 4.1 for FSx for ONTAP re-export (NFSv3 filehandle size limit causes Stale file handle on write)"
  type        = string
  default     = "4.1"

  validation {
    condition     = var.nfs_version != "3"
    error_message = "NFSv3 is incompatible with FSx for ONTAP re-export due to filehandle size overflow (40+ bytes source + 22 bytes re-export > 64-byte NFSv3 limit). Use \"4.1\" or \"4.2\". See: https://github.com/awslabs/knfsd-file-cache/issues/40"
  }

  validation {
    condition     = contains(["4.1", "4.2", "4"], var.nfs_version)
    error_message = "Supported values: \"4.1\" (recommended), \"4.2\", or \"4\"."
  }
}

####################################################################
# Cache Configuration
####################################################################

variable "cache_disk_type" {
  description = "Cache disk type: 'local-nvme' for instance store NVMe, 'ebs' for attached EBS volumes"
  type        = string
  default     = "local-nvme"
}

variable "nfs_threads" {
  description = "Number of NFS server threads (16 for test, 64-128 for production)"
  type        = number
  default     = 16
}

variable "acdirmin" {
  description = "Min directory attribute cache timeout (seconds). Lower = fresher but more source traffic"
  type        = number
  default     = 3
}

variable "acdirmax" {
  description = "Max directory attribute cache timeout (seconds)"
  type        = number
  default     = 60
}

variable "acregmin" {
  description = "Min file attribute cache timeout (seconds)"
  type        = number
  default     = 3
}

variable "acregmax" {
  description = "Max file attribute cache timeout (seconds). For dual-path with S3 AP, set to 5-10 for faster consistency"
  type        = number
  default     = 60
}

####################################################################
# Observability
####################################################################

variable "enable_metrics" {
  description = "Enable KNFSD metrics agent (CloudWatch custom metrics, 70+ metrics)"
  type        = bool
  default     = false
}

####################################################################
# FSx for ONTAP Reference
####################################################################

variable "fsxn_file_system_id" {
  description = "FSx for ONTAP file system ID (for CloudWatch dashboard integration)"
  type        = string
  default     = ""
}

variable "fsxn_secret_arn" {
  description = "Secrets Manager ARN for ONTAP admin credentials (for NetApp auto-detect feature)"
  type        = string
  default     = ""
}

####################################################################
# FSID Backend Configuration
####################################################################

variable "fsid_mode" {
  description = <<-EOT
    How KNFSD manages File System Identifiers for NFS re-export.
    Options:
      "local"    — Kernel fsidd + SQLite on FSx for ONTAP NFS mount ($0, recommended for single-node)
      "external" — knfsd-fsidd (Go) + RDS PostgreSQL (required for multi-node)
      "static"   — No fsidd, fixed fsid in exports (BROKEN — causes Stale file handle)
    See docs/fsid-backend-options.md for detailed comparison.
  EOT
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "external", "static"], var.fsid_mode)
    error_message = "Valid values: 'local' (recommended), 'external' (multi-node), 'static' (broken, do not use)"
  }
}

variable "fsid_sqlite_path" {
  description = "Path for SQLite FSID database when fsid_mode=local. Placed on FSx for ONTAP NFS mount for persistence across proxy restarts."
  type        = string
  default     = "/srv/nfs/vol1/.knfsd/fsids.sqlite"
}

# Cross-variable validation: fsid_mode=local is single-node only
variable "cluster_size" {
  description = "Number of KNFSD proxy instances (1 for test, 2+ for production HA)"
  type        = number
  default     = 1

  validation {
    condition     = var.cluster_size >= 1
    error_message = "cluster_size must be >= 1."
  }
}

variable "fsid_database_url" {
  description = "PostgreSQL connection URL when fsid_mode=external (e.g., postgres://user:pass@host:5432/dbname). Leave empty to auto-create DB."
  type        = string
  default     = ""
  sensitive   = true
}

variable "fsid_db_engine" {
  description = <<-EOT
    Database engine for FSID when fsid_mode=external:
      "rds"              — RDS PostgreSQL db.t4g.micro (~$15/month, Option A)
      "aurora-serverless" — Aurora Serverless v2 0.5-1 ACU (~$5-15/month, Option B)
    Ignored when fsid_mode=local.
  EOT
  type        = string
  default     = "aurora-serverless"

  validation {
    condition     = contains(["rds", "aurora-serverless"], var.fsid_db_engine)
    error_message = "Valid values: 'rds' or 'aurora-serverless'"
  }
}
