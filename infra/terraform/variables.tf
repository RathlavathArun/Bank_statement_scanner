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
