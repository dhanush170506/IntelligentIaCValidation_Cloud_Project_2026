"""Stable, serializable data contracts for Module 6."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


def _stable_id(prefix: str, value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class CollectionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class DriftCategory(str, Enum):
    CONFIRMED_DRIFT = "CONFIRMED_DRIFT"
    LIKELY_DRIFT = "LIKELY_DRIFT"
    POSSIBLE_DRIFT = "POSSIBLE_DRIFT"
    NO_DRIFT = "NO_DRIFT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, kw_only=True)
class TelemetryDatum:
    resource_id: str
    resource_type: str
    metric_name: str
    namespace: str
    timestamp: str
    value: float
    unit: str = "None"
    statistic: str = "Average"
    dimensions: dict[str, str] = field(default_factory=dict)
    source: str = "CLOUDWATCH"

    def __post_init__(self) -> None:
        if not all(isinstance(x, str) and x.strip() for x in (self.resource_id, self.resource_type, self.metric_name, self.namespace, self.timestamp, self.source)):
            raise ValueError("telemetry identity fields must be non-empty strings")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("telemetry value must be numeric")

    @property
    def evidence_id(self) -> str:
        return _stable_id("telemetry", asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"evidence_id": self.evidence_id}


@dataclass(frozen=True, kw_only=True)
class ConfigState:
    resource_id: str
    resource_type: str
    provider: str
    configuration: dict[str, Any]
    relationships: tuple[dict[str, Any], ...] = ()
    capture_timestamp: str = "1970-01-01T00:00:00Z"
    source: str = "AWS_CONFIG"
    collection_status: CollectionStatus = CollectionStatus.SUCCESS

    @property
    def evidence_id(self) -> str:
        return _stable_id("config", self.to_dict(include_evidence=False))

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        value = asdict(self)
        value["collection_status"] = self.collection_status.value
        value["relationships"] = list(self.relationships)
        if include_evidence:
            value["evidence_id"] = self.evidence_id
        return value


@dataclass(frozen=True, kw_only=True)
class CollectionError:
    source: str
    resource_id: str | None
    code: str
    message: str

    @property
    def evidence_id(self) -> str:
        return _stable_id("collection-error", self.to_dict(include_evidence=False))

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_evidence:
            value["evidence_id"] = self.evidence_id
        return value


@dataclass(frozen=True, kw_only=True)
class RuntimeState:
    resources: tuple[ConfigState, ...]
    telemetry: tuple[TelemetryDatum, ...]
    collection_evidence: tuple[dict[str, Any], ...]
    collection_errors: tuple[CollectionError, ...]
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resources": [x.to_dict() for x in self.resources],
            "telemetry": [x.to_dict() for x in self.telemetry],
            "collection_evidence": list(self.collection_evidence),
            "collection_errors": [x.to_dict() for x in self.collection_errors],
            "timestamp": self.timestamp, "metadata": self.metadata,
        }


@dataclass(frozen=True, kw_only=True)
class DriftAssessment:
    resource_id: str
    category: DriftCategory
    score: float
    severity: str
    confidence: float
    factors: dict[str, float]
    desired: dict[str, Any]
    observed: dict[str, Any] | None
    telemetry_evidence_ids: tuple[str, ...]
    evidence_id: str
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["category"] = self.category.value
        return value
