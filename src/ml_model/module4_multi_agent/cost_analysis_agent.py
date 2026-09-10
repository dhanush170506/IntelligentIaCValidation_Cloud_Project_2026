"""cost_analysis_agent.py.

Module 4 Cost Analysis Agent.

Provides deterministic, explainable infrastructure cost estimation from the
Module 2 UIR. Pricing is injected by the caller so the agent does not require
AWS credentials, network access, or a live pricing API.

The agent intentionally performs no LLM reasoning. It produces standardized
Module 4 AgentFinding / AgentResult objects and can later be connected to a
live pricing provider without changing its analysis contract.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from numbers import Real
from typing import Any, Dict, Iterable, List, Tuple

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]


logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_HOURS = 730.0
DEFAULT_HIGH_COST_THRESHOLD = 100.0
DEFAULT_CURRENCY = "USD"

# Canonical UIR types for which a deterministic quantity/count can be useful.
_QUANTITY_KEYS = ("count", "quantity", "instances", "replicas")

# Common property names used by deterministic catalog entries.
_TYPE_KEYS = ("type", "canonical_type", "resource_type")


class CostAnalysisAgentError(Exception):
    """Raised for direct Cost Analysis Agent errors."""


class CostAnalysisAgent(BaseAgent):
    """Estimate infrastructure cost using an injected deterministic catalog."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.COST_ANALYSIS

    def validate_input(
        self,
        *,
        uir: Any = None,
        pricing_catalog: Any = None,
        monthly_hours: Any = DEFAULT_MONTHLY_HOURS,
        high_cost_threshold: Any = DEFAULT_HIGH_COST_THRESHOLD,
        **kwargs: object,
    ) -> None:
        if not isinstance(uir, Mapping):
            raise TypeError(
                f"uir must be a mapping/dictionary, got {type(uir).__name__}"
            )

        if "resources" not in uir:
            raise ValueError("uir is missing required field 'resources'")

        if not isinstance(uir["resources"], (list, tuple)):
            raise TypeError("uir['resources'] must be a list or tuple")

        for index, resource in enumerate(uir["resources"]):
            if not isinstance(resource, Mapping):
                raise TypeError(
                    f"uir['resources'][{index}] must be a mapping"
                )
            resource_id = str(resource.get("id", "")).strip()
            if not resource_id:
                raise ValueError(
                    f"uir['resources'][{index}] is missing a usable resource ID"
                )

        if not isinstance(pricing_catalog, Mapping):
            raise TypeError(
                "pricing_catalog must be a mapping/dictionary"
            )

        self._validate_catalog(pricing_catalog)

        hours = self._validate_non_negative_number(
            monthly_hours, "monthly_hours"
        )
        if hours <= 0:
            raise ValueError("monthly_hours must be greater than zero")

        threshold = self._validate_non_negative_number(
            high_cost_threshold, "high_cost_threshold"
        )
        if threshold < 0:
            raise ValueError("high_cost_threshold cannot be negative")

    def execute(
        self,
        *,
        uir: Any = None,
        pricing_catalog: Any = None,
        monthly_hours: Any = DEFAULT_MONTHLY_HOURS,
        high_cost_threshold: Any = DEFAULT_HIGH_COST_THRESHOLD,
        currency: str = DEFAULT_CURRENCY,
        **kwargs: object,
    ) -> AgentResult:
        if not isinstance(uir, Mapping):
            raise CostAnalysisAgentError("validated UIR unexpectedly unavailable")

        provider = str(uir.get("provider", "UNKNOWN")).strip() or "UNKNOWN"
        resources = list(uir["resources"])
        hours = float(monthly_hours)
        threshold = float(high_cost_threshold)
        currency_text = str(currency).strip() or DEFAULT_CURRENCY

        findings: List[AgentFinding] = []
        evidence_ids: List[str] = []
        evidence_seen: set[str] = set()

        total_cost = 0.0
        priced_count = 0
        unpriced_count = 0

        def add_finding(
            severity: AgentSeverity,
            message: str,
            *,
            resource_id: str | None,
            rule_id: str,
            confidence: float,
        ) -> None:
            evidence_id = self._evidence_id(
                provider=provider,
                rule_id=rule_id,
                resource_id=resource_id,
            )
            if evidence_id not in evidence_seen:
                evidence_seen.add(evidence_id)
                evidence_ids.append(evidence_id)

            findings.append(
                AgentFinding(
                    agent_type=self.agent_type,
                    severity=severity,
                    message=message,
                    confidence=confidence,
                    resource_id=resource_id,
                    rule_id=rule_id,
                    evidence_ids=(evidence_id,),
                )
            )

        for resource in resources:
            resource_id = str(resource["id"]).strip()
            resource_type = self._resource_type(resource)
            properties = resource.get("properties", {})
            if not isinstance(properties, Mapping):
                properties = {}

            entry = self._lookup_price(pricing_catalog, resource, properties)

            if entry is None:
                unpriced_count += 1
                add_finding(
                    AgentSeverity.INFO,
                    (
                        f"Pricing information unavailable for resource "
                        f"'{resource_id}' (type '{resource_type}'). "
                        "No cost has been invented."
                    ),
                    resource_id=resource_id,
                    rule_id="COST_PRICING_UNAVAILABLE",
                    confidence=0.60,
                )
                continue

            cost, basis = self._calculate_monthly_cost(
                entry=entry,
                properties=properties,
                monthly_hours=hours,
            )

            priced_count += 1
            total_cost += cost

            add_finding(
                AgentSeverity.INFO,
                (
                    f"Resource '{resource_id}' estimated at "
                    f"{currency_text} {cost:.2f}/month using {basis}."
                ),
                resource_id=resource_id,
                rule_id="COST_ESTIMATE",
                confidence=0.98,
            )

            if cost > threshold:
                add_finding(
                    AgentSeverity.HIGH,
                    (
                        f"Resource '{resource_id}' has an estimated monthly "
                        f"cost of {currency_text} {cost:.2f}, exceeding the "
                        f"configured high-cost threshold of "
                        f"{currency_text} {threshold:.2f}."
                    ),
                    resource_id=resource_id,
                    rule_id="COST_HIGH_RESOURCE",
                    confidence=0.95,
                )

            recommendation = self._optimization_recommendation(
                resource=resource,
                pricing_catalog=pricing_catalog,
                current_entry=entry,
                properties=properties,
                monthly_hours=hours,
                currency=currency_text,
            )
            if recommendation is not None:
                message, recommendation_cost = recommendation
                savings = max(0.0, cost - recommendation_cost)
                add_finding(
                    AgentSeverity.MEDIUM,
                    (
                        f"{message} Estimated alternative cost is "
                        f"{currency_text} {recommendation_cost:.2f}/month "
                        f"(potential difference {currency_text} "
                        f"{savings:.2f}/month)."
                    ),
                    resource_id=resource_id,
                    rule_id="COST_OPTIMIZATION_OPPORTUNITY",
                    confidence=0.84,
                )

        # A summary finding makes the total cost visible in the standardized
        # finding stream as well as AgentResult.metadata.
        add_finding(
            AgentSeverity.INFO,
            (
                f"Estimated monthly infrastructure cost is "
                f"{currency_text} {total_cost:.2f} across "
                f"{priced_count} priced resource(s); "
                f"{unpriced_count} resource(s) lack pricing data."
            ),
            resource_id=None,
            rule_id="COST_TOTAL_ESTIMATE",
            confidence=0.90 if unpriced_count else 0.98,
        )

        if priced_count == 0 and resources:
            confidence = 0.60
        elif findings:
            confidence = min(f.confidence for f in findings)
        else:
            confidence = 1.0

        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            message=(
                f"Cost analysis completed for {provider}: "
                f"{currency_text} {total_cost:.2f}/month estimated."
            ),
            confidence=confidence,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            metadata={
                "provider": provider,
                "currency": currency_text,
                "monthly_hours": hours,
                "high_cost_threshold": threshold,
                "resource_count": len(resources),
                "priced_resource_count": priced_count,
                "unpriced_resource_count": unpriced_count,
                "estimated_monthly_cost": round(total_cost, 2),
            },
        )

    @staticmethod
    def _validate_non_negative_number(value: Any, field_name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{field_name} must be a number")
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError(f"{field_name} must be finite")
        if number < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return number

    @classmethod
    def _validate_catalog(cls, catalog: Mapping[str, Any]) -> None:
        for resource_type, type_entry in catalog.items():
            if not isinstance(resource_type, str) or not resource_type.strip():
                raise ValueError("pricing_catalog resource types must be non-empty strings")
            if not isinstance(type_entry, Mapping):
                raise TypeError(
                    f"pricing_catalog['{resource_type}'] must be a mapping"
                )

            for variant, entry in type_entry.items():
                if not isinstance(variant, str) or not variant.strip():
                    raise ValueError(
                        f"pricing_catalog['{resource_type}'] variant names must be non-empty strings"
                    )
                if not isinstance(entry, Mapping):
                    raise TypeError(
                        f"pricing_catalog['{resource_type}']['{variant}'] must be a mapping"
                    )

                for key in (
                    "hourly",
                    "monthly",
                    "price_per_gb_month",
                    "monthly_base",
                ):
                    if key in entry:
                        value = entry[key]
                        if isinstance(value, bool) or not isinstance(value, Real):
                            raise TypeError(
                                f"Pricing value '{key}' for "
                                f"{resource_type}/{variant} must be numeric"
                            )
                        if float(value) < 0:
                            raise ValueError(
                                f"Pricing value '{key}' for "
                                f"{resource_type}/{variant} cannot be negative"
                            )

    @staticmethod
    def _resource_type(resource: Mapping[str, Any]) -> str:
        for key in _TYPE_KEYS:
            value = resource.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown"

    @classmethod
    def _lookup_price(
        cls,
        catalog: Mapping[str, Any],
        resource: Mapping[str, Any],
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """
        Resolve pricing using the UIR resource type hierarchy.

        Module 2 deliberately stores both the provider-native ``type`` and
        the provider-agnostic ``canonical_type``. Pricing is a downstream
        concern, so the lookup must try both identifiers rather than stopping
        at the provider-native type. This is what allows one catalog to be
        shared by Terraform and CloudFormation representations of the same
        infrastructure concept.
        """
        type_candidates: List[str] = []

        for key in ("canonical_type", "type", "resource_type"):
            value = resource.get(key)
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if normalized not in type_candidates:
                    type_candidates.append(normalized)

        # Preserve compatibility for callers/resources that only expose the
        # provider-native type.
        if not type_candidates:
            fallback_type = cls._resource_type(resource)
            if fallback_type != "unknown":
                type_candidates.append(fallback_type)

        # Variant selection: first match a configured property such as
        # instance_type, engine, or size.
        variant_candidates: List[str] = []
        for key in ("instance_type", "engine", "size", "sku", "class", "tier"):
            value = properties.get(key)
            if value is not None:
                variant_candidates.append(str(value))

        for resource_type in type_candidates:
            type_entry = catalog.get(resource_type)
            if not isinstance(type_entry, Mapping):
                continue

            for candidate in variant_candidates:
                entry = type_entry.get(candidate)
                if isinstance(entry, Mapping):
                    return entry

            # A generic/default entry is allowed.
            for key in ("default", "*"):
                entry = type_entry.get(key)
                if isinstance(entry, Mapping):
                    return entry

        return None

    @classmethod
    def _calculate_monthly_cost(
        cls,
        *,
        entry: Mapping[str, Any],
        properties: Mapping[str, Any],
        monthly_hours: float,
    ) -> Tuple[float, str]:
        quantity = cls._quantity(properties)

        if "monthly" in entry:
            return float(entry["monthly"]) * quantity, (
                f"monthly price × quantity ({quantity:g})"
            )

        if "monthly_base" in entry:
            base = float(entry["monthly_base"])
            return base * quantity, (
                f"monthly base price × quantity ({quantity:g})"
            )

        if "hourly" in entry:
            hourly = float(entry["hourly"])
            return hourly * monthly_hours * quantity, (
                f"hourly price × {monthly_hours:g} hours × quantity ({quantity:g})"
            )

        if "price_per_gb_month" in entry:
            gb = cls._storage_gb(properties)
            return float(entry["price_per_gb_month"]) * gb * quantity, (
                f"price/GB-month × {gb:g} GB × quantity ({quantity:g})"
            )

        raise CostAnalysisAgentError(
            "Pricing catalog entry contains no supported pricing field"
        )

    @staticmethod
    def _quantity(properties: Mapping[str, Any]) -> float:
        for key in _QUANTITY_KEYS:
            value = properties.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValueError(f"Resource quantity '{key}' must be numeric")
                number = float(value)
                if number <= 0:
                    raise ValueError(f"Resource quantity '{key}' must be greater than zero")
                return number
        return 1.0

    @staticmethod
    def _storage_gb(properties: Mapping[str, Any]) -> float:
        for key in ("storage_gb", "size_gb", "allocated_storage", "volume_size"):
            value = properties.get(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValueError(f"Storage property '{key}' must be numeric")
                number = float(value)
                if number < 0:
                    raise ValueError(f"Storage property '{key}' cannot be negative")
                return number
        return 0.0

    @classmethod
    def _optimization_recommendation(
        cls,
        *,
        resource: Mapping[str, Any],
        pricing_catalog: Mapping[str, Any],
        current_entry: Mapping[str, Any],
        properties: Mapping[str, Any],
        monthly_hours: float,
        currency: str,
    ) -> Tuple[str, float] | None:
        instance_type = properties.get("instance_type")
        if not isinstance(instance_type, str):
            return None

        type_candidates: List[str] = []
        for key in ("canonical_type", "type", "resource_type"):
            value = resource.get(key)
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if normalized not in type_candidates:
                    type_candidates.append(normalized)

        type_catalog = None
        for resource_type in type_candidates:
            candidate_catalog = pricing_catalog.get(resource_type)
            if isinstance(candidate_catalog, Mapping):
                type_catalog = candidate_catalog
                break

        if not isinstance(type_catalog, Mapping):
            return None

        ordered_variants = list(type_catalog.keys())
        if instance_type not in ordered_variants:
            return None

        current_index = ordered_variants.index(instance_type)
        if current_index <= 0:
            return None

        # The catalog order is explicitly treated as the evaluation order.
        # We only suggest the immediately preceding catalog option and never
        # assert that it is safe for the workload.
        candidate = ordered_variants[current_index - 1]
        candidate_entry = type_catalog.get(candidate)
        if not isinstance(candidate_entry, Mapping):
            return None

        candidate_cost, _ = cls._calculate_monthly_cost(
            entry=candidate_entry,
            properties=properties,
            monthly_hours=monthly_hours,
        )
        current_cost, _ = cls._calculate_monthly_cost(
            entry=current_entry,
            properties=properties,
            monthly_hours=monthly_hours,
        )

        if candidate_cost >= current_cost:
            return None

        return (
            f"Consider evaluating instance type '{candidate}' instead of "
            f"'{instance_type}' if workload requirements permit.",
            candidate_cost,
        )

    @staticmethod
    def _evidence_id(
        *,
        provider: str,
        rule_id: str,
        resource_id: str | None,
    ) -> str:
        raw = f"{provider}|{rule_id}|{resource_id or 'global'}"
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"cost:{safe}"


__all__ = ["CostAnalysisAgent", "CostAnalysisAgentError"]
