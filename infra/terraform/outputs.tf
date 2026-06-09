output "aws_region" {
  description = "The AWS region where resources are deployed"
  value       = var.aws_region
}

output "cloudfront_domain" {
  description = "The secure HTTPS CloudFront domain for the website"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "alb_dns_name" {
  description = "The raw HTTP DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "s3_bucket_name" {
  description = "The name of the S3 bucket for documents"
  value       = aws_s3_bucket.documents.bucket
}

output "rds_endpoint" {
  description = "The connection endpoint for the RDS instance"
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "The connection endpoint for the ElastiCache Redis cluster"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "ecr_web_repo_url" {
  description = "ECR repository URL for the web image"
  value       = aws_ecr_repository.web.repository_url
}

output "ecr_api_repo_url" {
  description = "ECR repository URL for the API image"
  value       = aws_ecr_repository.api.repository_url
}

output "api_discovery_dns" {
  description = "Cloud Map DNS name for internal API service discovery"
  value       = "api.${var.project_name}.local"
}
