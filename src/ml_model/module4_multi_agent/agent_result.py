"""agent_result.py.

Represents the complete output of a single Module 4 agent execution.

Every future Module 4 agent — the Coordinator Agent as well as each
specialized agent (syntax validation, security validation, deployment
validation, drift detection, cost analysis, evidence collection) —
produces exactly one `AgentResult` per execution. This module defines
that single internal representation, built from zero or more
`AgentFinding`s (see `agent_schema.py`), so later stages of the
pipeline (the Coordinator Agent's own aggregation logic, evidence
collection, reporting) never need to know which specific agent
produced a given result in order to interpret it.

This module defines no new finding-level fields and duplicates none of
`agent_schema.py`'s field-level validation logic: `confidence` range
checking, `evidence_ids` validation, and `agent_type`/enum coercion are
each implemented exactly once, in `agent_schema.py`, and imported here
directly. The one exception is `findings` itself, which — exactly like
Module 3's `validation_schema.ValidationReport` does for
`ValidationFinding` — is validated only at the "is each element
actually an `AgentFinding`" level; each finding's own fields were
already validated when that `AgentFinding` was constructed, so
`AgentResult` does not re-validate them.

Requirements:
    - Python 3.12

Typical usage:
    from agent_result import AgentResult
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType

    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Security group allows unrestricted ingress",
        confidence=0.92,
    )

    result = AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.COMPLETED,
        findings=(finding,),
        confidence=0.92,
        message="Security validation completed with 1 finding.",
    )

    result.to_dict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# Relative imports are used since this module lives inside the
# `module4_multi_agent` package alongside `agent_schema.py`. A fallback
# to absolute (flat) imports is provided so this module also runs
# correctly when executed or imported directly without package
# context, matching the same pattern used throughout Module 3 (e.g.
# `validation_result.py`).
try:
    from .agent_schema import (
        AgentFinding,
        AgentSchemaError,
        AgentStatus,
        AgentType,
        _coerce_enum,
        _validate_confidence,
        _validate_evidence_ids,
        _validate_non_empty_string,
    )
except ImportError:
    from agent_schema import (  # type: ignore[no-redef]
        AgentFinding,
        AgentSchemaError,
        AgentStatus,
        AgentType,
        _coerce_enum,
        _validate_confidence,
        _validate_evidence_ids,
        _validate_non_empty_string,
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
class AgentResultError(Exception):
    """Raised when an `AgentResult` cannot be created from invalid data.

    Every failure this module can encounter — an `AgentSchemaError`
    raised by a shared `agent_schema.py` validator (e.g. an
    out-of-range `confidence`, or an invalid `evidence_ids` entry), or
    a type mismatch this class itself detects (e.g. a `findings`
    element that is not an `AgentFinding`) — is normalized into this
    single exception type.
    """


# ---------------------------------------------------------------------------
# Schema field-name constants, declared once so they are never repeated
# as literal strings elsewhere in this module.
# ---------------------------------------------------------------------------
_RESULT_REQUIRED_FIELDS = ("agent_type", "status", "message", "confidence")
_RESULT_OPTIONAL_FIELDS = ("findings", "evidence_ids", "metadata")


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class AgentResult:
    """The complete output of one Module 4 agent execution.

    Attributes:
        agent_type: Which agent produced this result.
        status: The lifecycle outcome of this execution.
        message: A human-readable summary of this execution's outcome.
        confidence: This agent's overall confidence in this result, in
            the inclusive range `[0.0, 1.0]`.
        findings: Every individual `AgentFinding` this agent produced,
            in the order they were produced. Stored as a tuple (rather
            than a list) so an `AgentResult`, like `AgentFinding`, is
            fully immutable. Defaults to an empty tuple for an
            execution that produced no findings.
        evidence_ids: The IDs of any supporting evidence this result as
            a whole is based on. Preserved in the order given. Distinct
            from, and not derived from, the `evidence_ids` of the
            individual `findings` — an agent may cite result-level
            evidence that isn't tied to any one finding.
        metadata: Optional, agent-specific auxiliary data that doesn't
            fit any other field (e.g. timing information, tool
            versions). `None` when an agent has nothing to attach.
    """

    agent_type: AgentType
    status: AgentStatus
    message: str
    confidence: float
    findings: Tuple[AgentFinding, ...] = field(default_factory=tuple)
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate and normalize all fields immediately after construction.

        Raises:
            AgentResultError: If `agent_type` or `status` cannot be
                coerced into their respective enums; if `message` is
                not a non-empty string; if `confidence` is not a
                number in `[0.0, 1.0]`; if any element of `findings` is
                not an `AgentFinding`; if `evidence_ids` is not an
                iterable of non-empty strings; or if `metadata` is
                present but not a `dict`.
        """
        try:
            # `agent_type` and `status` are coerced (string -> enum)
            # rather than only validated, so callers may pass either an
            # enum member or a plain string. `object.__setattr__` is
            # required since this dataclass is frozen.
            object.__setattr__(self, "agent_type", _coerce_enum(self.agent_type, AgentType, "agent_type"))
            object.__setattr__(self, "status", _coerce_enum(self.status, AgentStatus, "status"))

            _validate_non_empty_string(self.message, "message")
            object.__setattr__(self, "confidence", _validate_confidence(self.confidence, "confidence"))

            object.__setattr__(
                self, "evidence_ids", _validate_evidence_ids(self.evidence_ids, "evidence_ids")
            )
        except AgentSchemaError as exc:
            logger.error("AgentResult creation failed: %s", exc)
            raise AgentResultError(str(exc)) from exc

        # `findings` is validated at the "is this an AgentFinding"
        # level only; each finding's own fields were already validated
        # when that AgentFinding was constructed (see this module's
        # docstring).
        findings_tuple = tuple(self.findings)
        for index, finding in enumerate(findings_tuple):
            if not isinstance(finding, AgentFinding):
                logger.error(
                    "AgentResult creation failed: findings[%d] must be an AgentFinding, "
                    "got %s",
                    index,
                    type(finding).__name__,
                )
                raise AgentResultError(
                    f"findings[{index}] must be an AgentFinding, got {type(finding).__name__}"
                )
        object.__setattr__(self, "findings", findings_tuple)

        if self.metadata is not None and not isinstance(self.metadata, dict):
            logger.error(
                "AgentResult creation failed: field 'metadata' must be a dict or None, "
                "got %s",
                type(self.metadata).__name__,
            )
            raise AgentResultError(
                f"Field 'metadata' must be a dict or None, got {type(self.metadata).__name__}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert this `AgentResult` into a plain dictionary.

        Returns:
            A dictionary with the keys `agent_type`, `status`,
            `message`, `confidence`, `findings`, `evidence_ids`, and
            `metadata`. `agent_type` and `status` are serialized as
            their plain string values, `findings` as a list of each
            finding's own `to_dict()`, and `evidence_ids` as a list.
        """
        return {
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "message": self.message,
            "confidence": self.confidence,
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence_ids": list(self.evidence_ids),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        """Create an `AgentResult` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the required keys
                `agent_type`, `status`, `message`, and `confidence`.
                The optional keys `findings`, `evidence_ids`, and
                `metadata` default to `()`/`()`/`None` when absent.
                Each entry in `findings` may be either a nested
                dictionary or an existing `AgentFinding` instance.

        Returns:
            A new, validated `AgentResult`.

        Raises:
            AgentResultError: If `data` is not a dict, is missing any
                required key, or contains a value that fails field
                validation (see `__post_init__`, and `AgentFinding`
                validation for nested `findings` entries).
        """
        if not isinstance(data, dict):
            logger.error("AgentResult creation failed: expected a dict, got %s", type(data).__name__)
            raise AgentResultError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [
            field_name for field_name in _RESULT_REQUIRED_FIELDS if field_name not in data
        ]
        if missing_fields:
            logger.error("AgentResult creation failed: missing required fields: %s", missing_fields)
            raise AgentResultError(f"Missing required fields: {missing_fields}")

        findings_data = data.get("findings", ())
        try:
            findings = tuple(
                entry if isinstance(entry, AgentFinding) else AgentFinding.from_dict(entry)
                for entry in findings_data
            )
        except (AgentSchemaError, TypeError) as exc:
            logger.error("AgentResult creation failed: invalid 'findings' entry: %s", exc)
            raise AgentResultError(f"Invalid 'findings' entry: {exc}") from exc

        return cls(
            agent_type=data["agent_type"],
            status=data["status"],
            message=data["message"],
            confidence=data["confidence"],
            findings=findings,
            evidence_ids=tuple(data.get("evidence_ids", ())),
            metadata=data.get("metadata"),
        )


__all__ = [
    "AgentResultError",
    "AgentResult",
]
