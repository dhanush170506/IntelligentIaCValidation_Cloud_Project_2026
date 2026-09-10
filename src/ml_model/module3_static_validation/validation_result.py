"""validation_result.py.

A safe utility/factory layer built on top of `validation_schema.py`.

Every external validation tool (Terraform Validate, Checkov, TFLint,
CFN-Lint) will eventually have its own adapter that translates that
tool's native output into `ValidationFinding` objects. This module is
the clean, provider-independent interface those adapters — and
whatever assembles their results into a `ValidationReport` — are
expected to go through, rather than constructing and combining schema
objects by hand:

    Terraform adapter --\\
    Checkov adapter    ---+--> ValidationFinding(s) -> validation_result.py -> ValidationReport
    TFLint adapter     --/
    CFN-Lint adapter  -/

This module defines no new fields and duplicates none of
`validation_schema.py`'s field-level validation logic. Every function
here either constructs a schema object by delegating directly to its
constructor (`ValidationFinding`, `ValidationSummary`,
`ValidationReport`) or operates on already-constructed schema objects
(combining, summarizing, serializing). Any `ValidationSchemaError`
raised by the underlying schema is caught and re-raised as
`ValidationResultError`, so callers of this module only ever need to
handle one exception type — matching the same wrapping pattern already
used by `graph_builder.GraphBuilder` in Module 2.

This module is deliberately unaware of any external tool's native
output format (JSON reports, SARIF, plain text, exit codes, etc.) —
that translation is each future tool adapter's own responsibility.

Requirements:
    - Python 3.12

Typical usage:
    from validation_result import build_report, create_finding

    finding = create_finding(
        tool="checkov",
        provider="Terraform",
        status="FAILED",
        severity="HIGH",
        message="Security group allows unrestricted ingress",
        rule_id="CKV_AWS_24",
        resource_id="aws_security_group.web_sg",
    )

    report = build_report(provider="Terraform", findings=[finding])
    report.to_dict()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Tuple, Union

# Relative imports are used since this module lives inside the
# `module3_static_validation` package alongside `validation_schema.py`.
# A fallback to absolute (flat) imports is provided so this module also
# runs correctly when executed or imported directly without package
# context (e.g. `python validation_result.py`, or alongside Module 1/2's
# sibling-style flat imports), where Python has no enclosing package
# for relative imports to resolve against.
try:
    from .validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSchemaError,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )
except ImportError:
    from validation_schema import (  # type: ignore[no-redef]
        ValidationFinding,
        ValidationReport,
        ValidationSchemaError,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

if not logger.handlers:
    # Configure a default handler only if the module is used standalone
    # (i.e. the host application hasn't already configured logging).
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class ValidationResultError(Exception):
    """Raised when this utility layer cannot build or combine a validation result.

    Every failure this module can encounter — a `ValidationSchemaError`
    raised by the underlying schema classes, or a type mismatch this
    layer itself detects while combining already-constructed objects —
    is normalized into this single exception type, so callers of
    `validation_result` only ever need to handle one error, matching
    the same wrapping pattern already used by
    `graph_builder.GraphBuilderError` in Module 2.
    """


# Status -> ValidationSummary field name. Used by `summary_from_findings`
# to count findings by status. Deliberately exhaustive over every
# `ValidationStatus` member; a status added to the schema without a
# corresponding update here would surface as a clear
# `ValidationResultError` (via `_require_type`'s caller) rather than a
# silent miscount.
_STATUS_TO_SUMMARY_FIELD: Dict[ValidationStatus, str] = {
    ValidationStatus.PASSED: "passed",
    ValidationStatus.FAILED: "failed",
    ValidationStatus.WARNING: "warnings",
    ValidationStatus.ERROR: "errors",
    ValidationStatus.SKIPPED: "skipped",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _require_type(value: Any, expected_type: type, label: str) -> None:
    """Validate that a value is an instance of an expected type.

    Args:
        value: The value to check.
        expected_type: The type `value` is required to be an instance
            of.
        label: A short description of what `value` represents, used in
            the error message and log entry.

    Raises:
        ValidationResultError: If `value` is not an instance of
            `expected_type`.
    """
    if not isinstance(value, expected_type):
        logger.error(
            "%s must be a %s, got %s", label, expected_type.__name__, type(value).__name__
        )
        raise ValidationResultError(
            f"{label} must be a {expected_type.__name__}, got {type(value).__name__}"
        )


def _call_schema(factory, *args: Any, **kwargs: Any) -> Any:
    """Call a `validation_schema` constructor/factory, normalizing its errors.

    Args:
        factory: The callable to invoke (e.g. `ValidationFinding`,
            `ValidationReport.from_dict`).
        *args: Positional arguments to pass to `factory`.
        **kwargs: Keyword arguments to pass to `factory`.

    Returns:
        Whatever `factory` returns.

    Raises:
        ValidationResultError: If `factory` raises a
            `ValidationSchemaError`. The original exception is
            preserved as this exception's `__cause__`.
    """
    try:
        return factory(*args, **kwargs)
    except ValidationSchemaError as exc:
        logger.error("Validation schema rejected input: %s", exc)
        raise ValidationResultError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Creation helpers
# ---------------------------------------------------------------------------
def create_finding(
    *,
    tool: str,
    provider: str,
    status: Union[ValidationStatus, str],
    severity: Union[ValidationSeverity, str],
    message: str,
    rule_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
    column: Optional[int] = None,
) -> ValidationFinding:
    """Create a single `ValidationFinding`.

    A thin, keyword-only factory over `ValidationFinding`'s own
    constructor. All field-level validation (non-empty strings, status/
    severity coercion, positive `line`/`column`) is performed by
    `ValidationFinding` itself; this function adds no validation logic
    of its own.

    Args:
        tool: The name of the tool that produced this finding.
        provider: The IaC provider the finding applies to.
        status: The outcome of the check (`ValidationStatus` member or
            matching string, case-insensitive).
        severity: The severity of the finding (`ValidationSeverity`
            member or matching string, case-insensitive).
        message: A human-readable description of the finding.
        rule_id: The tool-specific rule/check identifier, if
            applicable.
        resource_id: The UIR resource id this finding applies to, if
            known.
        file_path: The source file the finding applies to, if known.
        line: The 1-based line number the finding applies to, if known.
        column: The 1-based column number the finding applies to, if
            known.

    Returns:
        A new, validated `ValidationFinding`.

    Raises:
        ValidationResultError: If any field fails `ValidationFinding`'s
            own validation.
    """
    return _call_schema(
        ValidationFinding,
        tool=tool,
        provider=provider,
        status=status,
        severity=severity,
        message=message,
        rule_id=rule_id,
        resource_id=resource_id,
        file_path=file_path,
        line=line,
        column=column,
    )


def create_summary(
    *,
    total_checks: int = 0,
    passed: int = 0,
    failed: int = 0,
    warnings: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> ValidationSummary:
    """Create a `ValidationSummary` from explicit counts.

    A thin factory over `ValidationSummary`'s own constructor. Prefer
    `summary_from_findings()` when a summary should reflect an actual
    set of findings rather than externally-supplied counts.

    Args:
        total_checks: The total number of checks that were run.
        passed: The number of checks that passed.
        failed: The number of checks that failed.
        warnings: The number of checks that produced a warning.
        errors: The number of checks that could not be completed due to
            an error.
        skipped: The number of checks that were skipped.

    Returns:
        A new, validated `ValidationSummary`.

    Raises:
        ValidationResultError: If any count fails `ValidationSummary`'s
            own validation (not a non-negative integer).
    """
    return _call_schema(
        ValidationSummary,
        total_checks=total_checks,
        passed=passed,
        failed=failed,
        warnings=warnings,
        errors=errors,
        skipped=skipped,
    )


def create_report(
    *,
    provider: str,
    validation_summary: ValidationSummary,
    findings: Iterable[ValidationFinding] = (),
) -> ValidationReport:
    """Create a `ValidationReport` from an already-computed summary.

    A thin factory over `ValidationReport`'s own constructor. Prefer
    `build_report()` when the summary should be computed automatically
    from `findings` rather than supplied separately.

    Args:
        provider: The IaC provider this report applies to.
        validation_summary: The summary to attach to the report.
        findings: The findings the report contains.

    Returns:
        A new, validated `ValidationReport`.

    Raises:
        ValidationResultError: If `provider` is empty, if
            `validation_summary` is not a `ValidationSummary`, or if any
            element of `findings` is not a `ValidationFinding`.
    """
    return _call_schema(
        ValidationReport,
        provider=provider,
        validation_summary=validation_summary,
        findings=tuple(findings),
    )


# ---------------------------------------------------------------------------
# Combination helpers
# ---------------------------------------------------------------------------
def combine_findings(*finding_groups: Iterable[ValidationFinding]) -> Tuple[ValidationFinding, ...]:
    """Combine findings from one or more sources into a single ordered tuple.

    Intended for merging the `ValidationFinding` output of several tool
    adapters (e.g. Checkov and TFLint findings for the same Terraform
    run) before building one combined report. Order is preserved:
    groups are concatenated in the order given, and findings within
    each group keep their original order.

    Args:
        *finding_groups: Any number of iterables of `ValidationFinding`.
            An adapter's own output list can be passed directly.

    Returns:
        A single tuple containing every finding from every group, in
        order.

    Raises:
        ValidationResultError: If any group is not iterable, or if any
            element within a group is not a `ValidationFinding`.
    """
    combined: list[ValidationFinding] = []

    for group_index, group in enumerate(finding_groups):
        try:
            items = list(group)
        except TypeError as exc:
            logger.error("combine_findings: group at index %d is not iterable: %r", group_index, group)
            raise ValidationResultError(
                f"Group at index {group_index} is not iterable: {group!r}"
            ) from exc

        for item_index, finding in enumerate(items):
            _require_type(finding, ValidationFinding, f"Item at group {group_index}, index {item_index}")
            combined.append(finding)

    logger.info(
        "Combined %d finding group(s) into %d finding(s).", len(finding_groups), len(combined)
    )
    return tuple(combined)


def add_finding(
    report: ValidationReport, finding: ValidationFinding, *, recalculate_summary: bool = True
) -> ValidationReport:
    """Return a new `ValidationReport` with one additional finding appended.

    `ValidationReport` is immutable, so this does not modify `report`
    in place — it returns a new instance. By default, the returned
    report's summary is recomputed from the full, updated set of
    findings via `summary_from_findings()`; pass
    `recalculate_summary=False` to keep the original report's summary
    unchanged instead.

    Args:
        report: The existing `ValidationReport` to extend.
        finding: The `ValidationFinding` to append.
        recalculate_summary: Whether to recompute the summary from the
            updated findings. Defaults to `True`.

    Returns:
        A new `ValidationReport` containing every finding from `report`
        plus `finding`.

    Raises:
        ValidationResultError: If `report` is not a `ValidationReport`,
            or `finding` is not a `ValidationFinding`.
    """
    _require_type(report, ValidationReport, "report")
    _require_type(finding, ValidationFinding, "finding")

    updated_findings = report.findings + (finding,)
    summary = summary_from_findings(updated_findings) if recalculate_summary else report.validation_summary

    return create_report(provider=report.provider, validation_summary=summary, findings=updated_findings)


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------
def summary_from_findings(findings: Iterable[ValidationFinding]) -> ValidationSummary:
    """Compute a `ValidationSummary` by counting findings' statuses.

    Counts `PASSED`/`FAILED`/`WARNING`/`ERROR`/`SKIPPED` occurrences
    across `findings` and sets `total_checks` to the total number of
    findings given. Severity is deliberately not counted —
    `ValidationSummary` has no severity-based fields, and introducing
    severity-based counting is out of scope for this layer.

    Because `total_checks` is simply `len(findings)`, a summary
    produced by this function will always satisfy
    `total_checks == passed + failed + warnings + errors + skipped`.
    This relationship is a natural consequence of counting findings
    here — it is not, and must not be, enforced inside
    `validation_schema.ValidationSummary` itself, since summaries
    built some other way (e.g. supplied directly by an external tool)
    may not satisfy it.

    Args:
        findings: The findings to count.

    Returns:
        A new `ValidationSummary` reflecting the given findings.

    Raises:
        ValidationResultError: If any element of `findings` is not a
            `ValidationFinding`.
    """
    counts = {field_name: 0 for field_name in _STATUS_TO_SUMMARY_FIELD.values()}
    total = 0

    for index, finding in enumerate(findings):
        _require_type(finding, ValidationFinding, f"Item at index {index}")
        total += 1
        counts[_STATUS_TO_SUMMARY_FIELD[finding.status]] += 1

    logger.info("Computed summary from %d finding(s): %s", total, counts)
    return create_summary(total_checks=total, **counts)


def build_report(provider: str, findings: Iterable[ValidationFinding]) -> ValidationReport:
    """Build a complete `ValidationReport`, computing its summary automatically.

    Convenience combination of `summary_from_findings()` and
    `create_report()`: the common case for a tool adapter (or whatever
    assembles several adapters' output) that has a set of findings and
    wants a complete, internally-consistent report in one call.

    Args:
        provider: The IaC provider this report applies to.
        findings: The findings to include in the report. The summary is
            computed from this same collection.

    Returns:
        A new `ValidationReport` whose `validation_summary` reflects
        exactly the findings it contains.

    Raises:
        ValidationResultError: If `provider` is empty, or if any
            element of `findings` is not a `ValidationFinding`.
    """
    finding_tuple = combine_findings(findings)
    summary = summary_from_findings(finding_tuple)
    return create_report(provider=provider, validation_summary=summary, findings=finding_tuple)


# ---------------------------------------------------------------------------
# Serialization / deserialization
# ---------------------------------------------------------------------------
def finding_to_dict(finding: ValidationFinding) -> Dict[str, Any]:
    """Serialize a `ValidationFinding` to a plain dictionary.

    Args:
        finding: The finding to serialize.

    Returns:
        `finding.to_dict()`.

    Raises:
        ValidationResultError: If `finding` is not a `ValidationFinding`.
    """
    _require_type(finding, ValidationFinding, "finding")
    return finding.to_dict()


def finding_from_dict(data: Dict[str, Any]) -> ValidationFinding:
    """Deserialize a `ValidationFinding` from a plain dictionary.

    Args:
        data: The dictionary to deserialize.

    Returns:
        A new, validated `ValidationFinding`.

    Raises:
        ValidationResultError: If `data` fails `ValidationFinding`'s own
            validation.
    """
    return _call_schema(ValidationFinding.from_dict, data)


def summary_to_dict(summary: ValidationSummary) -> Dict[str, int]:
    """Serialize a `ValidationSummary` to a plain dictionary.

    Args:
        summary: The summary to serialize.

    Returns:
        `summary.to_dict()`.

    Raises:
        ValidationResultError: If `summary` is not a `ValidationSummary`.
    """
    _require_type(summary, ValidationSummary, "summary")
    return summary.to_dict()


def summary_from_dict(data: Dict[str, Any]) -> ValidationSummary:
    """Deserialize a `ValidationSummary` from a plain dictionary.

    Args:
        data: The dictionary to deserialize.

    Returns:
        A new, validated `ValidationSummary`.

    Raises:
        ValidationResultError: If `data` fails `ValidationSummary`'s own
            validation.
    """
    return _call_schema(ValidationSummary.from_dict, data)


def report_to_dict(report: ValidationReport) -> Dict[str, Any]:
    """Serialize a `ValidationReport` to a plain dictionary.

    Args:
        report: The report to serialize.

    Returns:
        `report.to_dict()`.

    Raises:
        ValidationResultError: If `report` is not a `ValidationReport`.
    """
    _require_type(report, ValidationReport, "report")
    return report.to_dict()


def report_from_dict(data: Dict[str, Any]) -> ValidationReport:
    """Deserialize a `ValidationReport` from a plain dictionary.

    Args:
        data: The dictionary to deserialize.

    Returns:
        A new, validated `ValidationReport`.

    Raises:
        ValidationResultError: If `data` fails `ValidationReport`'s own
            validation.
    """
    return _call_schema(ValidationReport.from_dict, data)


__all__ = [
    "ValidationResultError",
    "create_finding",
    "create_summary",
    "create_report",
    "combine_findings",
    "add_finding",
    "summary_from_findings",
    "build_report",
    "finding_to_dict",
    "finding_from_dict",
    "summary_to_dict",
    "summary_from_dict",
    "report_to_dict",
    "report_from_dict",
]
