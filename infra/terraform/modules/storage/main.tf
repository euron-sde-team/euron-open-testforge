# One private bucket for everything too large to keep in Postgres (OBJECTS_BUCKET):
#
#   uploads/<project>/<import>.zip    a project as uploaded, kept until its snapshot exists
#                                     (the worker then deletes it); a leftover from a
#                                     failed import expires after upload_expiration_days
#   snapshots/<project>/<import>.zip  the normalized source snapshot every analysis,
#                                     generation and run reads; kept as long as the project
#   reports/<project>/<report>.<fmt>  exported reports; the scheduler's retention task
#                                     deletes them after RETENTION_DAYS
#
# Versioning is on: an overwritten or deleted object stays recoverable for
# noncurrent_retention_days. Only the api, worker and scheduler task roles may read or
# write here; the sandbox receives a workspace from the worker over HTTP and has no S3
# permission at all.
resource "aws_s3_bucket" "objects" {
  #checkov:skip=CKV_AWS_144:Cross-region replication doubles where customer source code lives; versioning and RDS backups cover recovery.
  #checkov:skip=CKV_AWS_18:Access logging targets a separate log bucket an operator chooses; CloudTrail data events cover object access.
  #checkov:skip=CKV2_AWS_62:No consumer for S3 event notifications.
  bucket        = "${var.name_prefix}-objects"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_versioning" "objects" {
  bucket = aws_s3_bucket.objects.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "objects" {
  bucket                  = aws_s3_bucket.objects.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "objects" {
  bucket = aws_s3_bucket.objects.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "objects" {
  bucket = aws_s3_bucket.objects.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "objects" {
  bucket     = aws_s3_bucket.objects.id
  depends_on = [aws_s3_bucket_versioning.objects]

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Replaced or deleted versions stay recoverable for a while, then go.
  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_retention_days
    }
  }

  # Uploads are deleted once snapshotted; this catches the ones a failed import left.
  rule {
    id     = "expire-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = var.upload_expiration_days
    }
  }
}

# Only needed when a browser fetches objects with JavaScript; a presigned download link
# opened as a navigation needs none, so the default is no CORS at all.
resource "aws_s3_bucket_cors_configuration" "objects" {
  count  = length(var.cors_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.objects.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.cors_origins
    allowed_headers = ["*"]
    expose_headers  = ["Content-Disposition", "Content-Length", "ETag"]
    max_age_seconds = 3600
  }
}

data "aws_iam_policy_document" "objects" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.objects.arn, "${aws_s3_bucket.objects.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "objects" {
  count      = var.enforce_tls ? 1 : 0
  bucket     = aws_s3_bucket.objects.id
  policy     = data.aws_iam_policy_document.objects.json
  depends_on = [aws_s3_bucket_public_access_block.objects]
}
