"""test_validation_result.py.

Focused tests for `validation_result.py`.

These tests exercise `validation_result`'s own responsibilities only
(creation, combination, summary computation, serialization, and error
handling) — they deliberately do not re-test field-level validation
rules that `validation_schema.py` already owns (e.g. every possible
invalid `line`/`column`/`status` value); a handful of representative
invalid-input cases are included here only to confirm that
`validation_result` correctly surfaces `ValidationSchemaError` failures
as `ValidationResultError`, not to re-verify the underlying rules
themselves.

Run directly:
    python -m src.ml_model.module3_static_validation.test_validation_result
"""

from __future__ import annotations

import sys

# See validation_result.py for why this try/except import pattern is
# used: it lets this file run correctly both via
# `python -m src.ml_model.module3_static_validation.test_validation_result`
# (package context, relative imports resolve) and via direct/flat
# execution (no package context, falls back to flat imports).
try:
    from .validation_result import (
        ValidationResultError,
        add_finding,
        build_report,
        combine_findings,
        create_finding,
        create_report,
        create_summary,
        finding_from_dict,
        finding_to_dict,
        report_from_dict,
        report_to_dict,
        summary_from_dict,
        summary_from_findings,
        summary_to_dict,
    )
    from .validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )
except ImportError:
    from validation_result import (  # type: ignore[no-redef]
        ValidationResultError,
        add_finding,
        build_report,
        combine_findings,
        create_finding,
        create_report,
        create_summary,
        finding_from_dict,
        finding_to_dict,
        report_from_dict,
        report_to_dict,
        summary_from_dict,
        summary_from_findings,
        summary_to_dict,
    )
    from validation_schema import (  # type: ignore[no-redef]
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )

_FAILURES: list[str] = []


def _check(condition: bool, description: str) -> None:
    """Record a single test assertion's outcome.

    Args:
        condition: The condition being asserted.
        description: A short, human-readable description of what was
            checked, printed either way.
    """
    if condition:
        print(f"PASS: {description}")
    else:
        print(f"FAIL: {description}")
        _FAILURES.append(description)


def _expect_error(description: str, fn) -> None:
    """Record whether calling `fn()` raises `ValidationResultError`.

    Args:
        description: A short, human-readable description of what was
            checked, printed either way.
        fn: A zero-argument callable expected to raise
            `ValidationResultError`.
    """
    try:
        fn()
        print(f"FAIL: {description} (no error raised)")
        _FAILURES.append(description)
    except ValidationResultError as exc:
        print(f"PASS: {description}: {exc}")


# ---------------------------------------------------------------------------
# 1. Creating a valid finding
# ---------------------------------------------------------------------------
def test_create_valid_finding() -> None:
    """A single finding can be created via `create_finding()`."""
    finding = create_finding(
        tool="checkov",
        provider="Terraform",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        message="Security group allows unrestricted ingress",
        rule_id="CKV_AWS_24",
        resource_id="aws_security_group.web_sg",
        file_path="sample_terraform.tf",
        line=12,
        column=3,
    )
    _check(isinstance(finding, ValidationFinding), "create_finding returns a ValidationFinding")
    _check(finding.status is ValidationStatus.FAILED, "finding.status is ValidationStatus.FAILED")
    _check(finding.severity is ValidationSeverity.HIGH, "finding.severity is ValidationSeverity.HIGH")

    # status/severity accepted as case-insensitive strings too (delegated
    # to ValidationFinding's own coercion, not reimplemented here).
    finding_from_strings = create_finding(
        tool="tflint", provider="Terraform", status="passed", severity="low", message="OK",
    )
    _check(finding_from_strings.status is ValidationStatus.PASSED, "status coerced from string 'passed'")
    _check(finding_from_strings.severity is ValidationSeverity.LOW, "severity coerced from string 'low'")


# ---------------------------------------------------------------------------
# 2. Creating multiple findings (and combining them)
# ---------------------------------------------------------------------------
def test_create_and_combine_multiple_findings() -> tuple[ValidationFinding, ...]:
    """Findings from multiple sources can be combined into one ordered tuple."""
    terraform_findings = [
        create_finding(tool="checkov", provider="Terraform", status="FAILED", severity="HIGH", message="f1"),
        create_finding(tool="checkov", provider="Terraform", status="PASSED", severity="NONE", message="f2"),
    ]
    checkov_findings = [
        create_finding(tool="tflint", provider="Terraform", status="WARNING", severity="MEDIUM", message="f3"),
        create_finding(tool="tflint", provider="Terraform", status="ERROR", severity="LOW", message="f4"),
        create_finding(tool="tflint", provider="Terraform", status="SKIPPED", severity="INFO", message="f5"),
    ]

    combined = combine_findings(terraform_findings, checkov_findings)
    _check(isinstance(combined, tuple), "combine_findings returns a tuple")
    _check(len(combined) == 5, "combine_findings preserves total count across groups")
    _check(combined[0].message == "f1", "combine_findings preserves order within first group")
    _check(combined[4].message == "f5", "combine_findings preserves order across groups")

    _expect_error(
        "combine_findings rejects a non-ValidationFinding item",
        lambda: combine_findings(["not a finding"]),
    )
    _expect_error(
        "combine_findings rejects a non-iterable group",
        lambda: combine_findings(123),
    )

    return combined


