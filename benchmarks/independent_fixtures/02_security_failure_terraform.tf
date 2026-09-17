resource "aws_security_group" "public_control" { name="public-control" ingress { from_port=22 to_port=22 protocol="tcp" cidr_blocks=["0.0.0.0/0"] } }
resource "aws_instance" "exposed_controller" { ami="ami-security" instance_type="t3.micro" vpc_security_group_ids=[aws_security_group.public_control.id] }
