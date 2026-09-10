"""validation_schema.py.

Defines the standardized, provider- and tool-independent validation
result schema for Module 3 (the Static Validation Engine).

Terraform Validate, Checkov, TFLint, and CFN-Lint each emit their own
native output format. This module defines the single internal
representation every one of those tools' results must be translated
into before reaching any later stage of the pipeline — the individual
tool adapters (implemented in later steps) are responsible for that
translation; this module only defines the shape they translate into
and validates that shape.

Three types are provided:
    - `ValidationFinding`: one individual check result from one tool,
      against one (optional) resource.
    - `ValidationSummary`: aggregate counts across a set of findings.
    - `ValidationReport`: a provider's full validation result — a
      summary plus the findings it was computed from.

`ValidationStatus` and `ValidationSeverity` are enumerations rather
than free-form strings, so every tool adapter is constrained to the
same fixed vocabulary regardless of what status/severity strings the
underlying tool itself uses.

Requirements:
    - Python 3.12

Typical usage:
    from validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
        ValidationSummary,
    )

    finding = ValidationFinding(
        tool="checkov",
        provider="Terraform",
        status=ValidationStatus.FAILED,
        severity=ValidationSeverity.HIGH,
        message="Security group allows unrestricted ingress",
        rule_id="CKV_AWS_24",
        resource_id="aws_security_group.web_sg",
    )

    report = ValidationReport(
        provider="Terraform",
        validation_summary=ValidationSummary(total_checks=1, failed=1),
        findings=(finding,),
    )

    report.to_dict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

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
class ValidationSchemaError(Exception):
    """Raised when a validation schema object cannot be created from invalid data."""


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
class ValidationStatus(str, Enum):
    """The outcome of a single validation check.

    Subclasses `str` so a `ValidationStatus` member serializes directly
    as its plain string value (e.g. `"PASSED"`) wherever a `str` is
    expected, without needing an explicit `.value` access.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class ValidationSeverity(str, Enum):
    """The severity of a single validation finding.

    Subclasses `str` for the same reason as `ValidationStatus`.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    NONE = "NONE"


_EnumT = TypeVar("_EnumT", bound=Enum)


def _coerce_enum(value: Any, enum_cls: Type[_EnumT], field_name: str) -> _EnumT:
    """Coerce a value into a member of the given enum class.

    Accepts an existing member of `enum_cls` unchanged, or a string
    matching one of its values (case-insensitive, surrounding
    whitespace ignored).

    Args:
        value: The value to coerce.
        enum_cls: The enum class `value` should become a member of.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Returns:
        The corresponding member of `enum_cls`.

    Raises:
        ValidationSchemaError: If `value` is not already a member of
            `enum_cls` and cannot be matched to one by string value.
    """
    if isinstance(value, enum_cls):
        return value

    if isinstance(value, str):
        try:
            return enum_cls(value.strip().upper())
        except ValueError:
            pass

    valid_values = ", ".join(member.value for member in enum_cls)
    logger.error(
        "Validation schema error: field '%s' must be one of [%s], got %r",
        field_name,
        valid_values,
        value,
    )
    raise ValidationSchemaError(
        f"Field '{field_name}' must be one of [{valid_values}], got {value!r}"
    )


# ---------------------------------------------------------------------------
# Field-level validation helpers
# ---------------------------------------------------------------------------
def _validate_non_empty_string(value: Any, field_name: str) -> None:
    """Validate that a required field's value is a non-empty string.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        ValidationSchemaError: If `value` is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        logger.error(
            "Validation schema error: field '%s' must be a non-empty string, got %r",
            field_name,
            value,
        )
        raise ValidationSchemaError(
            f"Field '{field_name}' must be a non-empty string, got {value!r}"
        )


def _validate_optional_string(value: Any, field_name: str) -> None:
    """Validate that an optional field's value, if present, is a string.

    Args:
        value: The value to validate. `None` is accepted and considered
            valid (the field is simply absent).
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        ValidationSchemaError: If `value` is neither `None` nor a
            `str`.
    """
    if value is not None and not isinstance(value, str):
        logger.error(
            "Validation schema error: field '%s' must be a string or None, got %r",
            field_name,
            value,
        )
        raise ValidationSchemaError(
            f"Field '{field_name}' must be a string or None, got {value!r}"
        )


