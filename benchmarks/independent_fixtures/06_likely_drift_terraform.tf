resource "aws_security_group" "likely_access" { name="likely-access" }
resource "aws_instance" "likely_processor" { ami="ami-likely" instance_type="t3.medium" vpc_security_group_ids=[aws_security_group.likely_access.id] }
resource "aws_cloudwatch_log_group" "likely_logs" { name="likely-logs" depends_on=[aws_instance.likely_processor] }
