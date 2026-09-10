resource "aws_security_group" "possible_access" { name="possible-access" }
resource "aws_instance" "possible_sensor" { ami="ami-possible" instance_type="t3.small" vpc_security_group_ids=[aws_security_group.possible_access.id] }
