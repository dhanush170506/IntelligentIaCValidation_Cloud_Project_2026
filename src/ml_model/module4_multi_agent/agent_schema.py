"""agent_schema.py.

Defines the standardized, agent- and module-independent finding schema
for Module 4 (the Intelligent Multi-Agent Framework).

Module 4's future Coordinator Agent and specialized agents (syntax
validation, security validation, deployment validation, drift
detection, cost analysis, evidence collection) each analyze different
inputs from Modules 1-3 (parsed IaC, the Unified Intermediate
Representation, the resource/dependency graphs, and Module 3's
`ValidationReport`s) using entirely different logic. This module
defines the single internal representation every one of those agents'
individual observations must be expressed as, so later stages of the
pipeline (the Coordinator Agent, evidence collection, reporting) never
need to know which specific agent produced a given finding in order to
interpret it.

One type is provided here:
    - `AgentFinding`: one individual observation made by one agent,
      optionally against one resource.

(See `agent_result.py` for `AgentResult`, which represents the
complete output of one agent's execution and is built from zero or
more `AgentFinding`s.)

`AgentType`, `AgentStatus`, and `AgentSeverity` are enumerations rather
than free-form strings, so every current and future agent is
constrained to the same fixed vocabulary.

This module intentionally mirrors the structure and validation style
of Module 3's `validation_schema.py` (frozen, keyword-only dataclasses;
field-level validation in `__post_init__`; `to_dict()`/`from_dict()`),
but defines its own independent types. Module 4 does not import or
extend Module 3's schema: an `AgentFinding` (one agent's observation)
and a `ValidationFinding` (one static-analysis tool's check result)
are conceptually distinct, even though a security-validation agent may
well read `ValidationFinding`s as one of its inputs.

Requirements:
    - Python 3.12

Typical usage:
    from agent_schema import AgentFinding, AgentSeverity, AgentType

    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Security group allows unrestricted ingress",
        resource_id="aws_security_group.web_sg",
        rule_id="CKV_AWS_24",
        evidence_ids=("evidence-001",),
        confidence=0.92,
    )

    finding.to_dict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Type, TypeVar

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
class AgentSchemaError(Exception):
    """Raised when a Module 4 agent schema object cannot be created from invalid data."""


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
class AgentType(str, Enum):
    """Which Module 4 agent produced a given finding/result.

    Subclasses `str` so a member serializes directly as its plain
    string value (e.g. `"SECURITY_VALIDATION"`) wherever a `str` is
    expected, without needing an explicit `.value` access.
    """

    COORDINATOR = "COORDINATOR"
    SYNTAX_VALIDATION = "SYNTAX_VALIDATION"
    SECURITY_VALIDATION = "SECURITY_VALIDATION"
    DEPLOYMENT_VALIDATION = "DEPLOYMENT_VALIDATION"
    DRIFT_DETECTION = "DRIFT_DETECTION"
    COST_ANALYSIS = "COST_ANALYSIS"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"


class AgentStatus(str, Enum):
    """The lifecycle outcome of a single agent execution.

    Subclasses `str` for the same reason as `AgentType`.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentSeverity(str, Enum):
    """The severity of a single agent finding.

    Subclasses `str` for the same reason as `AgentType`.
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

    This helper (and the other module-level validators below) is
    intentionally not underscore-hidden from the rest of the
    `module4_multi_agent` package: `agent_result.py` imports it
    directly rather than re-implementing the same coercion/validation
    logic, so a field shared between `AgentFinding` and `AgentResult`
    (e.g. `confidence`, `evidence_ids`) is only ever validated in one
    place.

    Args:
        value: The value to coerce.
        enum_cls: The enum class `value` should become a member of.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Returns:
        The corresponding member of `enum_cls`.

    Raises:
        AgentSchemaError: If `value` is not already a member of
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
        "Agent schema error: field '%s' must be one of [%s], got %r",
        field_name,
        valid_values,
        value,
    )
    raise AgentSchemaError(f"Field '{field_name}' must be one of [{valid_values}], got {value!r}")


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
        AgentSchemaError: If `value` is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        logger.error(
            "Agent schema error: field '%s' must be a non-empty string, got %r",
            field_name,
            value,
        )
        raise AgentSchemaError(f"Field '{field_name}' must be a non-empty string, got {value!r}")


def _validate_optional_string(value: Any, field_name: str) -> None:
    """Validate that an optional field's value, if present, is a non-empty string.

    Args:
        value: The value to validate. `None` is accepted and considered
            valid (the field is simply absent).
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        AgentSchemaError: If `value` is neither `None` nor a non-empty
            `str`.
    """
    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        logger.error(
            "Agent schema error: field '%s' must be a non-empty string or None, got %r",
            field_name,
            value,
        )
        raise AgentSchemaError(
            f"Field '{field_name}' must be a non-empty string or None, got {value!r}"
        )


def _validate_confidence(value: Any, field_name: str) -> float:
    """Validate and normalize a confidence score.

    Args:
        value: The value to validate. Accepted as an `int` or `float`
            (but not `bool`, which is technically an `int` subclass in
            Python but is never a meaningful confidence score) in the
            inclusive range `[0.0, 1.0]`.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Returns:
        `value` normalized to a `float`.

    Raises:
        AgentSchemaError: If `value` is not an `int`/`float` in
            `[0.0, 1.0]`.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0.0 <= float(value) <= 1.0):
        logger.error(
            "Agent schema error: field '%s' must be a number between 0.0 and 1.0, got %r",
            field_name,
            value,
        )
        raise AgentSchemaError(
            f"Field '{field_name}' must be a number between 0.0 and 1.0, got {value!r}"
        )
    return float(value)