# ---------------------------------------------------------------------------
# 3 & 4. Creating a summary from findings, with correct per-status counts
# ---------------------------------------------------------------------------
def test_summary_from_findings_counts_each_status(combined: tuple[ValidationFinding, ...]) -> ValidationSummary:
    """`summary_from_findings` counts PASSED/FAILED/WARNING/ERROR/SKIPPED correctly."""
    summary = summary_from_findings(combined)
    _check(isinstance(summary, ValidationSummary), "summary_from_findings returns a ValidationSummary")

    expected = {
        "total_checks": 5,
        "passed": 1,
        "failed": 1,
        "warnings": 1,
        "errors": 1,
        "skipped": 1,
    }
    _check(summary.to_dict() == expected, f"summary counts match expected {expected}")

    _expect_error(
        "summary_from_findings rejects a non-ValidationFinding item",
        lambda: summary_from_findings(["not a finding"]),
    )

    return summary


# ---------------------------------------------------------------------------
# 5. Creating a complete ValidationReport
# ---------------------------------------------------------------------------
def test_build_complete_report(combined: tuple[ValidationFinding, ...]) -> ValidationReport:
    """`build_report` produces a report whose summary matches its findings."""
    report = build_report(provider="Terraform", findings=combined)
    _check(isinstance(report, ValidationReport), "build_report returns a ValidationReport")
    _check(report.provider == "Terraform", "report.provider is set correctly")
    _check(len(report.findings) == 5, "report contains every combined finding")
    _check(
        report.validation_summary.total_checks == len(report.findings),
        "build_report's summary.total_checks matches len(findings)",
    )

    # create_report / create_summary as the lower-level, explicit-summary alternative
    manual_summary = create_summary(total_checks=5, passed=1, failed=1, warnings=1, errors=1, skipped=1)
    manual_report = create_report(provider="Terraform", validation_summary=manual_summary, findings=combined)
    _check(manual_report.to_dict() == report.to_dict(), "create_report matches build_report for equivalent input")

    _expect_error(
        "create_report rejects a non-ValidationSummary",
        lambda: create_report(provider="Terraform", validation_summary="nope", findings=()),
    )

    return report


# ---------------------------------------------------------------------------
# add_finding: controlled combination onto an existing report
# ---------------------------------------------------------------------------
def test_add_finding(report: ValidationReport) -> None:
    """`add_finding` returns a new, updated report without mutating the original."""
    original_finding_count = len(report.findings)
    original_failed_count = report.validation_summary.failed

    new_finding = create_finding(
        tool="checkov", provider="Terraform", status="FAILED", severity="CRITICAL", message="new failure",
    )
    updated_report = add_finding(report, new_finding)

    _check(len(updated_report.findings) == original_finding_count + 1, "add_finding appends exactly one finding")
    _check(
        updated_report.validation_summary.failed == original_failed_count + 1,
        "add_finding recalculates the summary by default",
    )
    _check(len(report.findings) == original_finding_count, "add_finding does not mutate the original report")

    updated_no_recalc = add_finding(report, new_finding, recalculate_summary=False)
    _check(
        updated_no_recalc.validation_summary.to_dict() == report.validation_summary.to_dict(),
        "add_finding(recalculate_summary=False) keeps the original summary",
    )

    _expect_error("add_finding rejects a non-ValidationReport", lambda: add_finding("nope", new_finding))
    _expect_error("add_finding rejects a non-ValidationFinding", lambda: add_finding(report, "nope"))


# ---------------------------------------------------------------------------
# 6 & 7. Serialization to / deserialization from dictionary
# ---------------------------------------------------------------------------
def test_serialization_round_trip(report: ValidationReport) -> None:
    """Every schema object round-trips through dict serialization unchanged."""
    finding = report.findings[0]

    finding_dict = finding_to_dict(finding)
    _check(finding_from_dict(finding_dict) == finding, "ValidationFinding round-trips through dict")

    summary_dict = summary_to_dict(report.validation_summary)
    _check(
        summary_from_dict(summary_dict).to_dict() == report.validation_summary.to_dict(),
        "ValidationSummary round-trips through dict",
    )

    report_dict = report_to_dict(report)
    _check(report_from_dict(report_dict).to_dict() == report.to_dict(), "ValidationReport round-trips through dict")

    import json

    _check(json.dumps(report_dict) is not None, "report_to_dict output is JSON-serializable")

    _expect_error("finding_to_dict rejects a non-ValidationFinding", lambda: finding_to_dict("nope"))
    _expect_error("report_to_dict rejects a non-ValidationReport", lambda: report_to_dict("nope"))
    _expect_error("summary_to_dict rejects a non-ValidationSummary", lambda: summary_to_dict("nope"))


