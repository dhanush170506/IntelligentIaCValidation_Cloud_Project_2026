"""Tests for the Module 4 Security Validation Agent."""

from __future__ import annotations

try:
    from .security_validation_agent import (
        SecurityValidationAgent,
        SecurityValidationAgentError,
    )
    from ..module3_static_validation.validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )
    from .agent_schema import AgentSeverity, AgentStatus, AgentType
except ImportError:  # pragma: no cover
    from security_validation_agent import (
        SecurityValidationAgent,
        SecurityValidationAgentError,
    )
    from validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )
    from agent_schema import AgentSeverity, AgentStatus, AgentType


def make_report(*findings):
    summary = ValidationSummary(
        total_checks=len(findings),
        passed=sum(f.status == ValidationStatus.PASSED for f in findings),
        failed=sum(f.status == ValidationStatus.FAILED for f in findings),
        warnings=sum(f.status == ValidationStatus.WARNING for f in findings),
        errors=sum(f.status == ValidationStatus.ERROR for f in findings),
        skipped=sum(f.status == ValidationStatus.SKIPPED for f in findings),
    )
    return ValidationReport(
        provider="aws",
        validation_summary=summary,
        findings=tuple(findings),
    )


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    print(f"[PASS] {name}")


def test_extracts_checkov_security_findings():
    finding = ValidationFinding(
        tool="CHECKOV",
        provider="aws",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        rule_id="CKV_AWS_79",
        message="Ensure EC2 instances do not have public IP addresses",
        resource_id="aws_instance.web",
        file_path="main.tf",
        line=12,
        column=3,
    )

    result = SecurityValidationAgent().run([make_report(finding)])

    check(result.status == AgentStatus.COMPLETED, "Checkov result completed")
    check(len(result.findings) == 1, "One security finding extracted")
    check(
        result.findings[0].severity == AgentSeverity.HIGH,
        "Severity mapped to HIGH",
    )
    check(
        result.findings[0].agent_type == AgentType.SECURITY_VALIDATION,
        "Agent type mapped correctly",
    )
    check(
        result.findings[0].resource_id == "aws_instance.web",
        "Resource ID preserved",
    )
    check(
        result.findings[0].rule_id == "CKV_AWS_79",
        "Rule ID preserved",
    )
    check(
        len(result.findings[0].evidence_ids) == 1,
        "Evidence ID generated",
    )


def test_maps_multiple_security_severities():
    findings = [
        ValidationFinding(
            tool="CHECKOV",
            provider="aws",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.CRITICAL,
            rule_id="CKV_CRITICAL",
            message="Critical security issue",
        ),
        ValidationFinding(
            tool="CHECKOV",
            provider="aws",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.MEDIUM,
            rule_id="CKV_MEDIUM",
            message="Medium security issue",
        ),
        ValidationFinding(
            tool="CHECKOV",
            provider="aws",
            status=ValidationStatus.WARNING,
            severity=ValidationSeverity.LOW,
            rule_id="CKV_LOW",
            message="Low security warning",
        ),
    ]

    result = SecurityValidationAgent().run([make_report(*findings)])

    check(len(result.findings) == 3, "All Checkov findings extracted")
    check(
        result.metadata["critical_count"] == 1,
        "Critical count correct",
    )
    check(
        result.metadata["medium_count"] == 1,
        "Medium count correct",
    )
    check(
        result.metadata["low_count"] == 1,
        "Low count correct",
    )


def test_ignores_non_checkov_findings():
    findings = [
        ValidationFinding(
            tool="TERRAFORM_VALIDATE",
            provider="aws",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.HIGH,
            rule_id="TERRAFORM_VALIDATE",
            message="Terraform syntax error",
        ),
        ValidationFinding(
            tool="CFN_LINT",
            provider="aws",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.HIGH,
            rule_id="E3001",
            message="Template error",
        ),
        ValidationFinding(
            tool="TFLINT",
            provider="aws",
            status=ValidationStatus.WARNING,
            severity=ValidationSeverity.MEDIUM,
            rule_id="aws_instance_invalid",
            message="Configuration issue",
        ),
    ]

    result = SecurityValidationAgent().run([make_report(*findings)])

    check(len(result.findings) == 0, "Non-Checkov findings ignored")
    check(result.confidence == 1.0, "Clean result confidence is 1.0")


def test_empty_reports_produce_clean_result():
    result = SecurityValidationAgent().run([])

    check(result.status == AgentStatus.COMPLETED, "Empty input completes")
    check(len(result.findings) == 0, "No findings for empty input")
    check(
        result.metadata["security_finding_count"] == 0,
        "Security finding count is zero",
    )


def test_checkov_tool_name_is_normalized():
    finding = ValidationFinding(
        tool=" checkov ",
        provider="aws",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.CRITICAL,
        rule_id="CKV_TEST",
        message="Security issue",
    )

    result = SecurityValidationAgent().run([make_report(finding)])

    check(len(result.findings) == 1, "Checkov tool name is normalized")


def test_invalid_input_fails_cleanly():
    result = SecurityValidationAgent().run(["not-a-validation-report"])

    check(result.status == AgentStatus.FAILED, "Invalid input returns FAILED result")
    check(
        "ValidationReport" in result.message,
        "Failure message identifies invalid input type",
    )


if __name__ == "__main__":
    tests = [
        test_extracts_checkov_security_findings,
        test_maps_multiple_security_severities,
        test_ignores_non_checkov_findings,
        test_empty_reports_produce_clean_result,
        test_checkov_tool_name_is_normalized,
        test_invalid_input_fails_cleanly,
    ]

    for test in tests:
        test()

    print("All Security Validation Agent tests PASSED.")
