provider "aws" {
  region = "us-east-1"
}

# ---------------------------------------------------------------------------
# Intentionally risky Terraform - use for the "FAIL verdict" demo scenario.
#   1. Public-read S3 bucket policy      -> security agent finding
#   2. Open SSH (0.0.0.0/0) ingress      -> security agent finding
#   3. Wildcard (*) IAM role policy      -> security agent finding
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "manufacturing_data" {
  bucket = "smart-mfg-telemetry-data"
}

resource "aws_s3_bucket_policy" "public_read" {
  bucket = aws_s3_bucket.manufacturing_data.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = ["s3:GetObject"]
      Resource  = ["arn:aws:s3:::smart-mfg-telemetry-data/*"]
    }]
  })
}

resource "aws_security_group_rule" "open_ingress" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = "sg-0123456789abcdef0"
}

resource "aws_iam_role" "operator" {
  name = "mfg-line-operator-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "overbroad" {
  name = "mfg-line-operator"
  role = aws_iam_role.operator.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["*"]
      Resource = ["*"]
    }]
  })
}
