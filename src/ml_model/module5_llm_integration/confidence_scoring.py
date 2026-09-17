"""Module 5.4 - Evidence-aware confidence scoring.

Computes a deterministic confidence score for Module 4 agent results and,
optionally, an LLM/model confidence signal.  The score is intentionally
separate from severity: a critical finding can be highly confident.

Formula (with weights renormalized when model confidence is absent):
    C = 0.35*A + 0.30*E + 0.20*G + 0.15*M

A = agent confidence component
E = evidence quality component
G = inter-agent agreement component
M = model confidence component

A small execution-quality gate is then applied:
    C_final = C * execution_quality

Execution quality penalizes failed/skipped agents, but never changes the
meaning of severity.  All values are clamped to [0, 1].
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable, Mapping, Optional, Sequence

try:
    from ..module4_multi_agent.agent_result import AgentResult
    from ..module4_multi_agent.agent_schema import AgentStatus
except ImportError:
    try:
        from src.ml_model.module4_multi_agent.agent_result import AgentResult
        from src.ml_model.module4_multi_agent.agent_schema import AgentStatus
    except ImportError:
        from agent_result import AgentResult  # type: ignore
        from agent_schema import AgentStatus  # type: ignore


class ConfidenceScoringError(ValueError):
    """Raised for invalid confidence-scoring input."""


@dataclass(frozen=True, kw_only=True)
class ConfidenceAssessment:
    """Structured, explainable confidence result."""

    score: float
    label: str
    agent_confidence: float
    evidence_quality: float
    agent_agreement: float
    model_confidence: Optional[float]
    execution_quality: float
    rationale: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "label": self.label,
            "components": {
                "agent_confidence": self.agent_confidence,
                "evidence_quality": self.evidence_quality,
                "agent_agreement": self.agent_agreement,
                "model_confidence": self.model_confidence,
                "execution_quality": self.execution_quality,
            },
            "rationale": list(self.rationale),
            "metadata": dict(self.metadata),
        }


class ConfidenceScorer:
    """Deterministic scorer for Module 4 results and evidence."""

    BASE_WEIGHTS = {
        "agent": 0.35,
        "evidence": 0.30,
        "agreement": 0.20,
        "model": 0.15,
    }

    def score(
        self,
        agent_results: Iterable[AgentResult],
        *,
        evidence_records: Optional[Iterable[Mapping[str, Any]]] = None,
        model_confidence: Optional[float] = None,
    ) -> ConfidenceAssessment:
        results = tuple(agent_results)
        self._validate_results(results)
        model = self._validate_optional_score(model_confidence, "model_confidence")
        evidence = tuple(evidence_records or ())
        for i, record in enumerate(evidence):
            if not isinstance(record, Mapping):
                raise ConfidenceScoringError(f"evidence_records[{i}] must be a mapping")

        agent_component = self._agent_confidence(results)
        evidence_component, evidence_meta = self._evidence_quality(results, evidence)
        agreement_component = self._agreement(results)
        execution_component = self._execution_quality(results)

        weights = dict(self.BASE_WEIGHTS)
        if model is None:
            weights.pop("model")
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        components = {
            "agent": agent_component,
            "evidence": evidence_component,
            "agreement": agreement_component,
        }
        if model is not None:
            components["model"] = model

        raw = sum(weights[k] * components[k] for k in components)
        final = self._clamp(raw * execution_component)
        label = self._label(final)

        rationale = []
        rationale.append(f"Agent confidence component: {agent_component:.3f}.")
        rationale.append(f"Evidence quality component: {evidence_component:.3f}.")
        rationale.append(f"Inter-agent agreement component: {agreement_component:.3f}.")
        if model is not None:
            rationale.append(f"Model confidence component: {model:.3f}.")
        else:
            rationale.append("No model confidence supplied; model weight was excluded and remaining weights were renormalized.")
        if execution_component < 1.0:
            rationale.append(f"Execution-quality gate reduced the combined score to account for failed/skipped agents ({execution_component:.3f}).")

        metadata = {
            "agent_count": len(results),
            "completed_count": sum(r.status == AgentStatus.COMPLETED for r in results),
            "failed_count": sum(r.status == AgentStatus.FAILED for r in results),
            "skipped_count": sum(r.status == AgentStatus.SKIPPED for r in results),
            "finding_count": sum(len(r.findings) for r in results),
            "unique_evidence_count": len(self._collect_evidence_ids(results, evidence)),
            "weights": weights,
            "raw_score": round(raw, 6),
            **evidence_meta,
        }
        return ConfidenceAssessment(
            score=round(final, 6),
            label=label,
            agent_confidence=round(agent_component, 6),
            evidence_quality=round(evidence_component, 6),
            agent_agreement=round(agreement_component, 6),
            model_confidence=None if model is None else round(model, 6),
            execution_quality=round(execution_component, 6),
            rationale=tuple(rationale),
            metadata=metadata,
        )

    def recommendation_confidence(
        self,
        recommendation: Mapping[str, Any],
        assessment: ConfidenceAssessment,
    ) -> float:
        """Combine an existing recommendation/model confidence with evidence confidence.

        If the recommendation has a numeric ``confidence`` field, the two
        signals are averaged. Otherwise the global evidence-aware score is
        used. This keeps recommendation confidence grounded in the pipeline
        rather than trusting an LLM score alone.
        """
        if not isinstance(recommendation, Mapping):
            raise ConfidenceScoringError("recommendation must be a mapping")
        supplied = recommendation.get("confidence")
        if supplied is None:
            return assessment.score
        supplied = self._validate_optional_score(supplied, "recommendation.confidence")
        assert supplied is not None
        return round((supplied + assessment.score) / 2.0, 6)

    @staticmethod
    def stable_assessment_id(assessment: ConfidenceAssessment) -> str:
        """Create a reproducible ID for the assessment contents."""
        payload = json.dumps(assessment.to_dict(), sort_keys=True, separators=(",", ":"))
        return "confidence:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _validate_results(results: Sequence[AgentResult]) -> None:
        if not results:
            raise ConfidenceScoringError("agent_results must contain at least one AgentResult")
        for i, result in enumerate(results):
            if not isinstance(result, AgentResult):
                raise ConfidenceScoringError(
                    f"agent_results[{i}] must be an AgentResult, got {type(result).__name__}"
                )

    @staticmethod
    def _validate_optional_score(value: Any, field: str) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfidenceScoringError(f"{field} must be a number in [0, 1]")
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ConfidenceScoringError(f"{field} must be a number in [0, 1]")
        return value

    @staticmethod
    def _agent_confidence(results: Sequence[AgentResult]) -> float:
        return sum(r.confidence for r in results) / len(results)

    def _evidence_quality(
        self,
        results: Sequence[AgentResult],
        explicit: Sequence[Mapping[str, Any]],
    ) -> tuple[float, dict[str, Any]]:
        ids = self._collect_evidence_ids(results, explicit)
        finding_count = sum(len(r.findings) for r in results)
        if not ids:
            # Absence of evidence is uncertainty, not proof of a bad result.
            score = 0.35 if finding_count else 0.70
            return score, {"evidence_coverage": 0.0, "evidence_source_diversity": 0}

        covered_findings = sum(1 for r in results for f in r.findings if f.evidence_ids)
        coverage = 1.0 if finding_count == 0 else covered_findings / finding_count
        agent_sources = {
            r.agent_type.value
            for r in results
            if r.evidence_ids or any(f.evidence_ids for f in r.findings)
        }
        explicit_sources = {str(x.get("source")) for x in explicit if x.get("source")}
        diversity = min(1.0, (len(agent_sources) + len(explicit_sources)) / 3.0)
        score = self._clamp(0.60 * coverage + 0.40 * diversity)
        return score, {
            "evidence_coverage": round(coverage, 6),
            "evidence_source_diversity": len(agent_sources) + len(explicit_sources),
        }

    @staticmethod
    def _collect_evidence_ids(
        results: Sequence[AgentResult], explicit: Sequence[Mapping[str, Any]]
    ) -> set[str]:
        ids: set[str] = set()
        for result in results:
            ids.update(result.evidence_ids)
            for finding in result.findings:
                ids.update(finding.evidence_ids)
        for record in explicit:
            value = record.get("evidence_id")
            if value:
                ids.add(str(value))
        return ids

    def _agreement(self, results: Sequence[AgentResult]) -> float:
        if len(results) < 2:
            return 0.75
        pair_scores = []
        for left, right in combinations(results, 2):
            left_keys = self._finding_keys(left)
            right_keys = self._finding_keys(right)
            if not left_keys and not right_keys:
                pair_scores.append(1.0)
                continue
            overlap = len(left_keys & right_keys)
            union = len(left_keys | right_keys)
            if overlap:
                pair_scores.append(overlap / union)
            else:
                # Heterogeneous agents often analyze unrelated dimensions;
                # lack of overlap is neutral rather than a contradiction.
                pair_scores.append(0.75)
        return sum(pair_scores) / len(pair_scores)

    @staticmethod
    def _finding_keys(result: AgentResult) -> set[tuple[str, str, str]]:
        return {
            (
                str(f.resource_id or ""),
                str(f.rule_id or ""),
                f.message.strip().lower(),
            )
            for f in result.findings
        }

    @staticmethod
    def _execution_quality(results: Sequence[AgentResult]) -> float:
        quality = 1.0
        for result in results:
            if result.status == AgentStatus.FAILED:
                quality *= 0.70
            elif result.status == AgentStatus.SKIPPED:
                quality *= 0.90
        return quality

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.85:
            return "VERY_HIGH"
        if score >= 0.70:
            return "HIGH"
        if score >= 0.50:
            return "MODERATE"
        if score >= 0.30:
            return "LOW"
        return "VERY_LOW"

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