def _validate_optional_positive_int(value: Any, field_name: str) -> None:
    """Validate that an optional field's value, if present, is a positive int.

    Used for 1-based source positions (`line`, `column`), where `0` and
    negative values are not valid positions.

    Args:
        value: The value to validate. `None` is accepted and considered
            valid (the field is simply absent).
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        ValidationSchemaError: If `value` is not `None`, and is not an
            `int` `>= 1`. `bool` is explicitly rejected even though it
            is technically an `int` subclass in Python, since a boolean
            is not a meaningful line/column number.
    """
    if value is None:
        return

    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        logger.error(
            "Validation schema error: field '%s' must be a positive integer (>= 1) or "
            "None, got %r",
            field_name,
            value,
        )
        raise ValidationSchemaError(
            f"Field '{field_name}' must be a positive integer (>= 1) or None, got {value!r}"
        )


def _validate_non_negative_int(value: Any, field_name: str) -> None:
    """Validate that a required field's value is a non-negative int.

    Used for summary counts (e.g. `total_checks`, `passed`), where `0`
    is a valid count.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        ValidationSchemaError: If `value` is not a non-negative `int`.
            `bool` is explicitly rejected even though it is technically
            an `int` subclass in Python, since a boolean is not a
            meaningful count.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        logger.error(
            "Validation schema error: field '%s' must be a non-negative integer, got %r",
            field_name,
            value,
        )
        raise ValidationSchemaError(
            f"Field '{field_name}' must be a non-negative integer, got {value!r}"
        )


# ---------------------------------------------------------------------------
# Schema field-name constants, declared once so they are never repeated
# as literal strings elsewhere in this module.
# ---------------------------------------------------------------------------
_FINDING_REQUIRED_FIELDS = ("tool", "provider", "status", "severity", "message")
_FINDING_OPTIONAL_FIELDS = ("rule_id", "resource_id", "file_path", "line", "column")

_SUMMARY_FIELDS = ("total_checks", "passed", "failed", "warnings", "errors", "skipped")

_REPORT_REQUIRED_FIELDS = ("provider", "validation_summary", "findings")


# ---------------------------------------------------------------------------
# ValidationFinding
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class ValidationFinding:
    """One individual validation check result from one tool.

    Every tool adapter (Terraform Validate, Checkov, TFLint, CFN-Lint)
    must translate its native output into instances of this single
    type, so that later stages of the pipeline never need to know
    which tool a given finding came from in order to interpret it.

    Attributes:
        tool: The name of the tool that produced this finding (e.g.
            "checkov", "tflint", "cfn-lint", "terraform_validate").
        provider: The IaC provider the finding applies to (e.g.
            "Terraform", "CloudFormation").
        status: The outcome of the check.
        severity: The severity of the finding.
        rule_id: The tool-specific rule/check identifier that produced
            this finding (e.g. "CKV_AWS_24"), if applicable.
        message: A human-readable description of the finding.
        resource_id: The UIR resource id this finding applies to, if
            the finding can be attributed to a specific resource.
        file_path: The source file the finding applies to, if known.
        line: The 1-based line number the finding applies to, if known.
        column: The 1-based column number the finding applies to, if
            known.
    """

    tool: str
    provider: str
    status: ValidationStatus
    severity: ValidationSeverity
    rule_id: Optional[str] = None
    message: str
    resource_id: Optional[str] = None
    file_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate and normalize all fields immediately after construction.

        Raises:
            ValidationSchemaError: If `tool`, `provider`, or `message`
                is not a non-empty string; if `status` or `severity`
                cannot be coerced into their respective enums; if
                `rule_id`, `resource_id`, or `file_path` is present but
                not a string; or if `line` or `column` is present but
                not a positive integer (`line` and `column` are
                1-based source positions, so `0` and negative values
                are invalid).
        """
        _validate_non_empty_string(self.tool, "tool")
        _validate_non_empty_string(self.provider, "provider")
        _validate_non_empty_string(self.message, "message")

        # `status` and `severity` are coerced (string -> enum) rather
        # than only validated, so tool adapters may pass either an enum
        # member or a plain string. `object.__setattr__` is required
        # since this dataclass is frozen.
        object.__setattr__(self, "status", _coerce_enum(self.status, ValidationStatus, "status"))
        object.__setattr__(
            self, "severity", _coerce_enum(self.severity, ValidationSeverity, "severity")
        )

        _validate_optional_string(self.rule_id, "rule_id")
        _validate_optional_string(self.resource_id, "resource_id")
        _validate_optional_string(self.file_path, "file_path")
        _validate_optional_positive_int(self.line, "line")
        _validate_optional_positive_int(self.column, "column")

    def to_dict(self) -> Dict[str, Any]:
        """Convert this `ValidationFinding` into a plain dictionary.

        Returns:
            A dictionary with the keys `tool`, `provider`, `status`,
            `severity`, `rule_id`, `message`, `resource_id`,
            `file_path`, `line`, and `column`. `status` and `severity`
            are serialized as their plain string values.
        """
        return {
            "tool": self.tool,
            "provider": self.provider,
            "status": self.status.value,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "message": self.message,
            "resource_id": self.resource_id,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationFinding":
        """Create a `ValidationFinding` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the required keys
                `tool`, `provider`, `status`, `severity`, and `message`.
                The optional keys `rule_id`, `resource_id`,
                `file_path`, `line`, and `column` default to `None`
                when absent.

        Returns:
            A new, validated `ValidationFinding`.

        Raises:
            ValidationSchemaError: If `data` is not a dict, is missing
                any required key, or contains a value that fails field
                validation (see `__post_init__`).
        """
        if not isinstance(data, dict):
            logger.error(
                "ValidationFinding creation failed: expected a dict, got %s",
                type(data).__name__,
            )
            raise ValidationSchemaError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [
            field_name for field_name in _FINDING_REQUIRED_FIELDS if field_name not in data
        ]
        if missing_fields:
            logger.error(
                "ValidationFinding creation failed: missing required fields: %s",
                missing_fields,
            )
            raise ValidationSchemaError(f"Missing required fields: {missing_fields}")

        return cls(
            tool=data["tool"],
            provider=data["provider"],
            status=data["status"],
            severity=data["severity"],
            message=data["message"],
            rule_id=data.get("rule_id"),
            resource_id=data.get("resource_id"),
            file_path=data.get("file_path"),
            line=data.get("line"),
            column=data.get("column"),
        )


# ---------------------------------------------------------------------------
# ValidationSummary
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class ValidationSummary:
    """Aggregate counts across a set of `ValidationFinding` instances.

    This is a pure data holder: it does not compute its counts from a
    list of findings itself (that is the responsibility of the future
    Validation Result Aggregator). All fields default to `0`, so an
    empty summary can be constructed with no arguments.

    Attributes:
        total_checks: The total number of checks that were run.
        passed: The number of checks that passed.
        failed: The number of checks that failed.
        warnings: The number of checks that produced a warning.
        errors: The number of checks that could not be completed due
            to an error (as distinct from a failed check).
        skipped: The number of checks that were skipped.
    """

    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    errors: int = 0
    skipped: int = 0

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction.

        Raises:
            ValidationSchemaError: If any field is not a non-negative
                integer.
        """
        for field_name in _SUMMARY_FIELDS:
            _validate_non_negative_int(getattr(self, field_name), field_name)

    def to_dict(self) -> Dict[str, int]:
        """Convert this `ValidationSummary` into a plain dictionary.

        Returns:
            A dictionary with the keys `total_checks`, `passed`,
            `failed`, `warnings`, `errors`, and `skipped`.
        """
        return {field_name: getattr(self, field_name) for field_name in _SUMMARY_FIELDS}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationSummary":
        """Create a `ValidationSummary` from a plain dictionary.

        Args:
            data: A dictionary whose keys are a subset of
                `total_checks`, `passed`, `failed`, `warnings`,
                `errors`, and `skipped`. Any key not present defaults
                to `0`.

        Returns:
            A new, validated `ValidationSummary`.

        Raises:
            ValidationSchemaError: If `data` is not a dict, or contains
                a value that fails field validation (see
                `__post_init__`).
        """
        if not isinstance(data, dict):
            logger.error(
                "ValidationSummary creation failed: expected a dict, got %s",
                type(data).__name__,
            )
            raise ValidationSchemaError(f"Expected a dict, got {type(data).__name__}")

        return cls(**{field_name: data.get(field_name, 0) for field_name in _SUMMARY_FIELDS})


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class ValidationReport:
    """A provider's complete validation result: a summary plus its findings.

    Attributes:
        provider: The IaC provider this report applies to (e.g.
            "Terraform", "CloudFormation").
        validation_summary: The aggregate counts for `findings`.
        findings: Every individual `ValidationFinding` the summary was
            computed from. Stored as a tuple (rather than a list) so a
            `ValidationReport`, like `ValidationFinding` and
            `ValidationSummary`, is fully immutable.
    """

    provider: str
    validation_summary: ValidationSummary
    findings: Tuple[ValidationFinding, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction.

        Raises:
            ValidationSchemaError: If `provider` is not a non-empty
                string, if `validation_summary` is not a
                `ValidationSummary` instance, if `findings` is not an
                iterable of `ValidationFinding` instances, or if any
                element within it is not a `ValidationFinding`.
        """
        _validate_non_empty_string(self.provider, "provider")

        if not isinstance(self.validation_summary, ValidationSummary):
            logger.error(
                "ValidationReport creation failed: field 'validation_summary' must be a "
                "ValidationSummary, got %s",
                type(self.validation_summary).__name__,
            )
            raise ValidationSchemaError(
                f"Field 'validation_summary' must be a ValidationSummary, got "
                f"{type(self.validation_summary).__name__}"
            )

        # Normalize `findings` to a tuple so a list passed positionally
        # (or via `from_dict`) is stored the same way a tuple would be.
        # `object.__setattr__` is required since this dataclass is
        # frozen.
        findings_tuple = tuple(self.findings)
        for index, finding in enumerate(findings_tuple):
            if not isinstance(finding, ValidationFinding):
                logger.error(
                    "ValidationReport creation failed: findings[%d] must be a "
                    "ValidationFinding, got %s",
                    index,
                    type(finding).__name__,
                )
                raise ValidationSchemaError(
                    f"findings[{index}] must be a ValidationFinding, got "
                    f"{type(finding).__name__}"
                )
        object.__setattr__(self, "findings", findings_tuple)

    def to_dict(self) -> Dict[str, Any]:
        """Convert this `ValidationReport` into a plain dictionary.

        Returns:
            A dictionary with the shape:
                {
                    "provider": "...",
                    "validation_summary": {...},
                    "findings": [...]
                }
        """
        return {
            "provider": self.provider,
            "validation_summary": self.validation_summary.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationReport":
        """Create a `ValidationReport` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the keys `provider`,
                `validation_summary`, and `findings`.
                `validation_summary` may be either a nested dictionary
                or an existing `ValidationSummary` instance. Each entry
                in `findings` may be either a nested dictionary or an
                existing `ValidationFinding` instance.

        Returns:
            A new, validated `ValidationReport`.

        Raises:
            ValidationSchemaError: If `data` is not a dict, is missing
                any required key, or contains a value that fails field
                validation (see `__post_init__`, and `ValidationFinding`
                / `ValidationSummary` validation for nested entries).
        """
        if not isinstance(data, dict):
            logger.error(
                "ValidationReport creation failed: expected a dict, got %s",
                type(data).__name__,
            )
            raise ValidationSchemaError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [
            field_name for field_name in _REPORT_REQUIRED_FIELDS if field_name not in data
        ]
        if missing_fields:
            logger.error(
                "ValidationReport creation failed: missing required fields: %s",
                missing_fields,
            )
            raise ValidationSchemaError(f"Missing required fields: {missing_fields}")

        summary_data = data["validation_summary"]
        if isinstance(summary_data, ValidationSummary):
            validation_summary = summary_data
        elif isinstance(summary_data, dict):
            validation_summary = ValidationSummary.from_dict(summary_data)
        else:
            logger.error(
                "ValidationReport creation failed: field 'validation_summary' must be a "
                "dict or ValidationSummary, got %s",
                type(summary_data).__name__,
            )
            raise ValidationSchemaError(
                f"Field 'validation_summary' must be a dict or ValidationSummary, got "
                f"{type(summary_data).__name__}"
            )

        findings_data = data["findings"]
        if not isinstance(findings_data, list):
            logger.error(
                "ValidationReport creation failed: field 'findings' must be a list, got %s",
                type(findings_data).__name__,
            )
            raise ValidationSchemaError(
                f"Field 'findings' must be a list, got {type(findings_data).__name__}"
            )

        findings: List[ValidationFinding] = [
            entry if isinstance(entry, ValidationFinding) else ValidationFinding.from_dict(entry)
            for entry in findings_data
        ]

        return cls(
            provider=data["provider"],
            validation_summary=validation_summary,
            findings=tuple(findings),
        )


__all__ = [
    "ValidationSchemaError",
    "ValidationStatus",
    "ValidationSeverity",
    "ValidationFinding",
    "ValidationSummary",
    "ValidationReport",
]
