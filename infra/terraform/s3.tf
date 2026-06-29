resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ─── Task 7: Customer-managed KMS key for S3 at rest ─────────────────────────
resource "aws_kms_key" "s3" {
  description             = "${var.project_name} S3 documents encryption key"
  deletion_window_in_days = 14
  enable_key_rotation     = true

  tags = {
    Name        = "${var.project_name}-s3-kms"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.project_name}-s3-${var.environment}"
  target_key_id = aws_kms_key.s3.key_id
}

resource "aws_s3_bucket" "documents" {
  bucket = "${var.project_name}-docs-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "Bank Statement Documents"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_ownership_controls" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Task 7: AES-256 SSE-KMS encryption at rest (customer-managed key)
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    # Disable SSE-S3 fallback — require KMS at all times
    bucket_key_enabled = true
  }
}

# Task 11: Delete original uploaded PDFs after 90 days.
# Processed outputs and exports must use prefixes outside uploads/originals/pdf/.
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "delete-original-uploaded-pdfs-after-90-days"
    status = "Enabled"

    filter {
      prefix = "uploads/originals/pdf/"
    }

    expiration {
      days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Enforce encrypted transport — deny any unencrypted (HTTP) requests
resource "aws_s3_bucket_policy" "documents_tls_only" {
  bucket = aws_s3_bucket.documents.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
