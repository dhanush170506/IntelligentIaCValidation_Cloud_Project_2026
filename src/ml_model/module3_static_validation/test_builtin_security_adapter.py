"""Tests: normal upload flow must produce content-derived reports.

Covers:
  * built-in Module 3 security adapter (Terraform + CloudFormation)
  * end-to-end content sensitivity through the api.py orchestrator
    (two materially different uploads must produce different reports)
  * clean IaC must produce fewer/no builtin findings than insecure IaC
Run from the project root:
    python -m pytest src/ml_model/module3_static_validation/test_builtin_security_adapter.py -q
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.ml_model.module3_static_validation.builtin_security_adapter import (
    TOOL_NAME,
    BuiltinSecurityAdapter,
)
from src.ml_model.module3_static_validation.validation_schema import (
    ValidationSeverity,
    ValidationStatus,
)

INSECURE_TERRAFORM = """
resource "aws_s3_bucket" "data" {
  bucket = "corp-logs-2026"
  acl    = "public-read"
}

resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"
}
"""

SECURE_TERRAFORM = """
resource "aws_s3_bucket" "data" {
  bucket = "corp-logs-2026"

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

resource "aws_security_group" "web" {
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}

resource "aws_instance" "app" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    encrypted = true
  }
}
"""

PUBLIC_CFN = """
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  BadBucket:
    Type: AWS::S3::Bucket
    Properties:
      AccessControl: PublicRead
"""


def _validate(tmp_path: Path, filename: str, content: str):
    target = tmp_path / filename
    target.write_text(content, encoding="utf-8")
    return BuiltinSecurityAdapter().validate(target)


def _findings_by_rule(report) -> dict:
    return {f.rule_id: f for f in report.findings}


def test_terraform_public_acl_produces_high_finding(tmp_path):
    report = _validate(tmp_path, "main.tf", INSECURE_TERRAFORM)
    rules = _findings_by_rule(report)
    assert "TF_S3_PUBLIC_ACL" in rules
    assert rules["TF_S3_PUBLIC_ACL"].severity is ValidationSeverity.HIGH
    assert rules["TF_S3_PUBLIC_ACL"].status is ValidationStatus.FAILED
    assert rules["TF_S3_PUBLIC_ACL"].tool == TOOL_NAME
    assert rules["TF_S3_PUBLIC_ACL"].resource_id == "aws_s3_bucket.data"


def test_terraform_ssh_world_open_produces_high_finding(tmp_path):
    report = _validate(tmp_path, "main.tf", INSECURE_TERRAFORM)
    assert "TF_SG_SSH_WORLD_OPEN" in _findings_by_rule(report)


def test_terraform_imdsv1_and_unencrypted_root_detected(tmp_path):
    report = _validate(tmp_path, "main.tf", INSECURE_TERRAFORM)
    rules = _findings_by_rule(report)
    assert "TF_IMDSV1_ALLOWED" in rules
    assert "TF_ROOT_VOLUME_UNENCRYPTED" in rules


def test_secure_terraform_produces_no_builtin_findings(tmp_path):
    report = _validate(tmp_path, "main.tf", SECURE_TERRAFORM)
    assert len(report.findings) == 0


def test_insecure_vs_secure_terraform_differ(tmp_path):
    insecure = _validate(tmp_path, "a.tf", INSECURE_TERRAFORM)
    secure = _validate(tmp_path, "b.tf", SECURE_TERRAFORM)
    assert len(insecure.findings) > len(secure.findings)


def test_cloudformation_public_read_detected(tmp_path):
    report = _validate(tmp_path, "template.yaml", PUBLIC_CFN)
    rules = _findings_by_rule(report)
    assert "CFN_S3_PUBLIC_ACL" in rules
    assert rules["CFN_S3_PUBLIC_ACL"].provider == "CloudFormation"


def test_directory_input_scans_all_iac_files(tmp_path):
    (tmp_path / "main.tf").write_text(INSECURE_TERRAFORM, encoding="utf-8")
    report = BuiltinSecurityAdapter().validate(tmp_path)
    assert len(report.findings) >= 4


def test_report_summary_consistent_with_findings(tmp_path):
    report = _validate(tmp_path, "main.tf", INSECURE_TERRAFORM)
    assert report.validation_summary.failed >= 4
    assert len(report.findings) == report.validation_summary.failed


# ---------------------------------------------------------------------------
# End-to-end: the orchestrator wired in src/ml_model/api.py (normal upload
# path) must produce content-derived reports for different uploads.
# ---------------------------------------------------------------------------

def _run_normal_flow(content: str) -> dict:
    from src.ml_model.api import orchestrator

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "main.tf"
        path.write_text(content, encoding="utf-8")
        result = orchestrator.run(iac_path=str(path), project="content-sensitivity-test")
    return result.assurance_report.to_dict()


@pytest.mark.parametrize("report_key", ["security", "confidence"])
def test_end_to_end_reports_differ_for_different_uploads(report_key):
    insecure = _run_normal_flow(INSECURE_TERRAFORM)
    secure = _run_normal_flow(SECURE_TERRAFORM)
    assert insecure[report_key]["score"] != secure[report_key]["score"], (
        f"{report_key} score must reflect the actual uploaded IaC content"
    )


def test_end_to_end_recommendation_sets_differ_for_different_uploads():
    insecure = _run_normal_flow(INSECURE_TERRAFORM)
    secure = _run_normal_flow(SECURE_TERRAFORM)

    def categories(report):
        return {r["category"] for r in report.get("recommendations", [])}

    # Security/deployment recommendations appear only for the insecure IaC.
    assert "SECURITY" in categories(insecure)
    assert "SECURITY" not in categories(secure)
    assert categories(insecure) != categories(secure)


def test_end_to_end_security_finding_derived_from_content():
    from src.ml_model.api import orchestrator

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "main.tf"
        path.write_text(INSECURE_TERRAFORM, encoding="utf-8")
        result = orchestrator.run(iac_path=str(path), project="finding-source-test")

    security_results = [
        r for r in result.agent_results
        if r.agent_type.value == "SECURITY_VALIDATION"
    ]
    assert security_results, "Security agent must run"
    rule_ids = {f.rule_id for r in security_results for f in r.findings}
    assert "TF_S3_PUBLIC_ACL" in rule_ids, "finding must be derived from the uploaded IaC"
