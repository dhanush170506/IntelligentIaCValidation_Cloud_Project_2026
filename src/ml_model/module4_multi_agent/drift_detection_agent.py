"""drift_detection_agent.py.

Module 4 Configuration Drift Detection Agent.

Compares desired configuration represented by the Module 2 UIR with an
observed/runtime state supplied by the caller.

The agent is intentionally cloud-provider/API independent. Runtime state can
come from AWS Config, CloudWatch, another inventory service, or a deterministic
mock in evaluation. This keeps Module 4 testable without cloud credentials.

Observed resource shape expected by this agent:
    {
        "id": "aws_instance.web_server",
        "properties": {...}
    }

A top-level observed state may be:
    {"resources": [...]}
or simply a list/tuple of resource mappings.

The comparison detects:
    - missing desired resources
    - unexpected observed resources
    - changed resource properties
    - property additions/removals
    - nested property changes

Each finding is represented using the shared Module 4 AgentFinding schema.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Set, Tuple

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]


logger = logging.getLogger(__name__)


class DriftDetectionAgentError(Exception):
    """Raised for direct Drift Detection Agent errors."""


class DriftDetectionAgent(BaseAgent):
    """Detect configuration drift between desired UIR and observed state."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.DRIFT_DETECTION

    def validate_input(
        self,
        *,
        uir: Any = None,
        observed_state: Any = None,
        runtime_state: Any = None,
        runtime_assessments: Any = None,
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

        if observed_state is None and runtime_state is not None:
            observed_state = {"resources": [{"id": x.resource_id, "properties": x.configuration} for x in getattr(runtime_state, "resources", ())]}
        if observed_state is None:
            raise ValueError("observed_state is required")

        if isinstance(observed_state, Mapping):
            if "resources" not in observed_state:
                raise ValueError(
                    "observed_state mapping must contain a 'resources' field"
                )
            if not isinstance(observed_state["resources"], (list, tuple)):
                raise TypeError(
                    "observed_state['resources'] must be a list or tuple"
                )
        elif not isinstance(observed_state, (list, tuple)):
            raise TypeError(
                "observed_state must be a mapping with 'resources', "
                "a list, or a tuple"
            )

        if runtime_assessments is not None and not isinstance(runtime_assessments, (list, tuple)):
            raise TypeError("runtime_assessments must be a list or tuple when supplied")

    def execute(
        self,
        *,
        uir: Any = None,
        observed_state: Any = None,
        runtime_state: Any = None,
        runtime_assessments: Any = None,
        **kwargs: object,
    ) -> AgentResult:
        if runtime_state is not None and observed_state is None:
            observed_state = {"resources": [{"id": x.resource_id, "properties": x.configuration} for x in getattr(runtime_state, "resources", ())]}
        if not isinstance(uir, Mapping):
            raise DriftDetectionAgentError("validated UIR is unavailable")

        desired_resources = list(uir["resources"])

        if isinstance(observed_state, Mapping):
            observed_resources = list(observed_state["resources"])
        else:
            observed_resources = list(observed_state)

        provider = str(uir.get("provider", "UNKNOWN")).strip() or "UNKNOWN"

        findings: List[AgentFinding] = []
        evidence_ids: List[str] = []
        evidence_seen: Set[str] = set()

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
                    evidence_ids=(evidence_id,),
                    resource_id=resource_id,
                    rule_id=rule_id,
                )
            )

        desired_map = self._index_resources(
            desired_resources,
            "desired",
            add_finding,
        )
        observed_map = self._index_resources(
            observed_resources,
            "observed",
            add_finding,
        )

        desired_ids = set(desired_map)
        observed_ids = set(observed_map)

        # A desired resource absent from runtime is a deployment/runtime drift.
        collection_errors = tuple(getattr(runtime_state, "collection_errors", ()))
        for resource_id in sorted(desired_ids - observed_ids):
            unavailable = any(getattr(error, "source", "") == "AWS_CONFIG" and getattr(error, "resource_id", None) in (None, resource_id) and getattr(error, "code", "") in {"API_ERROR", "UNAVAILABLE", "MALFORMED"} for error in collection_errors)
            unconfirmed = runtime_state is not None and not any(getattr(error, "source", "") == "AWS_CONFIG" and getattr(error, "resource_id", None) in (None, resource_id) and getattr(error, "code", "") == "NOT_FOUND" for error in collection_errors)
            if unavailable or unconfirmed:
                add_finding(AgentSeverity.INFO, f"Runtime presence for desired resource '{resource_id}' is insufficiently evidenced; it is not classified as drift.", resource_id=resource_id, rule_id="DRIFT_INSUFFICIENT_EVIDENCE", confidence=.25)
                continue
            add_finding(
                AgentSeverity.CRITICAL,
                f"Desired resource '{resource_id}' is missing from the observed runtime state.",
                resource_id=resource_id,
                rule_id="DRIFT_MISSING_RESOURCE",
                confidence=0.99,
            )

        # An observed resource not represented by IaC is unmanaged/unexpected.
        for resource_id in sorted(observed_ids - desired_ids):
            add_finding(
                AgentSeverity.HIGH,
                f"Observed resource '{resource_id}' is not present in the desired UIR.",
                resource_id=resource_id,
                rule_id="DRIFT_UNEXPECTED_RESOURCE",
                confidence=0.98,
            )

        # Compare desired and observed resources that exist in both states.
        for resource_id in sorted(desired_ids & observed_ids):
            desired = desired_map[resource_id]
            observed = observed_map[resource_id]

            desired_properties = desired.get("properties", {})
            observed_properties = observed.get("properties", {})

            if not isinstance(desired_properties, Mapping):
                desired_properties = {}
            if not isinstance(observed_properties, Mapping):
                observed_properties = {}

            differences = self._diff_properties(
                desired_properties,
                observed_properties,
            )

            for path, desired_value, observed_value, change_type in differences:
                severity = self._property_severity(path)
                message = (
                    f"Resource '{resource_id}' has configuration drift at "
                    f"'{path}': desired={desired_value!r}, observed={observed_value!r}."
                )
                if change_type == "added":
                    message = (
                        f"Resource '{resource_id}' has an unexpected runtime "
                        f"property at '{path}': observed={observed_value!r}."
                    )
                elif change_type == "removed":
                    message = (
                        f"Resource '{resource_id}' is missing desired property "
                        f"'{path}' in the observed state."
                    )

                add_finding(
                    severity,
                    message,
                    resource_id=resource_id,
                    rule_id="DRIFT_PROPERTY_CHANGE",
                    confidence=0.95,
                )

        # Module 6 may supply evidence-aware runtime assessments.  This is
        # additive: the long-standing configuration comparison above remains
        # unchanged when the optional extension is absent.
        for assessment in runtime_assessments or ():
            value = assessment.to_dict() if hasattr(assessment, "to_dict") else assessment
            if not isinstance(value, Mapping):
                continue
            category = str(value.get("category", "")).upper()
            if category in {"NO_DRIFT", "INSUFFICIENT_EVIDENCE", ""}:
                continue
            resource_id = value.get("resource_id")
            severity_text = str(value.get("severity", "LOW")).upper()
            try:
                severity = AgentSeverity(severity_text)
            except ValueError:
                severity = AgentSeverity.LOW
            score = float(value.get("score", 0.0))
            confidence = max(0.0, min(1.0, float(value.get("confidence", 0.5))))
            evidence_id = str(value.get("evidence_id") or self._evidence_id(
                provider=provider, rule_id="DRIFT_RUNTIME_TELEMETRY", resource_id=resource_id
            ))
            if evidence_id not in evidence_seen:
                evidence_seen.add(evidence_id)
                evidence_ids.append(evidence_id)
            findings.append(AgentFinding(
                agent_type=self.agent_type,
                severity=severity,
                message=(f"Runtime telemetry analysis classified resource '{resource_id}' as "
                         f"{category} (score={score:.3f})."),
                confidence=confidence,
                evidence_ids=(evidence_id,),
                resource_id=resource_id,
                rule_id="DRIFT_RUNTIME_TELEMETRY",
            ))

        if not findings:
            message = (
                f"Drift detection completed for {provider}: "
                f"{len(desired_resources)} desired resource(s) match the "
                f"{len(observed_resources)} observed resource(s)."
            )
            confidence = 1.0
        else:
            message = (
                f"Drift detection completed for {provider}: "
                f"{len(findings)} drift finding(s) detected across "
                f"{len(desired_resources)} desired and "
                f"{len(observed_resources)} observed resource(s)."
            )
            confidence = min(f.confidence for f in findings)

        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            confidence=confidence,
            message=message,
            metadata={
                "provider": provider,
                "desired_resource_count": len(desired_resources),
                "observed_resource_count": len(observed_resources),
                "finding_count": len(findings),
                "missing_resource_count": sum(
                    1 for f in findings if f.rule_id == "DRIFT_MISSING_RESOURCE"
                ),
                "unexpected_resource_count": sum(
                    1 for f in findings if f.rule_id == "DRIFT_UNEXPECTED_RESOURCE"
                ),
                "property_change_count": sum(
                    1 for f in findings if f.rule_id == "DRIFT_PROPERTY_CHANGE"
                ),
                "runtime_telemetry_finding_count": sum(
                    1 for f in findings if f.rule_id == "DRIFT_RUNTIME_TELEMETRY"
                ),
            },
        )

    @staticmethod
    def _index_resources(
        resources: Iterable[Any],
        state_name: str,
        add_finding: Any,
    ) -> Dict[str, Mapping[str, Any]]:
        indexed: Dict[str, Mapping[str, Any]] = {}

        for index, resource in enumerate(resources):
            if not isinstance(resource, Mapping):
                add_finding(
                    AgentSeverity.HIGH,
                    f"{state_name.capitalize()} resource at index {index} is not a mapping.",
                    resource_id=None,
                    rule_id="DRIFT_INVALID_RESOURCE",
                    confidence=0.99,
                )
                continue

            resource_id = str(resource.get("id", "")).strip()
            if not resource_id:
                add_finding(
                    AgentSeverity.HIGH,
                    f"{state_name.capitalize()} resource at index {index} has no usable resource ID.",
                    resource_id=None,
                    rule_id="DRIFT_INVALID_RESOURCE",
                    confidence=0.99,
                )
                continue

            if resource_id in indexed:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Duplicate {state_name} resource ID '{resource_id}' makes drift comparison ambiguous.",
                    resource_id=resource_id,
                    rule_id="DRIFT_DUPLICATE_RESOURCE_ID",
                    confidence=0.99,
                )
                continue

            indexed[resource_id] = resource

        return indexed

    @classmethod
    def _diff_properties(
        cls,
        desired: Mapping[str, Any],
        observed: Mapping[str, Any],
        prefix: str = "",
    ) -> List[Tuple[str, Any, Any, str]]:
        differences: List[Tuple[str, Any, Any, str]] = []

        all_keys = sorted(
            set(desired.keys()) | set(observed.keys()),
            key=lambda value: str(value),
        )

        for key in all_keys:
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text

            in_desired = key in desired
            in_observed = key in observed

            if not in_desired:
                differences.append((path, None, observed[key], "added"))
                continue

            if not in_observed:
                differences.append((path, desired[key], None, "removed"))
                continue

            desired_value = desired[key]
            observed_value = observed[key]

            if isinstance(desired_value, Mapping) and isinstance(observed_value, Mapping):
                differences.extend(
                    cls._diff_properties(desired_value, observed_value, path)
                )
            elif desired_value != observed_value:
                differences.append(
                    (path, desired_value, observed_value, "changed")
                )

        return differences

    @staticmethod
    def _property_severity(path: str) -> AgentSeverity:
        """Assign higher severity to properties likely to affect availability/security."""
        normalized = path.lower()

        critical_tokens = (
            "availability_zone",
            "subnet",
            "security_group",
            "iam",
            "role",
            "policy",
            "encryption",
            "engine",
            "instance_type",
        )
        if any(token in normalized for token in critical_tokens):
            return AgentSeverity.HIGH

        medium_tokens = (
            "port",
            "cidr",
            "network",
            "volume",
            "storage",
            "replica",
        )
        if any(token in normalized for token in medium_tokens):
            return AgentSeverity.MEDIUM

        return AgentSeverity.LOW

    @staticmethod
    def _evidence_id(
        *,
        provider: str,
        rule_id: str,
        resource_id: str | None,
    ) -> str:
        resource_part = resource_id or "global"
        raw = f"{provider}|{rule_id}|{resource_part}"
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"drift:{safe}"
