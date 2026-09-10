resource "aws_security_group" "offline_access" { name="offline-access" }
resource "aws_instance" "offline_gateway" { ami="ami-offline" instance_type="t3.micro" vpc_security_group_ids=[aws_security_group.offline_access.id] }
resource "aws_eip" "offline_ip" { instance=aws_instance.offline_gateway.id }