def _validate_evidence_ids(value: Any, field_name: str) -> Tuple[str, ...]:
    """Validate and normalize a collection of evidence IDs.

    Args:
        value: The value to validate. Must be an iterable of non-empty
            strings (a bare `str`/`bytes` is explicitly rejected, since
            iterating one yields individual characters/bytes rather
            than the intended collection of IDs).
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Returns:
        `value` normalized to a `tuple` of strings, in original order.

    Raises:
        AgentSchemaError: If `value` is not iterable, is a bare
            `str`/`bytes`, or contains any element that is not a
            non-empty string.
    """
    if isinstance(value, (str, bytes)):
        logger.error(
            "Agent schema error: field '%s' must be an iterable of ID strings, not a "
            "single string, got %r",
            field_name,
            value,
        )
        raise AgentSchemaError(
            f"Field '{field_name}' must be an iterable of ID strings, not a single "
            f"string, got {value!r}"
        )

    try:
        items = list(value)
    except TypeError as exc:
        logger.error(
            "Agent schema error: field '%s' must be an iterable of ID strings, got %r",
            field_name,
            value,
        )
        raise AgentSchemaError(
            f"Field '{field_name}' must be an iterable of ID strings, got {value!r}"
        ) from exc

    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            logger.error(
                "Agent schema error: field '%s[%d]' must be a non-empty string, got %r",
                field_name,
                index,
                item,
            )
            raise AgentSchemaError(
                f"Field '{field_name}[{index}]' must be a non-empty string, got {item!r}"
            )

    return tuple(items)


# ---------------------------------------------------------------------------
# Schema field-name constants, declared once so they are never repeated
# as literal strings elsewhere in this module.
# ---------------------------------------------------------------------------
_FINDING_REQUIRED_FIELDS = ("agent_type", "severity", "message", "confidence")
_FINDING_OPTIONAL_FIELDS = ("resource_id", "rule_id", "evidence_ids")


