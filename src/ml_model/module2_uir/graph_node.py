"""graph_node.py.

Defines `GraphNode`, the graph-ready representation of a single
infrastructure resource within the Unified Intermediate Representation
(UIR).

Where `uir_schema.build_uir()` produces plain resource dictionaries and
`uir_validator.validate_uir()` confirms those dictionaries are
structurally sound, `GraphNode` is the typed, immutable object that
later modules — the Static Validation Engine, the Multi-Agent
Framework, Runtime Drift Analysis, and the Recommendation Engine — are
expected to actually work with once a UIR resource becomes a node in a
graph. It performs no parsing, extraction, or schema construction of
its own; it only wraps an already-validated resource record and
enforces that its own required fields are present and well-formed.

Requirements:
    - Python 3.12

Typical usage:
    from graph_node import GraphNode

    node = GraphNode.from_dict(uir["resources"][0])
    print(node)
    # GraphNode(id='aws_instance.web_server')

    node.to_dict()
    # {"id": "...", "provider": "...", "type": "...",
    #  "canonical_type": "...", "name": "...", "properties": {...}}
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
class GraphNodeError(Exception):
    """Raised when a `GraphNode` cannot be created from invalid data."""


# ---------------------------------------------------------------------------
# Required field names, declared once so they are never repeated as
# literal strings elsewhere in this module.
# ---------------------------------------------------------------------------
_FIELD_ID = "id"
_FIELD_PROVIDER = "provider"
_FIELD_TYPE = "type"
_FIELD_CANONICAL_TYPE = "canonical_type"
_FIELD_NAME = "name"
_FIELD_PROPERTIES = "properties"

_REQUIRED_STRING_FIELDS = (
    _FIELD_ID,
    _FIELD_PROVIDER,
    _FIELD_TYPE,
    _FIELD_CANONICAL_TYPE,
    _FIELD_NAME,
)
_REQUIRED_FIELDS = _REQUIRED_STRING_FIELDS + (_FIELD_PROPERTIES,)


def _validate_non_empty_string(value: Any, field_name: str) -> None:
    """Validate that a field's value is a non-empty string.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message and log entry.

    Raises:
        GraphNodeError: If `value` is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        logger.error("GraphNode creation failed: field '%s' is invalid: %r", field_name, value)
        raise GraphNodeError(f"Field '{field_name}' must be a non-empty string, got {value!r}")


# ---------------------------------------------------------------------------
# GraphNode
# ---------------------------------------------------------------------------
@dataclass(frozen=True, repr=False)
class GraphNode:
    """An immutable graph-ready representation of one infrastructure resource.

    A `GraphNode` is the node type later graph-based modules build on
    top of: the Static Validation Engine, the Multi-Agent Framework,
    Runtime Drift Analysis, and the Recommendation Engine. It is
    frozen (immutable) since a node's identity should never silently
    change after construction — any transformation should produce a
    new `GraphNode` rather than mutate an existing one.

    Attributes:
        id: The resource's stable UIR identifier (e.g.
            "aws_instance.web_server" for Terraform, or
            "WebServerInstance" for CloudFormation).
        provider: The IaC provider that produced the resource (e.g.
            "Terraform", "CloudFormation").
        type: The resource's provider-native type (e.g. "aws_instance",
            "AWS::EC2::Instance").
        canonical_type: The resource's provider-agnostic UIR type (e.g.
            "compute_instance"), as produced by
            `provider_mapper.get_canonical_resource_type()`.
        name: The resource's logical/declared name.
        properties: The resource's raw, unmodified property block.
    """

    id: str
    provider: str
    type: str
    canonical_type: str
    name: str
    properties: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate all fields immediately after construction.

        Raises:
            GraphNodeError: If `id`, `provider`, `type`,
                `canonical_type`, or `name` is not a non-empty string,
                or if `properties` is not a dict.
        """
        for field_name in _REQUIRED_STRING_FIELDS:
            _validate_non_empty_string(getattr(self, field_name), field_name)

        if not isinstance(self.properties, dict):
            logger.error(
                "GraphNode creation failed: field '%s' must be a dict, got %s",
                _FIELD_PROPERTIES,
                type(self.properties).__name__,
            )
            raise GraphNodeError(
                f"Field '{_FIELD_PROPERTIES}' must be a dict, got "
                f"{type(self.properties).__name__}"
            )

    def __hash__(self) -> int:
        """Hash a `GraphNode` by its `id` alone.

        `properties` is a dict and therefore unhashable, so hashing
        every field (the dataclass default for a frozen class) is not
        possible. Since `id` is a resource's stable UIR identifier, it
        alone is sufficient to identify a node within a graph.

        Returns:
            The hash of `self.id`.
        """
        return hash(self.id)

    def __repr__(self) -> str:
        """Return a short, readable representation for debugging.

        Returns:
            A string of the form "GraphNode(id='...')".
        """
        return f"GraphNode(id={self.id!r})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert this `GraphNode` back into a plain dictionary.

        Returns:
            A dictionary with the keys `id`, `provider`, `type`,
            `canonical_type`, `name`, and `properties`.
        """
        return {
            _FIELD_ID: self.id,
            _FIELD_PROVIDER: self.provider,
            _FIELD_TYPE: self.type,
            _FIELD_CANONICAL_TYPE: self.canonical_type,
            _FIELD_NAME: self.name,
            _FIELD_PROPERTIES: self.properties,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        """Create a `GraphNode` from a plain dictionary.

        Args:
            data: A dictionary expected to contain the keys `id`,
                `provider`, `type`, `canonical_type`, `name`, and
                `properties` (e.g. a resource entry from a UIR
                produced by `uir_schema.build_uir()`).

        Returns:
            A new, validated `GraphNode`.

        Raises:
            GraphNodeError: If `data` is not a dict, is missing any
                required key, or contains a value that fails field
                validation (see `__post_init__`).
        """
        if not isinstance(data, dict):
            logger.error("GraphNode creation failed: expected a dict, got %s", type(data).__name__)
            raise GraphNodeError(f"Expected a dict, got {type(data).__name__}")

        missing_fields = [field_name for field_name in _REQUIRED_FIELDS if field_name not in data]
        if missing_fields:
            logger.error("GraphNode creation failed: missing required fields: %s", missing_fields)
            raise GraphNodeError(f"Missing required fields: {missing_fields}")

        return cls(
            id=data[_FIELD_ID],
            provider=data[_FIELD_PROVIDER],
            type=data[_FIELD_TYPE],
            canonical_type=data[_FIELD_CANONICAL_TYPE],
            name=data[_FIELD_NAME],
            properties=data[_FIELD_PROPERTIES],
        )


__all__ = [
    "GraphNode",
    "GraphNodeError",
]
