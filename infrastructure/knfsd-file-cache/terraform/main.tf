####################################################################
# KNFSD File Cache — Production-Ready Deployment
#
# Lessons applied from 2026-07-22 verification:
# 1. Public IP required for proxy-startup.sh (EC2 API access)
# 2. SSM Parameter Store must be populated before instance launch
# 3. Security Group needs TCP + UDP for NFS ports
# 4. KNFSD AMI uses proxy-startup.sh via CLUSTER_NAME tag
# 5. knfsd-fsidd is required for NFS re-export FSID management
#
# Deployment flow:
#   scripts/setup.sh      → Build AMI (Packer)
#   scripts/create-ssm-params.sh → Create SSM Parameter Store entries
#   terraform apply       → Deploy proxy instance
#   proxy-startup.sh runs automatically on boot via user_data
####################################################################

locals {
  name         = "${var.name_prefix}-${var.environment}"
  cluster_name = var.name_prefix

  # NFS mount options (used by proxy-startup.sh via SSM)
  export_map = join("\n", [
    for m in var.source_mounts :
    "${m.host};${m.export};${m.export}"
  ])
}

####################################################################
# Security Group — TCP + UDP for all NFS ports
####################################################################

resource "aws_security_group" "knfsd" {
  name_prefix = "${local.name}-"
  description = "KNFSD File Cache proxy"
  vpc_id      = var.vpc_id

  # NFS (TCP + UDP)
  ingress {
    description = "NFS TCP"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }
  ingress {
    description = "NFS UDP"
    from_port   = 2049
    to_port     = 2049
    protocol    = "udp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }

  # Portmapper (TCP + UDP)
  ingress {
    description = "Portmapper TCP"
    from_port   = 111
    to_port     = 111
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }
  ingress {
    description = "Portmapper UDP"
    from_port   = 111
    to_port     = 111
    protocol    = "udp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }

  # Mountd (TCP + UDP)
  ingress {
    description = "Mountd TCP"
    from_port   = 20048
    to_port     = 20048
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }
  ingress {
    description = "Mountd UDP"
    from_port   = 20048
    to_port     = 20048
    protocol    = "udp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }

  # All outbound (NFS to source, EC2 API, SSM, CloudWatch)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-sg" }
  lifecycle { create_before_destroy = true }
}

####################################################################
# Data Sources
####################################################################

data "aws_vpc" "selected" {
  id = var.vpc_id
}

####################################################################
# IAM Role — SSM + CloudWatch + EC2 Tags + Secrets Manager
####################################################################

resource "aws_iam_role" "knfsd" {
  name_prefix = "${local.name}-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.knfsd.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cw" {
  role       = aws_iam_role.knfsd.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Additional permissions for proxy-startup.sh
resource "aws_iam_role_policy" "knfsd_extra" {
  name = "${local.name}-extra"
  role = aws_iam_role.knfsd.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateTags",
          "ec2:DescribeTags"
        ]
        Resource = "*"
        Condition = {
          StringEquals = { "ec2:ResourceTag/Component" = "knfsd-file-cache" }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParametersByPath", "ssm:GetParameter"]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/knfsd/${local.cluster_name}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.fsxn_secret_arn != "" ? var.fsxn_secret_arn : "arn:aws:secretsmanager:${var.aws_region}:*:secret:fsxn/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "knfsd" {
  name_prefix = "${local.name}-"
  role        = aws_iam_role.knfsd.name
}

####################################################################
# SSM Parameter Store — Configuration for proxy-startup.sh
####################################################################

resource "aws_ssm_parameter" "knfsd" {
  for_each = {
    CLUSTER_NAME            = local.cluster_name
    EXPORT_MAP              = local.export_map
    EXPORT_CIDR             = join(",", var.export_cidrs)
    NFS_MOUNT_VERSION       = var.nfs_version
    NUM_NFS_THREADS         = tostring(var.nfs_threads)
    CACHEFILESD_DISK_TYPE   = var.cache_disk_type
    FSID_MODE               = var.fsid_mode
    ENABLE_KNFSD_AGENT      = "true"
    ENABLE_METRICS          = tostring(var.enable_metrics)
    ENABLE_NETAPP_AUTO_DETECT = "false"
    AUTO_REEXPORT           = "false"
    NOHIDE                  = "false"
    NCONNECT                = "1"
    ACDIRMIN                = tostring(var.acdirmin)
    ACDIRMAX                = tostring(var.acdirmax)
    ACREGMIN                = tostring(var.acregmin)
    ACREGMAX                = tostring(var.acregmax)
    RSIZE                   = "1048576"
    WSIZE                   = "1048576"
    READ_AHEAD              = "0"
    TCP_SLOT_TABLE_ENTRIES  = "128"
    TCP_MAX_SLOT_TABLE_ENTRIES = "65536"
    VFS_CACHE_PRESSURE      = "100"
    SVC_RPC_PER_CONNECTION_LIMIT = "0"
    DISABLED_NFS_VERSIONS   = "\"\""
    EXCLUDED_EXPORTS        = "\"\""
    INCLUDED_EXPORTS        = "\"\""
    EXPORT_HOST_AUTO_DETECT = "\"\""
    EXPORT_OPTIONS          = "\"\""
    MOUNT_OPTIONS           = "\"\""
    NETAPP_HOST             = "\"\""
    NETAPP_URL              = "\"\""
    NETAPP_USER             = "\"\""
    NETAPP_SECRET           = "\"\""
    NETAPP_CA               = "\"\""
    NETAPP_ALLOW_COMMON_NAME = "false"
    NETAPP_SECRET_REGION    = "\"\""
    NETAPP_SECRET_VERSION   = "AWSCURRENT"
    METRICS_AGENT_CONFIG    = "\"\""
    FSID_DATABASE_CONFIG    = var.fsid_mode == "external" ? jsonencode({url = coalesce(var.fsid_database_url, local.fsid_db_url), table_name = "fsids", create_table = true, iam_auth = false}) : "\"\""
  }

  name  = "/knfsd/${local.cluster_name}/${each.key}"
  type  = "String"
  value = each.value

  tags = { Component = "knfsd-file-cache" }
}

####################################################################
# EC2 Instance — KNFSD Proxy
####################################################################

resource "aws_instance" "knfsd" {
  count = var.cluster_size

  ami                         = var.knfsd_ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_ids[count.index % length(var.subnet_ids)]
  vpc_security_group_ids      = [aws_security_group.knfsd.id]
  iam_instance_profile        = aws_iam_instance_profile.knfsd.name
  associate_public_ip_address = var.assign_public_ip
  key_name                    = var.key_pair_name != "" ? var.key_pair_name : null

  # proxy-startup.sh reads CLUSTER_NAME from instance tag
  # then loads config from SSM Parameter Store: /knfsd/{CLUSTER_NAME}/*
  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -e

    # Configure FSID SQLite path on FSx for ONTAP (persistent across restarts)
    %{if var.fsid_mode == "local"}
    SQLITE_DIR=$(dirname "${var.fsid_sqlite_path}")
    # Wait for source NFS to be mounted (proxy-startup.sh will mount it)
    # Configure nfs.conf to use FSx for ONTAP path for SQLite
    sed -i "s|sqlitedb=.*|sqlitedb=${var.fsid_sqlite_path}|" /etc/nfs.conf
    %{endif}

    export CLUSTER_NAME=${local.cluster_name}
    /usr/local/sbin/proxy-startup.sh
  EOF
  )

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  tags = {
    Name                       = "${local.name}-proxy-${count.index}"
    "knfsd-file-cache:cluster" = local.cluster_name
  }

  depends_on = [aws_ssm_parameter.knfsd]
}
