resource "aws_security_group" "consensus_access" { name="consensus-access" }
resource "aws_instance" "consensus_api" { ami="ami-consensus" instance_type="t3.large" vpc_security_group_ids=[aws_security_group.consensus_access.id] }
resource "aws_cloudwatch_log_group" "consensus_logs" { name="consensus-logs" depends_on=[aws_instance.consensus_api] }
