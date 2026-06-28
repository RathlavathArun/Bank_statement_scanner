variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "bank-statement"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
  default     = "bse_secret_2026"
}

variable "smtp_username" {
  description = "SMTP Username for sending emails"
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "SMTP Password for sending emails"
  type        = string
  sensitive   = true
  default     = ""
}

variable "smtp_from_email" {
  description = "Verified sender email identity used by SES and SMTP From headers"
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "jwt_secret" {
  description = "Secret key for JWT token signing"
  type        = string
  sensitive   = true
  default     = "change-this-in-production-jwt-secret-key-2026"
}

variable "totp_encryption_key" {
  description = "URL-safe base64 Fernet key used to encrypt TOTP secrets"
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{43}=$", var.totp_encryption_key))
    error_message = "totp_encryption_key must be a Fernet key (32 URL-safe base64 bytes)."
  }
}

# Task 6: TLS 1.3 at ALB
variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate to attach to the ALB HTTPS listener (TLS 1.3). Required in production."
  type        = string
  default     = ""
}
