resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name        = "${var.project_name}-db-subnet-group"
    Environment = var.environment
  }
}

# ─── Task 7: Customer-managed KMS key for RDS at rest ────────────────────────
# PRD §11.1 requires customer-managed KMS (SSE-KMS), not AWS-managed (SSE-S3).
# IMPORTANT: Enable on a fresh RDS instance — changing an existing unencrypted
# instance requires a snapshot restore and a maintenance window.
resource "aws_kms_key" "rds" {
  description             = "${var.project_name} RDS encryption key"
  deletion_window_in_days = 14
  enable_key_rotation     = true

  tags = {
    Name        = "${var.project_name}-rds-kms"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.project_name}-rds-${var.environment}"
  target_key_id = aws_kms_key.rds.key_id
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-db-${var.environment}"
  allocated_storage      = 20
  engine                 = "postgres"
  engine_version         = "16.14"
  instance_class         = "db.t4g.micro"
  db_name                = "bank_statements"
  username               = "bse_admin"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  skip_final_snapshot    = true
  publicly_accessible    = false

  # Task 7: AES-256 SSE-KMS encryption at rest
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  tags = {
    Name        = "${var.project_name}-postgres"
    Environment = var.environment
  }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project_name}-redis-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.database.id]

  tags = {
    Name        = "${var.project_name}-redis"
    Environment = var.environment
  }
}
