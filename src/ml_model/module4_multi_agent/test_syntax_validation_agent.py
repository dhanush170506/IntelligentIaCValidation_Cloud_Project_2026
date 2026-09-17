"""Tests for syntax_validation_agent.py."""

from __future__ import annotations

try:
    from .agent_schema import AgentSeverity, AgentStatus, AgentType
    from .syntax_validation_agent import (
        SyntaxValidationAgent,
        SyntaxValidationAgentError,
    )
    from ..module3_static_validation.validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )
except ImportError:
    from agent_schema import AgentSeverity, AgentStatus, AgentType
    from syntax_validation_agent import SyntaxValidationAgent, SyntaxValidationAgentError
    from validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )


def report(provider: str, findings: tuple[ValidationFinding, ...]) -> ValidationReport:
    summary = ValidationSummary(
        total_checks=len(findings),
        passed=sum(f.status is ValidationStatus.PASSED for f in findings),
        failed=sum(f.status is ValidationStatus.FAILED for f in findings),
        warnings=sum(f.status is ValidationStatus.WARNING for f in findings),
        errors=sum(f.status is ValidationStatus.ERROR for f in findings),
        skipped=sum(f.status is ValidationStatus.SKIPPED for f in findings),
    )
    return ValidationReport(
        provider=provider,
        validation_summary=summary,
        findings=findings,
    )


def test_extracts_terraform_syntax() -> None:
    finding = ValidationFinding(
        tool="TERRAFORM_VALIDATE",
        provider="AWS",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        rule_id="TERRAFORM_VALIDATE",
        message="Invalid reference",
        resource_id="aws_instance.web",
        file_path="main.tf",
        line=12,
        column=4,
    )
    result = SyntaxValidationAgent().run(
        validation_reports=(report("TERRAFORM", (finding,)),)
    )
    assert result.agent_type is AgentType.SYNTAX_VALIDATION
    assert result.status is AgentStatus.COMPLETED
    assert len(result.findings) == 1
    assert result.findings[0].severity is AgentSeverity.HIGH
    assert result.findings[0].resource_id == "aws_instance.web"
    assert result.findings[0].evidence_ids


def test_extracts_cfn_lint_syntax() -> None:
    finding = ValidationFinding(
        tool="CFN_LINT",
        provider="AWS",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        rule_id="E3002",
        message="Invalid property",
    )
    result = SyntaxValidationAgent().run(
        validation_reports=(report("CLOUDFORMATION", (finding,)),)
    )
    assert len(result.findings) == 1


def test_does_not_classify_checkov_as_syntax() -> None:
    finding = ValidationFinding(
        tool="CHECKOV",
        provider="AWS",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        rule_id="CKV_AWS_1",
        message="Security issue",
    )
    result = SyntaxValidationAgent().run(
        validation_reports=(report("TERRAFORM", (finding,)),)
    )
    assert result.findings == ()
    assert result.confidence == 1.0


def test_tflint_only_syntax_like_findings_are_selected() -> None:
    syntax = ValidationFinding(
        tool="TFLINT",
        provider="AWS",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.MEDIUM,
        rule_id="PARSER_ERROR",
        message="Parser error",
    )
    lint = ValidationFinding(
        tool="TFLINT",
        provider="AWS",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.LOW,
        rule_id="aws_instance_invalid_type",
        message="Invalid instance type",
    )
    result = SyntaxValidationAgent().run(
        validation_reports=(report("TERRAFORM", (syntax, lint)),)
    )
    assert len(result.findings) == 1
    assert result.findings[0].rule_id == "PARSER_ERROR"


def test_empty_reports_produce_clean_result() -> None:
    result = SyntaxValidationAgent().run(validation_reports=())
    assert result.status is AgentStatus.COMPLETED
    assert result.findings == ()
    assert result.confidence == 1.0


def test_invalid_input_fails_cleanly() -> None:
    result = SyntaxValidationAgent().run(validation_reports=("bad",))
    assert result.status is AgentStatus.FAILED
    assert isinstance(result.message, str)


if __name__ == "__main__":
    tests = [
        test_extracts_terraform_syntax,
        test_extracts_cfn_lint_syntax,
        test_does_not_classify_checkov_as_syntax,
        test_tflint_only_syntax_like_findings_are_selected,
        test_empty_reports_produce_clean_result,
        test_invalid_input_fails_cleanly,
    ]
    for fn in tests:
        fn()
        print(f"[PASS] {fn.__name__}")
    print("All Syntax Validation Agent tests PASSED.")
