resource "aws_security_group" "plant_access" { name="plant-access" ingress { from_port=22 to_port=22 protocol="tcp" cidr_blocks=["0.0.0.0/0"] } }
resource "aws_s3_bucket" "plant_telemetry" { bucket="plant-telemetry" }
resource "aws_db_instance" "plant_database" { identifier="plant-db" instance_class="db.t3.large" engine="postgres" }
resource "aws_instance" "plant_controller" { ami="ami-plant" instance_type="m5.2xlarge" vpc_security_group_ids=[aws_security_group.plant_access.id] depends_on=[aws_s3_bucket.plant_telemetry,aws_db_instance.plant_database] }
resource "aws_eip" "plant_ip" { instance=aws_instance.plant_controller.id }