# ---------------------------------------------------------------------------
# AgentFinding
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class AgentFinding:
    """One individual observation made by one Module 4 agent.

    Every current and future Module 4 agent must express its
    observations as instances of this single type, so later stages of
    the pipeline never need to know which specific agent produced a
    given finding in order to interpret it.

    Attributes:
        agent_type: Which agent produced this finding.
        severity: The severity of this finding.
        message: A human-readable description of the finding.
        resource_id: The UIR resource id this finding applies to, if
            the finding can be attributed to a specific resource.
        rule_id: The agent-specific rule/check identifier that
            produced this finding, if applicable.
        evidence_ids: The IDs of any supporting evidence this finding
            is based on (e.g. IDs produced by a future evidence
            collection agent). Defaults to an empty tuple when a
            finding has no associated evidence.
        confidence: This agent's confidence in this finding, in the
            inclusive range `[0.0, 1.0]`.
    """

    agent_type: AgentType
    severity: AgentSeverity
    message: str
    confidence: float
    resource_id: Optional[str] = None
    rule_id: Optional[str] = None
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate and normalize all fields immediately after construction.

        Raises:
            AgentSchemaError: If `agent_type` or `severity` cannot be
                coerced into their respective enums; if `message` is
                not a non-empty string; if `confidence` is not a
                number in `[0.0, 1.0]`; if `resource_id` or `rule_id`
                is present but not a non-empty string; or if
                `evidence_ids` is not an iterable of non-empty
                strings.
        """
        # `agent_type` and `severity` are coerced (string -> enum)
        # rather than only validated, so callers may pass either an
        # enum member or a plain string. `object.__setattr__` is
        # required since this dataclass is frozen.
        object.__setattr__(self, "agent_type", _coerce_enum(self.agent_type, AgentType, "agent_type"))
        object.__setattr__(self, "severity", _coerce_enum(self.severity, AgentSeverity, "severity"))

        _validate_non_empty_string(self.message, "message")
        object.__setattr__(self, "confidence", _validate_confidence(self.confidence, "confidence"))

        _validate_optional_string(self.resource_id, "resource_id")
        _validate_optional_string(self.rule_id, "rule_id")

        object.__setattr__(
            self, "evidence_ids", _validate_evidence_ids(self.evidence_ids, "evidence_ids")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert this `AgentFinding` into a plain dictionary.

        Returns:
            A dictionary with the keys `agent_type`, `severity`,
            `message`, `resource_id`, `rule_id`, `evidence_ids`, and
            `confidence`. `agent_type` and `severity` are serialized as
            their plain string values, and `evidence_ids` is
            serialized as a `list`.
        """
        return {
            "agent_type": self.agent_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "resource_id": self.resource_id,
            "rule_id": self.rule_id,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentFinding":
        """Create an `AgentFinding` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the required keys
                `agent_type`, `severity`, `message`, and `confidence`.
                The optional keys `resource_id`, `rule_id`, and
                `evidence_ids` default to `None`/`()` when absent.

        Returns:
            A new, validated `AgentFinding`.

        Raises:
            AgentSchemaError: If `data` is not a dict, is missing any
                required key, or contains a value that fails field
                validation (see `__post_init__`).
        """
        if not isinstance(data, dict):
            logger.error(
                "AgentFinding creation failed: expected a dict, got %s", type(data).__name__
            )
            raise AgentSchemaError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [
            field_name for field_name in _FINDING_REQUIRED_FIELDS if field_name not in data
        ]
        if missing_fields:
            logger.error("AgentFinding creation failed: missing required fields: %s", missing_fields)
            raise AgentSchemaError(f"Missing required fields: {missing_fields}")

        return cls(
            agent_type=data["agent_type"],
            severity=data["severity"],
            message=data["message"],
            confidence=data["confidence"],
            resource_id=data.get("resource_id"),
            rule_id=data.get("rule_id"),
            evidence_ids=tuple(data.get("evidence_ids", ())),
        )


__all__ = [
    "AgentSchemaError",
    "AgentType",
    "AgentStatus",
    "AgentSeverity",
    "AgentFinding",
]
