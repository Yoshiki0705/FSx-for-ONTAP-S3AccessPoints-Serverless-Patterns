####################################################################
# FSID Database — RDS PostgreSQL (Option A) or Aurora Serverless v2 (Option B)
#
# Created only when fsid_mode = "external"
# Controls: var.fsid_db_engine selects between RDS and Aurora
#
# Option A: db.t4g.micro (~$15/month) — simple, single-instance
# Option B: Aurora Serverless v2 (0.5-1 ACU, ~$5-15/month) — auto-scaling
####################################################################

locals {
  create_fsid_db  = var.fsid_mode == "external"
  use_aurora      = local.create_fsid_db && var.fsid_db_engine == "aurora-serverless"
  use_rds         = local.create_fsid_db && var.fsid_db_engine == "rds"
  db_port         = 5432
  db_name         = "knfsd"
  db_username     = "knfsd_admin"
  db_table_name   = "fsids"
}

####################################################################
# Common: Subnet Group + Security Group
####################################################################

resource "aws_db_subnet_group" "fsid" {
  count      = local.create_fsid_db ? 1 : 0
  name       = "${local.name}-fsid-db"
  subnet_ids = var.subnet_ids

  tags = { Name = "${local.name}-fsid-db-subnet-group" }
}

resource "aws_security_group" "fsid_db" {
  count       = local.create_fsid_db ? 1 : 0
  name_prefix = "${local.name}-fsid-db-"
  description = "KNFSD FSID database (PostgreSQL)"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from KNFSD proxy"
    from_port       = local.db_port
    to_port         = local.db_port
    protocol        = "tcp"
    security_groups = [aws_security_group.knfsd.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-fsid-db-sg" }
}

####################################################################
# Random password for DB
####################################################################

resource "random_password" "fsid_db" {
  count   = local.create_fsid_db ? 1 : 0
  length  = 24
  special = false
}

####################################################################
# Option A: RDS PostgreSQL (db.t4g.micro)
####################################################################

resource "aws_db_instance" "fsid" {
  count = local.use_rds ? 1 : 0

  identifier     = "${local.name}-fsid"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = local.db_name
  username = local.db_username
  password = random_password.fsid_db[0].result

  db_subnet_group_name   = aws_db_subnet_group.fsid[0].name
  vpc_security_group_ids = [aws_security_group.fsid_db[0].id]

  skip_final_snapshot       = true
  deletion_protection       = false
  backup_retention_period   = 1
  auto_minor_version_upgrade = true
  publicly_accessible       = false

  tags = { Name = "${local.name}-fsid-rds" }
}

####################################################################
# Option B: Aurora Serverless v2
####################################################################

resource "aws_rds_cluster" "fsid" {
  count = local.use_aurora ? 1 : 0

  cluster_identifier = "${local.name}-fsid"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "16.4"

  database_name   = local.db_name
  master_username = local.db_username
  master_password = random_password.fsid_db[0].result

  db_subnet_group_name   = aws_db_subnet_group.fsid[0].name
  vpc_security_group_ids = [aws_security_group.fsid_db[0].id]

  storage_encrypted   = true
  skip_final_snapshot = true
  deletion_protection = false

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 1.0
  }

  tags = { Name = "${local.name}-fsid-aurora" }
}

resource "aws_rds_cluster_instance" "fsid" {
  count = local.use_aurora ? 1 : 0

  identifier         = "${local.name}-fsid-instance"
  cluster_identifier = aws_rds_cluster.fsid[0].id
  instance_class     = "db.serverless"
  engine             = "aurora-postgresql"
  engine_version     = "16.4"

  publicly_accessible = false

  tags = { Name = "${local.name}-fsid-aurora-instance" }
}

####################################################################
# Outputs: Connection URL for knfsd-fsidd
####################################################################

locals {
  # Build PostgreSQL connection URL based on which DB was created
  fsid_db_endpoint = local.use_rds ? (
    aws_db_instance.fsid[0].endpoint
  ) : local.use_aurora ? (
    aws_rds_cluster.fsid[0].endpoint
  ) : ""

  fsid_db_url = local.create_fsid_db ? (
    "postgres://${local.db_username}:${random_password.fsid_db[0].result}@${local.fsid_db_endpoint}/${local.db_name}"
  ) : ""
}