# ---------------------------------------------------------------------------
# 8. Empty findings/report handling
# ---------------------------------------------------------------------------
def test_empty_findings_and_report() -> None:
    """Empty inputs are handled cleanly, without errors, at every entry point."""
    empty_combined = combine_findings()
    _check(empty_combined == (), "combine_findings() with no groups returns an empty tuple")

    empty_summary = summary_from_findings([])
    _check(
        empty_summary.to_dict() == {"total_checks": 0, "passed": 0, "failed": 0, "warnings": 0, "errors": 0, "skipped": 0},
        "summary_from_findings([]) produces an all-zero summary",
    )

    empty_report = build_report(provider="Terraform", findings=[])
    _check(len(empty_report.findings) == 0, "build_report with no findings produces an empty report")
    _check(
        empty_report.validation_summary.total_checks == 0,
        "empty report's summary.total_checks is 0",
    )

    empty_report_dict = report_to_dict(empty_report)
    _check(empty_report_dict["findings"] == [], "empty report serializes findings as an empty list")
    _check(
        report_from_dict(empty_report_dict).to_dict() == empty_report.to_dict(),
        "empty report round-trips through dict",
    )


# ---------------------------------------------------------------------------
# 9. Invalid input handling
# ---------------------------------------------------------------------------
def test_invalid_input_is_rejected_as_validation_result_error() -> None:
    """Invalid input at every entry point raises ValidationResultError, never a raw schema error."""
    _expect_error(
        "create_finding rejects an empty tool",
        lambda: create_finding(tool="", provider="Terraform", status="PASSED", severity="NONE", message="x"),
    )
    _expect_error(
        "create_finding rejects an invalid status string",
        lambda: create_finding(
            tool="checkov", provider="Terraform", status="NOT_A_STATUS", severity="NONE", message="x"
        ),
    )
    _expect_error(
        "create_finding rejects line=0 (must be positive)",
        lambda: create_finding(
            tool="checkov", provider="Terraform", status="PASSED", severity="NONE", message="x", line=0
        ),
    )
    _expect_error(
        "create_summary rejects a negative count",
        lambda: create_summary(failed=-1),
    )
    _expect_error(
        "finding_from_dict rejects a non-dict",
        lambda: finding_from_dict("not a dict"),
    )
    _expect_error(
        "report_from_dict rejects missing required fields",
        lambda: report_from_dict({"provider": "Terraform"}),
    )


# ---------------------------------------------------------------------------
# 10. Confirm schema validation is reused, not duplicated
# ---------------------------------------------------------------------------
def test_schema_validation_is_reused_not_duplicated() -> None:
    """The same field-level rule enforced by ValidationFinding is enforced identically here.

    This does not re-derive or restate the rule (e.g. "line must be
    >= 1") independently — it constructs a `ValidationFinding` directly
    and via `create_finding()` with the same invalid input and checks
    that both paths reject it for the same underlying reason, proving
    `validation_result` adds no parallel validation logic of its own.
    """
    direct_error = None
    try:
        ValidationFinding(
            tool="checkov", provider="Terraform", status=ValidationStatus.PASSED,
            severity=ValidationSeverity.NONE, message="x", line=0,
        )
    except Exception as exc:  # noqa: BLE001 - capturing the schema's own exception type
        direct_error = exc

    wrapped_error = None
    try:
        create_finding(tool="checkov", provider="Terraform", status="PASSED", severity="NONE", message="x", line=0)
    except ValidationResultError as exc:
        wrapped_error = exc

    _check(direct_error is not None, "ValidationFinding itself rejects line=0")
    _check(wrapped_error is not None, "create_finding also rejects line=0")
    _check(
        direct_error is not None and wrapped_error is not None and str(direct_error) == str(wrapped_error),
        "create_finding's error message is identical to ValidationFinding's own (proves no re-implementation)",
    )


def run_all_tests() -> int:
    """Run every test function in this module and print a final summary.

    Returns:
        `0` if every check passed, `1` otherwise (suitable as a process
        exit code).
    """
    test_create_valid_finding()
    combined = test_create_and_combine_multiple_findings()
    test_summary_from_findings_counts_each_status(combined)
    report = test_build_complete_report(combined)
    test_add_finding(report)
    test_serialization_round_trip(report)
    test_empty_findings_and_report()
    test_invalid_input_is_rejected_as_validation_result_error()
    test_schema_validation_is_reused_not_duplicated()

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED:")
        for description in _FAILURES:
            print(f"  - {description}")
        return 1

    print("All checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
