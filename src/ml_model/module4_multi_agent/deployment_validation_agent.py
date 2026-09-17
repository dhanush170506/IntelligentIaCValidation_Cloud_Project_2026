"""deployment_validation_agent.py.

Module 4 Deployment Validation Agent.

Analyzes the Module 2 Unified Intermediate Representation (UIR) and its
resource/dependency information for deployment-readiness problems that are
not primarily syntax or security findings.

Checks include:
    - dependency references to unknown resources
    - self-dependencies
    - dependency cycles
    - dependency provider mismatches
    - duplicate dependency declarations
    - resources with missing/empty canonical type
    - resources with missing/empty properties
    - obvious unresolved Terraform-style resource references in properties

The agent produces only the standardized Module 4 AgentResult/AgentFinding
objects and does not call cloud APIs. Runtime deployment checks belong to
later telemetry/infrastructure integrations.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]


logger = logging.getLogger(__name__)

_TERRAFORM_REF_RE = re.compile(
    r"(?<![\w.-])(?:aws|azurerm|google|random|tls|local|module|data)"
    r"\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*"
)

_HIGH_RISK_CANONICAL_TYPES = {
    "compute_instance",
    "container_service",
    "load_balancer",
    "database",
    "storage_bucket",
    "security_group",
    "iam_role",
}


class DeploymentValidationAgentError(Exception):
    """Raised for direct Deployment Validation Agent programming/configuration errors."""


class DeploymentValidationAgent(BaseAgent):
    """Validate whether a UIR is structurally ready for deployment."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.DEPLOYMENT_VALIDATION

    def validate_input(self, *, uir: Any = None, **kwargs: object) -> None:
        if not isinstance(uir, Mapping):
            raise TypeError(
                f"uir must be a mapping/dictionary, got {type(uir).__name__}"
            )

        required = ("provider", "resources", "dependencies")
        missing = [key for key in required if key not in uir]
        if missing:
            raise ValueError(f"uir is missing required field(s): {', '.join(missing)}")

        if not isinstance(uir["resources"], (list, tuple)):
            raise TypeError("uir['resources'] must be a list or tuple")
        if not isinstance(uir["dependencies"], (list, tuple)):
            raise TypeError("uir['dependencies'] must be a list or tuple")

    def execute(self, *, uir: Any = None, **kwargs: object) -> AgentResult:
        if not isinstance(uir, Mapping):
            raise DeploymentValidationAgentError("validated uir unexpectedly unavailable")

        provider = str(uir["provider"]).strip()
        resources = list(uir["resources"])
        dependencies = list(uir["dependencies"])

        findings: List[AgentFinding] = []
        evidence_ids: List[str] = []
        evidence_seen: Set[str] = set()

        def add_finding(
            severity: AgentSeverity,
            message: str,
            *,
            resource_id: str | None = None,
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

        resource_map: Dict[str, Mapping[str, Any]] = {}
        for index, resource in enumerate(resources):
            if not isinstance(resource, Mapping):
                add_finding(
                    AgentSeverity.HIGH,
                    f"Resource at index {index} is not a mapping and cannot be deployed.",
                    rule_id="DEPLOYMENT_INVALID_RESOURCE",
                    confidence=0.99,
                )
                continue

            resource_id = str(resource.get("id", "")).strip()
            if not resource_id:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Resource at index {index} has no usable resource ID.",
                    rule_id="DEPLOYMENT_MISSING_RESOURCE_ID",
                    confidence=0.99,
                )
                continue

            if resource_id in resource_map:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Duplicate resource ID '{resource_id}' makes deployment ambiguous.",
                    resource_id=resource_id,
                    rule_id="DEPLOYMENT_DUPLICATE_RESOURCE_ID",
                    confidence=0.99,
                )
            else:
                resource_map[resource_id] = resource

            canonical_type = str(resource.get("canonical_type", "")).strip()
            if not canonical_type:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Resource '{resource_id}' has no canonical_type and cannot be reliably classified for deployment.",
                    resource_id=resource_id,
                    rule_id="DEPLOYMENT_MISSING_CANONICAL_TYPE",
                    confidence=0.98,
                )

            if "properties" not in resource or not isinstance(resource.get("properties"), Mapping):
                add_finding(
                    AgentSeverity.HIGH,
                    f"Resource '{resource_id}' has missing or invalid properties.",
                    resource_id=resource_id,
                    rule_id="DEPLOYMENT_INVALID_PROPERTIES",
                    confidence=0.97,
                )

        seen_dependencies: Set[Tuple[str, str, str, str]] = set()
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for index, dependency in enumerate(dependencies):
            if not isinstance(dependency, Mapping):
                add_finding(
                    AgentSeverity.HIGH,
                    f"Dependency at index {index} is not a mapping.",
                    rule_id="DEPLOYMENT_INVALID_DEPENDENCY",
                    confidence=0.99,
                )
                continue

            source = str(dependency.get("source", "")).strip()
            target = str(dependency.get("target", "")).strip()
            relationship = str(dependency.get("relationship", "depends_on")).strip()
            dep_provider = str(dependency.get("provider", "")).strip()

            if not source or not target:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Dependency at index {index} is missing source or target.",
                    rule_id="DEPLOYMENT_INVALID_DEPENDENCY",
                    confidence=0.99,
                )
                continue

            key = (source, target, relationship, dep_provider)
            if key in seen_dependencies:
                add_finding(
                    AgentSeverity.MEDIUM,
                    f"Duplicate dependency '{source}' -> '{target}' may cause redundant deployment ordering.",
                    resource_id=source,
                    rule_id="DEPLOYMENT_DUPLICATE_DEPENDENCY",
                    confidence=0.96,
                )
            seen_dependencies.add(key)

            if source == target:
                add_finding(
                    AgentSeverity.CRITICAL,
                    f"Resource '{source}' depends on itself, creating an impossible deployment dependency.",
                    resource_id=source,
                    rule_id="DEPLOYMENT_SELF_DEPENDENCY",
                    confidence=0.99,
                )

            if source not in resource_map:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Dependency source '{source}' does not exist in the UIR resources.",
                    resource_id=source,
                    rule_id="DEPLOYMENT_UNKNOWN_DEPENDENCY_SOURCE",
                    confidence=0.99,
                )

            if target not in resource_map:
                add_finding(
                    AgentSeverity.HIGH,
                    f"Dependency target '{target}' does not exist in the UIR resources.",
                    resource_id=source,
                    rule_id="DEPLOYMENT_UNKNOWN_DEPENDENCY_TARGET",
                    confidence=0.99,
                )

            if dep_provider and dep_provider.lower() != provider.lower():
                add_finding(
                    AgentSeverity.HIGH,
                    f"Dependency '{source}' -> '{target}' declares provider '{dep_provider}', "
                    f"but the UIR provider is '{provider}'.",
                    resource_id=source,
                    rule_id="DEPLOYMENT_PROVIDER_MISMATCH",
                    confidence=0.98,
                )

            if source in resource_map and target in resource_map and source != target:
                adjacency[source].append(target)

        # Detect directed dependency cycles with DFS.
        cycle_nodes = self._find_cycle_nodes(adjacency)
        for resource_id in sorted(cycle_nodes):
            add_finding(
                AgentSeverity.CRITICAL,
                f"Resource '{resource_id}' participates in a dependency cycle and cannot be deployed in a valid topological order.",
                resource_id=resource_id,
                rule_id="DEPLOYMENT_DEPENDENCY_CYCLE",
                confidence=0.99,
            )

        # Look for unresolved Terraform-style references inside resource properties.
        for resource_id, resource in resource_map.items():
            properties = resource.get("properties")
            if not isinstance(properties, Mapping):
                continue

            refs = sorted(self._collect_terraform_refs(properties))
            for ref in refs:
                parts = ref.split(".")
                if len(parts) < 3:
                    continue
                referenced_resource = ".".join(parts[:2])
                if referenced_resource not in resource_map:
                    add_finding(
                        AgentSeverity.HIGH,
                        f"Resource '{resource_id}' contains unresolved reference '{ref}'. "
                        f"The referenced resource '{referenced_resource}' is absent from the UIR.",
                        resource_id=resource_id,
                        rule_id="DEPLOYMENT_UNRESOLVED_REFERENCE",
                        confidence=0.97,
                    )

        # Confidence is deterministic so evaluation experiments are reproducible.
        if not findings:
            status = AgentStatus.COMPLETED
            confidence = 1.0
            message = (
                f"Deployment validation completed successfully for {provider}: "
                f"{len(resources)} resources and {len(dependencies)} dependencies "
                f"passed deployment-readiness checks."
            )
        else:
            status = AgentStatus.COMPLETED
            confidence = min(finding.confidence for finding in findings)
            message = (
                f"Deployment validation completed for {provider}: "
                f"{len(findings)} deployment-readiness finding(s) detected "
                f"across {len(resources)} resource(s) and {len(dependencies)} dependency(ies)."
            )

        return AgentResult(
            agent_type=self.agent_type,
            status=status,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            confidence=confidence,
            message=message,
            metadata={
                "provider": provider,
                "resource_count": len(resources),
                "dependency_count": len(dependencies),
                "finding_count": len(findings),
                "cycle_resource_count": len(cycle_nodes),
            },
        )

    @staticmethod
    def _collect_terraform_refs(value: Any) -> Set[str]:
        refs: Set[str] = set()
        if isinstance(value, str):
            refs.update(_TERRAFORM_REF_RE.findall(value))
        elif isinstance(value, Mapping):
            for nested in value.values():
                refs.update(DeploymentValidationAgent._collect_terraform_refs(nested))
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                refs.update(DeploymentValidationAgent._collect_terraform_refs(nested))
        return refs

    @staticmethod
    def _find_cycle_nodes(adjacency: Mapping[str, Iterable[str]]) -> Set[str]:
        state: Dict[str, int] = {}
        stack: List[str] = []
        cycle_nodes: Set[str] = set()

        def visit(node: str) -> None:
            state[node] = 1
            stack.append(node)

            for target in adjacency.get(node, ()):
                target_state = state.get(target, 0)
                if target_state == 0:
                    visit(target)
                elif target_state == 1:
                    if target in stack:
                        cycle_nodes.update(stack[stack.index(target):])

            stack.pop()
            state[node] = 2

        for node in adjacency:
            if state.get(node, 0) == 0:
                visit(node)

        return cycle_nodes

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
        return f"deployment:{safe}"
