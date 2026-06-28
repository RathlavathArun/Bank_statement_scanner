resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

resource "aws_ecr_repository" "web" {
  name         = "${var.project_name}-web"
  force_delete = true
}

resource "aws_ecr_repository" "api" {
  name         = "${var.project_name}-api"
  force_delete = true
}

resource "aws_ecr_repository" "parser" {
  name         = "${var.project_name}-parser"
  force_delete = true
}

# --- IAM Roles ---

resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-ecsTaskExecutionRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecsTaskRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "s3_access" {
  name = "${var.project_name}-s3-access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_s3_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_policy" "ses_send_email" {
  name = "${var.project_name}-ses-send-email"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_ses_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ses_send_email.arn
}

# --- CloudWatch Logs ---
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 14
}

# --- Task Definitions & Services ---
# NOTE: We use nginx as a placeholder image so terraform can apply successfully the first time.
# After terraform apply, you will build and push the real docker images to ECR, and update the ECS service.

# Web Task
resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project_name}-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = "nginx:alpine" # Placeholder — deploy.sh replaces with real ECR image
      essential = true
      portMappings = [
        {
          containerPort = 3000
          hostPort      = 3000
        }
      ]
      environment = [
        {
          name  = "API_URL"
          value = "http://api.${var.project_name}.local:8000"
        },
        {
          name  = "HOSTNAME"
          value = "0.0.0.0"
        },
        {
          name  = "PORT"
          value = "3000"
        },
        {
          name  = "NODE_ENV"
          value = "production"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "web"
        }
      }
    }
  ])
}

# Web Service
resource "aws_ecs_service" "web" {
  name            = "${var.project_name}-web-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
}

# --- Service Discovery (Cloud Map) ---
# Enables the web container to reach the API container internally via DNS,
# which is required because Next.js rewrites proxy requests server-side.

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${var.project_name}.local"
  vpc  = aws_vpc.main.id

  tags = {
    Name        = "${var.project_name}-namespace"
    Environment = var.environment
  }
}

resource "aws_service_discovery_service" "api" {
  name = "api"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "clamav" {
  name = "clamav"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# --- API Task Definition ---
# Higher resources than web (512 CPU / 1024 MB) for OCR, PDF parsing, and LLM calls.

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "nginx:alpine" # Placeholder — deploy.sh replaces with real ECR image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      environment = [
        {
          name  = "DATABASE_URL"
          value = "postgresql+asyncpg://bse_admin:${var.db_password}@${aws_db_instance.postgres.endpoint}/bank_statements"
        },
        {
          name  = "REDIS_URL"
          value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
        },
        {
          name  = "S3_BUCKET"
          value = aws_s3_bucket.documents.bucket
        },
        {
          name  = "SMTP_USERNAME"
          value = var.smtp_username
        },
        {
          name  = "SMTP_PASSWORD"
          value = var.smtp_password
        },
        {
          name  = "SMTP_FROM_EMAIL"
          value = var.smtp_from_email != "" ? var.smtp_from_email : var.smtp_username
        },
        {
          name  = "EMAIL_PROVIDER"
          value = "ses"
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = var.aws_region
        },
        {
          name  = "TEXTRACT_REGION"
          value = var.aws_region
        },
        {
          name  = "S3_ENDPOINT"
          value = ""
        },
        {
          name  = "S3_ACCESS_KEY"
          value = ""
        },
        {
          name  = "S3_SECRET_KEY"
          value = ""
        },
        {
          name  = "JWT_SECRET_KEY"
          value = var.jwt_secret
        },
        {
          name  = "TOTP_ENCRYPTION_KEY"
          value = var.totp_encryption_key
        },
        {
          name  = "API_HOST"
          value = "0.0.0.0"
        },
        {
          name  = "API_PORT"
          value = "8000"
        },
        {
          name = "CORS_ORIGINS"
          # CloudFront URL is the primary origin; ALB direct access and localhost are included for testing.
          # TODO (custom domain): Add "https://app.yourdomain.com" here once you have one.
          value = "https://${aws_cloudfront_distribution.main.domain_name},http://${aws_lb.main.dns_name},https://${aws_lb.main.dns_name},http://localhost:3000"
        },
        {
          name  = "DEBUG"
          value = "false"
        },
        {
          name  = "CLAMAV_ENABLED"
          value = "true"
        },
        {
          name  = "CLAMAV_HOST"
          value = "clamav.${var.project_name}.local"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

# API Service
resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }
}

# --- ClamAV Task Definition ---
resource "aws_ecs_task_definition" "clamav" {
  family                   = "${var.project_name}-clamav"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "3072"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "clamav"
      image     = "clamav/clamav:latest"
      essential = true
      portMappings = [
        {
          containerPort = 3310
          hostPort      = 3310
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "clamav"
        }
      }
    }
  ])
}

# ClamAV Service
resource "aws_ecs_service" "clamav" {
  name            = "${var.project_name}-clamav-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.clamav.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.clamav.arn

  }
}
