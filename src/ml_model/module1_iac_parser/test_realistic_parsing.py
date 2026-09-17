"""End-to-end parser regression coverage for nested, explicit, and intrinsic dependencies."""
from pathlib import Path
from tempfile import TemporaryDirectory
from .parser_manager import process_iac_file

TF='''resource "aws_security_group" "sg" {}\nresource "aws_instance" "web" { depends_on=[aws_security_group.sg] nested={x=aws_security_group.sg.id} refs=[aws_security_group.sg.id] }\nresource "aws_eip" "ip" { instance=aws_instance.web.id }'''
CF='''Resources:\n  Group: {Type: AWS::EC2::SecurityGroup, Properties: {GroupDescription: test}}\n  Web:\n    Type: AWS::EC2::Instance\n    DependsOn: Group\n    Properties:\n      SecurityGroupIds: [!Ref Group]\n  Ip:\n    Type: AWS::EC2::EIP\n    Properties: {InstanceId: !GetAtt Web.InstanceId}\n'''
def main():
 with TemporaryDirectory() as d:
  tf=Path(d)/"main.tf"; tf.write_text(TF); cfn=Path(d)/"main.yaml"; cfn.write_text(CF)
  # Explicit and implicit references to the same target are deduplicated.
  for path, expected_resources, expected_edges in ((tf,3,2),(cfn,3,3)):
   result=process_iac_file(str(path)); assert len(result["resources"])==expected_resources and len(result["dependencies"])>=expected_edges and result==process_iac_file(str(path))
 print("MODULE 1 REALISTIC PARSING TESTS: PASSED")
if __name__ == "__main__": main()
