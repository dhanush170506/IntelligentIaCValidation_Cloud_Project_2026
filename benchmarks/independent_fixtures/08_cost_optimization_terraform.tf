resource "aws_security_group" "cost_access" { name="cost-access" }
resource "aws_instance" "cost_engine" { ami="ami-cost" instance_type="m5.4xlarge" vpc_security_group_ids=[aws_security_group.cost_access.id] }
resource "aws_eip" "cost_ip" { instance=aws_instance.cost_engine.id }
