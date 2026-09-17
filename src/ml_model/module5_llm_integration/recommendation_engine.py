from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Optional

try:
    from .bedrock_schema import BedrockResponse
    from .recommendation_schema import (
        Recommendation,
        RecommendationAction,
        RecommendationPriority,
        RecommendationReport,
    )
except ImportError:
    from bedrock_schema import BedrockResponse
    from recommendation_schema import (
        Recommendation,
        RecommendationAction,
        RecommendationPriority,
        RecommendationReport,
    )


class RecommendationEngineError(RuntimeError):
    """Raised when recommendation generation fails."""


class RecommendationEngine:
    """
    Generates structured, explainable recommendations from LLM output
    and the evidence that was supplied to the LLM.

    The engine intentionally does not invent evidence IDs. Every evidence
    reference in a recommendation must exist in the supplied evidence set.
    """

    def generate(
        self,
        *,
        response: BedrockResponse,
        agent_results: Iterable[Any],
        evidence: Iterable[Any] = (),
    ) -> RecommendationReport:
        if not isinstance(response, BedrockResponse):
            raise RecommendationEngineError(
                "response must be a BedrockResponse"
            )

        results = tuple(agent_results)

        if not results:
            raise RecommendationEngineError(
                "agent_results must contain at least one result"
            )

        evidence_records = tuple(evidence)

        valid_evidence_ids = self._collect_evidence_ids(
            results,
            evidence_records,
        )

        recommendations = self._generate_from_agent_findings(
            results=results,
            valid_evidence_ids=valid_evidence_ids,
        )

        overall_confidence = self._calculate_overall_confidence(
            response=response,
            recommendations=recommendations,
        )

        return RecommendationReport(
            recommendations=tuple(recommendations),
            overall_confidence=overall_confidence,
            source_model_id=response.model_id,
            source_response_confidence=response.confidence,
            metadata={
                "agent_result_count": len(results),
                "evidence_record_count": len(evidence_records),
                "recommendation_count": len(recommendations),
                "evidence_grounded": True,
                "generation_mode": "evidence_derived",
            },
        )

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def _collect_evidence_ids(
        self,
        results: tuple[Any, ...],
        evidence_records: tuple[Any, ...],
    ) -> set[str]:
        """
        Build the authoritative evidence-ID registry.

        Evidence IDs claimed by an AgentResult or AgentFinding are NOT
        automatically trusted. They must be backed by an explicit evidence
        record supplied to the recommendation engine.
        """

        valid_ids: set[str] = set()

        for record in evidence_records:
            if hasattr(record, "to_dict"):
                record = record.to_dict()

            if not isinstance(record, Mapping):
                continue

            evidence_id = record.get("evidence_id")

            if evidence_id:
                valid_ids.add(str(evidence_id))

        return valid_ids
    # ------------------------------------------------------------------
    # Recommendation generation
    # ------------------------------------------------------------------

    def _generate_from_agent_findings(
        self,
        *,
        results: tuple[Any, ...],
        valid_evidence_ids: set[str],
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        for result in results:
            if not hasattr(result, "findings"):
                continue

            for finding in result.findings:
                severity = getattr(
                    finding,
                    "severity",
                    "INFO",
                )

                severity_value = getattr(
                    severity,
                    "value",
                    str(severity),
                ).upper()

                message = str(
                    getattr(
                        finding,
                        "message",
                        "Infrastructure issue detected.",
                    )
                )

                evidence_ids = tuple(
                    evidence_id
                    for evidence_id in getattr(
                        finding,
                        "evidence_ids",
                        (),
                    )
                    if evidence_id in valid_evidence_ids
                )

                resource_id = getattr(
                    finding,
                    "resource_id",
                    None,
                )

                priority = self._priority_from_severity(
                    severity_value
                )

                action = self._action_from_severity(
                    severity_value
                )

                recommendation_id = self._make_id(
                    severity_value,
                    message,
                    resource_id,
                    evidence_ids,
                )

                recommendations.append(
                    Recommendation(
                        recommendation_id=recommendation_id,
                        title=self._make_title(
                            severity_value,
                            message,
                        ),
                        description=(
                            "Review and address the identified "
                            "infrastructure assurance issue."
                        ),
                        priority=priority,
                        action=action,
                        rationale=(
                            f"The {severity_value} finding states: "
                            f"{message}"
                        ),
                        evidence_ids=evidence_ids,
                        resource_id=resource_id,
                        confidence=float(
                            getattr(
                                finding,
                                "confidence",
                                0.5,
                            )
                        ),
                    )
                )

        return recommendations

    # ------------------------------------------------------------------
    # Priority / action
    # ------------------------------------------------------------------

    @staticmethod
    def _priority_from_severity(
        severity: str,
    ) -> RecommendationPriority:
        mapping = {
            "CRITICAL": RecommendationPriority.CRITICAL,
            "HIGH": RecommendationPriority.HIGH,
            "MEDIUM": RecommendationPriority.MEDIUM,
            "LOW": RecommendationPriority.LOW,
            "INFO": RecommendationPriority.INFO,
        }

        return mapping.get(
            severity,
            RecommendationPriority.INFO,
        )

    @staticmethod
    def _action_from_severity(
        severity: str,
    ) -> RecommendationAction:
        if severity in {"CRITICAL", "HIGH", "MEDIUM"}:
            return RecommendationAction.FIX

        if severity == "LOW":
            return RecommendationAction.REVIEW

        return RecommendationAction.MONITOR

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_overall_confidence(
        *,
        response: BedrockResponse,
        recommendations: list[Recommendation],
    ) -> float:
        if not recommendations:
            return response.confidence

        recommendation_confidence = sum(
            recommendation.confidence
            for recommendation in recommendations
        ) / len(recommendations)

        # Keep model confidence relevant while preventing it from
        # completely overriding evidence-derived confidence.
        return round(
            (
                0.4 * response.confidence
                + 0.6 * recommendation_confidence
            ),
            4,
        )

    # ------------------------------------------------------------------
    # Deterministic IDs / titles
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(
        severity: str,
        message: str,
        resource_id: Optional[str],
        evidence_ids: tuple[str, ...],
    ) -> str:
        canonical = json.dumps(
            {
                "severity": severity,
                "message": message,
                "resource_id": resource_id,
                "evidence_ids": evidence_ids,
            },
            sort_keys=True,
        )

        digest = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()[:16]

        return f"recommendation:{digest}"

    @staticmethod
    def _make_title(
        severity: str,
        message: str,
    ) -> str:
        words = message.strip().split()

        if len(words) > 10:
            message = " ".join(words[:10]) + "..."

        return f"{severity} assurance recommendation: {message}"