provider "aws" {
  region = "us-east-1"
}

# ---------------------------------------------------------------------------
# Minimal, conservative Terraform - use for the "PASS / REVIEW" demo scenario.
# No wildcard IAM, no public buckets, no open ingress.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "telemetry_archive" {
  bucket = "mfg-telemetry-archive-demo"
}

resource "aws_s3_bucket_versioning" "telemetry_archive" {
  bucket = aws_s3_bucket.telemetry_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_iam_role" "archive_reader" {
  name = "mfg-archive-reader-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "archive_read_only" {
  name = "mfg-archive-read-only"
  role = aws_iam_role.archive_reader.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.telemetry_archive.arn,
        "${aws_s3_bucket.telemetry_archive.arn}/*"
      ]
    }]
  })
}
