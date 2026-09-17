from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class RecommendationSchemaError(ValueError):
    """Raised when a recommendation schema object is invalid."""


class RecommendationPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class RecommendationAction(str, Enum):
    FIX = "FIX"
    REVIEW = "REVIEW"
    MONITOR = "MONITOR"
    NO_ACTION = "NO_ACTION"


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecommendationSchemaError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _validate_confidence(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecommendationSchemaError(
            f"{field_name} must be a number between 0.0 and 1.0"
        )

    value = float(value)

    if not 0.0 <= value <= 1.0:
        raise RecommendationSchemaError(
            f"{field_name} must be between 0.0 and 1.0"
        )

    return value


@dataclass(frozen=True, kw_only=True)
class Recommendation:
    """One explainable infrastructure recommendation."""

    recommendation_id: str
    title: str
    description: str
    priority: RecommendationPriority
    action: RecommendationAction
    rationale: str
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    resource_id: Optional[str] = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        _require_string(
            self.recommendation_id,
            "recommendation_id",
        )

        _require_string(self.title, "title")
        _require_string(self.description, "description")
        _require_string(self.rationale, "rationale")

        try:
            priority = RecommendationPriority(self.priority)
        except (ValueError, TypeError) as exc:
            raise RecommendationSchemaError(
                f"Invalid recommendation priority: {self.priority}"
            ) from exc

        try:
            action = RecommendationAction(self.action)
        except (ValueError, TypeError) as exc:
            raise RecommendationSchemaError(
                f"Invalid recommendation action: {self.action}"
            ) from exc

        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "action", action)

        object.__setattr__(
            self,
            "confidence",
            _validate_confidence(
                self.confidence,
                "confidence",
            ),
        )

        evidence_ids = tuple(self.evidence_ids)

        for index, evidence_id in enumerate(evidence_ids):
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise RecommendationSchemaError(
                    f"evidence_ids[{index}] must be a non-empty string"
                )

        object.__setattr__(
            self,
            "evidence_ids",
            evidence_ids,
        )

        if self.resource_id is not None:
            _require_string(
                self.resource_id,
                "resource_id",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "action": self.action.value,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
            "resource_id": self.resource_id,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, kw_only=True)
class RecommendationReport:
    """Complete explainable recommendation output."""

    recommendations: Tuple[Recommendation, ...]
    overall_confidence: float
    source_model_id: str
    source_response_confidence: float
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        recommendations = tuple(self.recommendations)

        for index, recommendation in enumerate(recommendations):
            if not isinstance(recommendation, Recommendation):
                raise RecommendationSchemaError(
                    f"recommendations[{index}] must be a Recommendation"
                )

        object.__setattr__(
            self,
            "recommendations",
            recommendations,
        )

        object.__setattr__(
            self,
            "overall_confidence",
            _validate_confidence(
                self.overall_confidence,
                "overall_confidence",
            ),
        )

        _require_string(
            self.source_model_id,
            "source_model_id",
        )

        object.__setattr__(
            self,
            "source_response_confidence",
            _validate_confidence(
                self.source_response_confidence,
                "source_response_confidence",
            ),
        )

        if self.metadata is not None and not isinstance(
            self.metadata,
            dict,
        ):
            raise RecommendationSchemaError(
                "metadata must be a dictionary or None"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendations": [
                recommendation.to_dict()
                for recommendation in self.recommendations
            ],
            "overall_confidence": self.overall_confidence,
            "source_model_id": self.source_model_id,
            "source_response_confidence": self.source_response_confidence,
            "metadata": self.metadata,
        }