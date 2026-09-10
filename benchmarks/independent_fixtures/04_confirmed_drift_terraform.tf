resource "aws_security_group" "drift_access" { name="drift-access" }
resource "aws_instance" "drift_machine" { ami="ami-drift" instance_type="t3.micro" vpc_security_group_ids=[aws_security_group.drift_access.id] }
resource "aws_eip" "drift_ip" { instance=aws_instance.drift_machine.id }
