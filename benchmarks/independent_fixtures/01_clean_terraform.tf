resource "aws_security_group" "clean_access" { name="clean-access" }
resource "aws_instance" "clean_worker" { ami="ami-clean" instance_type="t3.micro" vpc_security_group_ids=[aws_security_group.clean_access.id] }
