"""Explainable criticality-weighted telemetry-to-intent drift scoring."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping

from .schemas import DriftAssessment, DriftCategory, RuntimeState


class CriticalityModel:
    """Configurable deterministic model; all coefficients are explicit."""
    DEFAULT_WEIGHTS = {"base": 0.30, "security": 0.25, "availability": 0.15, "dependency": 0.20, "production": 0.10}
    SECURITY = ("iam", "security", "network", "encryption", "kms")
    AVAILABILITY = ("compute", "database", "load_balancer")
    def __init__(self, weights: Mapping[str, float] | None = None, overrides: Mapping[str, float] | None = None) -> None:
        self.weights = dict(self.DEFAULT_WEIGHTS) | dict(weights or {}); self.overrides = dict(overrides or {})
    def score(self, resource: Mapping[str, Any], graph: Mapping[str, Any] | None = None) -> tuple[float, dict[str, float]]:
        rid = str(resource.get("id", "")); kind = str(resource.get("canonical_type", resource.get("type", ""))).lower(); props = resource.get("properties", {})
        if rid in self.overrides: return self._clamp(self.overrides[rid]), {"override": self._clamp(self.overrides[rid])}
        edges = (graph or {}).get("edges", ())
        degree = sum(1 for e in edges if e.get("source") == rid or e.get("target") == rid)
        production = "production" in json.dumps(props, sort_keys=True).lower()
        parts = {"base": self.weights["base"], "security": self.weights["security"] if any(x in kind for x in self.SECURITY) else 0.0, "availability": self.weights["availability"] if any(x in kind for x in self.AVAILABILITY) else 0.0, "dependency": min(self.weights["dependency"], degree * self.weights["dependency"] / 3), "production": self.weights["production"] if production else 0.0}
        return self._clamp(sum(parts.values())), parts
    @staticmethod
    def _clamp(v: float) -> float: return max(0.0, min(1.0, float(v)))


class TelemetryIntentDriftAnalyzer:
    def __init__(self, criticality_model: CriticalityModel | None = None) -> None: self.criticality_model = criticality_model or CriticalityModel()
    def analyze(self, uir: Mapping[str, Any], runtime: RuntimeState) -> tuple[DriftAssessment, ...]:
        observed = {x.resource_id: x for x in runtime.resources}; metrics = {}
        for item in runtime.telemetry: metrics.setdefault(item.resource_id, []).append(item)
        return tuple(self._one(x, observed.get(str(x.get("id"))), metrics.get(str(x.get("id")), []), uir.get("graph"), runtime.collection_errors) for x in sorted(uir.get("resources", ()), key=lambda x: str(x.get("id"))))
    def _one(self, desired: Mapping[str, Any], observed: Any, telemetry: list[Any], graph: Mapping[str, Any] | None, collection_errors: tuple[Any, ...]) -> DriftAssessment:
        rid = str(desired["id"]); criticality, criticality_parts = self.criticality_model.score(desired, graph)
        config_failure = any(
            error.source == "AWS_CONFIG" and error.resource_id in (None, rid)
            and error.code in {"API_ERROR", "UNAVAILABLE", "MALFORMED"}
            for error in collection_errors
        )
        not_found = any(error.source == "AWS_CONFIG" and error.resource_id in (None, rid) and error.code == "NOT_FOUND" for error in collection_errors)
        if observed is None and config_failure:
            mismatch, magnitude, evidence_quality, category = 0.0, 0.0, 0.25, DriftCategory.INSUFFICIENT_EVIDENCE
            observed_dict = None
            rationale = ["AWS Config collection failed; missing observation is not configuration drift."]
        elif observed is None and not_found:
            mismatch, magnitude, evidence_quality, category = 1.0, 1.0, 0.85, DriftCategory.CONFIRMED_DRIFT
            observed_dict = None
            rationale = ["AWS Config confirmed that the desired runtime resource was not found."]
        elif observed is None:
            # No record without an authoritative NOT_FOUND result is an
            # observation gap, not proof that a resource was deleted.
            mismatch, magnitude, evidence_quality, category = 0.0, 0.0, 0.25, DriftCategory.INSUFFICIENT_EVIDENCE
            observed_dict = None
            rationale = ["No runtime configuration was returned and absence was not authoritatively confirmed."]
        else:
            diffs = self._diff(desired.get("properties", {}), observed.configuration)
            mismatch, magnitude = (1.0 if diffs else 0.0), min(1.0, len(diffs) / max(1, len(desired.get("properties", {}))))
            observed_dict = observed.to_dict(); evidence_quality = 0.9 if observed.collection_status.value == "SUCCESS" else 0.5
            category = (DriftCategory.CONFIRMED_DRIFT if observed.collection_status.value == "SUCCESS" else DriftCategory.LIKELY_DRIFT) if diffs else DriftCategory.NO_DRIFT
            rationale = [f"Configuration comparison found {len(diffs)} differing property path(s)."]
        # Telemetry is supporting evidence, never absence-as-drift.
        telemetry_weight = 1.0 if telemetry else 0.5
        persistence, persistence_factors = self._persistence(telemetry)
        dependency = min(1.0, 0.5 + sum(1 for e in (graph or {}).get("edges", ()) if rid in (e.get("source"), e.get("target"))) / 4)
        if not mismatch and telemetry:
            anomalies = [x for x in telemetry if ("error" in x.metric_name.lower() and x.value > 0) or ("cpu" in x.metric_name.lower() and x.value >= 95)]
            if anomalies:
                mismatch, magnitude = 1.0, min(0.8, .4 + .15 * len(anomalies))
                category = DriftCategory.LIKELY_DRIFT if len(anomalies) >= 2 and persistence >= .55 else DriftCategory.POSSIBLE_DRIFT
                rationale.append(f"{len(anomalies)} telemetry anomaly observation(s) support a {category.value} classification.")
        if not mismatch and not telemetry:
            category = DriftCategory.INSUFFICIENT_EVIDENCE
            rationale.append("No telemetry was collected; this is not treated as drift.")
        score = self._clamp(mismatch * criticality * telemetry_weight * magnitude * persistence * dependency * evidence_quality)
        if category == DriftCategory.NO_DRIFT: severity = "NONE"
        elif category == DriftCategory.INSUFFICIENT_EVIDENCE: severity = "INFO"
        elif score >= .55: severity = "CRITICAL"
        elif score >= .30: severity = "HIGH"
        elif score >= .12: severity = "MEDIUM"
        else: severity = "LOW"
        factors = {"intent_mismatch": mismatch, "criticality": criticality, "telemetry_evidence_weight": telemetry_weight, "persistence": persistence, "dependency_impact": dependency, "evidence_confidence": evidence_quality, **persistence_factors, **{f"criticality_{k}": v for k, v in criticality_parts.items()}}
        ids = tuple(x.evidence_id for x in telemetry) + (() if observed is None else (observed.evidence_id,))
        raw = {"resource_id": rid, "category": category.value, "factors": factors, "evidence_ids": ids}
        evidence_id = "runtime-drift:" + hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:16]
        return DriftAssessment(resource_id=rid, category=category, score=round(score, 6), severity=severity, confidence=round(evidence_quality, 6), factors=factors, desired=dict(desired), observed=observed_dict, telemetry_evidence_ids=ids, evidence_id=evidence_id, rationale=tuple(rationale))
    @staticmethod
    def _diff(a: Any, b: Any, path: str = "") -> list[str]:
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            return sum((TelemetryIntentDriftAnalyzer._diff(a.get(k), b.get(k), f"{path}.{k}" if path else str(k)) for k in sorted(set(a) | set(b), key=str)), [])
        return [] if a == b else [path]
    @staticmethod
    def _persistence(telemetry: list[Any]) -> tuple[float, dict[str, float]]:
        """Describe observed repetition without claiming statistical persistence."""
        if not telemetry:
            return .5, {"telemetry_observation_count": 0., "telemetry_unique_timestamps": 0., "telemetry_span_seconds": 0., "telemetry_repeated_anomaly_count": 0., "telemetry_continuity": 0.}
        timestamps = []
        for item in telemetry:
            try: timestamps.append(datetime.fromisoformat(str(item.timestamp).replace("Z", "+00:00")))
            except ValueError: pass
        unique = sorted(set(timestamps)); span = max(0., (unique[-1] - unique[0]).total_seconds()) if len(unique) > 1 else 0.
        anomalies = sum(1 for x in telemetry if ("error" in x.metric_name.lower() and x.value > 0) or ("cpu" in x.metric_name.lower() and x.value >= 95))
        continuity = min(1., (len(unique)-1) / max(1, len(telemetry)-1)) if len(telemetry) > 1 else 0.
        score = min(1., .20 + .20 * min(len(telemetry), 3) + .25 * min(anomalies, 2) / 2 + .15 * continuity)
        return score, {"telemetry_observation_count": float(len(telemetry)), "telemetry_unique_timestamps": float(len(unique)), "telemetry_span_seconds": round(span, 3), "telemetry_repeated_anomaly_count": float(anomalies), "telemetry_continuity": round(continuity, 6)}
    @staticmethod
    def _clamp(v: float) -> float: return max(0.0, min(1.0, float(v)))
