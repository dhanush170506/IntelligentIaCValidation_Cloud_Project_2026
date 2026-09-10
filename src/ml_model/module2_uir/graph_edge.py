"""graph_edge.py.

Defines `GraphEdge`, the graph-ready representation of a single
dependency relationship between two infrastructure resources within
the Unified Intermediate Representation (UIR).

Where `graph_node.GraphNode` represents one resource (a graph vertex),
`GraphEdge` represents the directed relationship between exactly two
resources (a graph edge) — e.g. an EC2 instance that depends on a
security group. Later modules — the Resource Graph, the Static
Validation Engine, the Multi-Agent Framework, Runtime Drift Analysis,
and the Recommendation Engine — are expected to build directly on this
type rather than on raw dependency dictionaries. This module performs
no dependency extraction or graph construction of its own; it only
wraps an already-extracted dependency record and enforces that it
describes a valid, non-degenerate edge.

Requirements:
    - Python 3.12

Typical usage:
    from graph_edge import GraphEdge

    edge = GraphEdge.from_dict(uir["dependencies"][0])
    print(edge)
    # GraphEdge(
    #     source='aws_instance.web_server',
    #     target='aws_security_group.web_sg',
    #     relationship='depends_on'
    # )

    edge.to_dict()
    # {"source": "...", "target": "...", "relationship": "...",
    #  "provider": "..."}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

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
class GraphEdgeError(Exception):
    """Raised when a `GraphEdge` cannot be created from invalid data."""


# ---------------------------------------------------------------------------
# Required field names, declared once so they are never repeated as
# literal strings elsewhere in this module.
# ---------------------------------------------------------------------------
_FIELD_SOURCE = "source"
_FIELD_TARGET = "target"
_FIELD_RELATIONSHIP = "relationship"
_FIELD_PROVIDER = "provider"

_REQUIRED_FIELDS = (_FIELD_SOURCE, _FIELD_TARGET, _FIELD_RELATIONSHIP, _FIELD_PROVIDER)


def _validate_non_empty_string(value: Any, field_name: str) -> None:
    """Validate that a field's value is a non-empty string.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        GraphEdgeError: If `value` is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        logger.error("GraphEdge validation failed: field '%s' is invalid: %r", field_name, value)
        raise GraphEdgeError(f"Field '{field_name}' must be a non-empty string, got {value!r}")


# ---------------------------------------------------------------------------
# GraphEdge
# ---------------------------------------------------------------------------
@dataclass(frozen=True, repr=False)
class GraphEdge:
    """An immutable graph-ready representation of one resource dependency.

    A `GraphEdge` is the edge type later graph-based modules build on
    top of: the Resource Graph, the Static Validation Engine, the
    Multi-Agent Framework, Runtime Drift Analysis, and the
    Recommendation Engine. It is frozen (immutable) since an edge's
    identity should never silently change after construction — any
    transformation should produce a new `GraphEdge` rather than mutate
    an existing one.

    Attributes:
        source: The identifier of the resource holding the reference
            (matches a `GraphNode.id`).
        target: The identifier of the resource being referenced
            (matches a `GraphNode.id`).
        relationship: The kind of reference (e.g. "depends_on", "Ref",
            "Fn::GetAtt").
        provider: The IaC provider that produced the dependency (e.g.
            "Terraform", "CloudFormation").
    """

    source: str
    target: str
    relationship: str
    provider: str

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction.

        Raises:
            GraphEdgeError: If `source`, `target`, `relationship`, or
                `provider` is not a non-empty string, or if `source`
                equals `target` (a resource cannot depend on itself).
        """
        for field_name in _REQUIRED_FIELDS:
            _validate_non_empty_string(getattr(self, field_name), field_name)

        if self.source == self.target:
            logger.error(
                "GraphEdge validation failed: source and target are identical: %r",
                self.source,
            )
            raise GraphEdgeError(
                f"'{_FIELD_SOURCE}' and '{_FIELD_TARGET}' must not be identical, "
                f"got {self.source!r}"
            )

    def __hash__(self) -> int:
        """Hash a `GraphEdge` by `(source, target, relationship)`.

        `provider` is deliberately excluded: the same edge described by
        different providers (or re-derived without a known provider)
        should still be recognized as the same dependency.

        Returns:
            The hash of `(self.source, self.target, self.relationship)`.
        """
        return hash((self.source, self.target, self.relationship))

    def __repr__(self) -> str:
        """Return a readable, multi-line representation for debugging.

        Returns:
            A string of the form:
                GraphEdge(
                    source='...',
                    target='...',
                    relationship='...'
                )
        """
        return (
            "GraphEdge(\n"
            f"    source={self.source!r},\n"
            f"    target={self.target!r},\n"
            f"    relationship={self.relationship!r}\n"
            ")"
        )

    def to_dict(self) -> Dict[str, str]:
        """Convert this `GraphEdge` back into a plain dictionary.

        Returns:
            A dictionary with the keys `source`, `target`,
            `relationship`, and `provider`.
        """
        return {
            _FIELD_SOURCE: self.source,
            _FIELD_TARGET: self.target,
            _FIELD_RELATIONSHIP: self.relationship,
            _FIELD_PROVIDER: self.provider,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        """Create a `GraphEdge` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the keys `source`,
                `target`, `relationship`, and `provider` (e.g. a
                dependency entry from a UIR produced by
                `uir_schema.build_uir()`).

        Returns:
            A new, validated `GraphEdge`.

        Raises:
            GraphEdgeError: If `data` is not a dict, is missing any
                required key, or contains a value that fails field
                validation (see `__post_init__`).
        """
        if not isinstance(data, dict):
            logger.error("GraphEdge creation failed: expected a dict, got %s", type(data).__name__)
            raise GraphEdgeError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [field_name for field_name in _REQUIRED_FIELDS if field_name not in data]
        if missing_fields:
            logger.error("GraphEdge creation failed: missing required fields: %s", missing_fields)
            raise GraphEdgeError(f"Missing required fields: {missing_fields}")

        return cls(
            source=data[_FIELD_SOURCE],
            target=data[_FIELD_TARGET],
            relationship=data[_FIELD_RELATIONSHIP],
            provider=data[_FIELD_PROVIDER],
        )


__all__ = [
    "GraphEdge",
    "GraphEdgeError",
]
