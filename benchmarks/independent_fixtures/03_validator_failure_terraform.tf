resource "aws_s3_bucket" "validator_artifacts" { bucket="validator-artifacts" }
resource "aws_instance" "validator_gateway" { ami="ami-validator" instance_type="t3.small" depends_on=[aws_s3_bucket.validator_artifacts] }
