"""Security Validation Agent for Module 4.

Consumes normalized Module 3 ValidationReport objects and extracts security
findings produced by Checkov.  The agent deliberately stays independent of
Checkov's native JSON schema; the Module 3 adapter is responsible for
normalizing external tool output first.
"""

from __future__ import annotations

from typing import Iterable, Tuple

try:
    from .agent_result import AgentResult
    from .agent_schema import (
        AgentFinding,
        AgentSeverity,
        AgentStatus,
        AgentType,
    )
    from .base_agent import BaseAgent
    from ..module3_static_validation.validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )
except ImportError:  # pragma: no cover - supports simple local execution
    from agent_result import AgentResult
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from base_agent import BaseAgent
    from validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )


class SecurityValidationAgentError(Exception):
    """Raised when SecurityValidationAgent input is invalid."""


class SecurityValidationAgent(BaseAgent):
    """Extract and normalize security findings from Checkov reports."""

    agent_type = AgentType.SECURITY_VALIDATION

    _CHECKOV_TOOLS = {
        "CHECKOV",
        "CHECKOV_TERRAFORM",
        "CHECKOV-CHECK",
    }

    def validate_input(self, *args, **kwargs) -> None:
        validation_reports = kwargs.get("validation_reports")

        # Support both:
        #   agent.run(validation_reports)
        # and:
        #   agent.run(validation_reports=validation_reports)
        if validation_reports is None and args:
            validation_reports = args[0]

        if validation_reports is None:
            raise SecurityValidationAgentError(
                "validation_reports argument is required"
            )

        if isinstance(validation_reports, (str, bytes)):
            raise SecurityValidationAgentError(
                "validation_reports must be an iterable of ValidationReport objects"
            )

        try:
            reports = tuple(validation_reports)
        except TypeError as exc:
            raise SecurityValidationAgentError(
                "validation_reports must be an iterable of ValidationReport objects"
            ) from exc

        for index, report in enumerate(reports):
            if not isinstance(report, ValidationReport):
                raise SecurityValidationAgentError(
                    f"validation_reports[{index}] must be a ValidationReport, "
                    f"got {type(report).__name__}"
                )
        
    def execute(self, *args, **kwargs) -> AgentResult:
        validation_reports = kwargs.get("validation_reports")

        # Support both positional and keyword invocation.
        if validation_reports is None and args:
            validation_reports = args[0]

        validation_reports = tuple(validation_reports or ())

        findings = []
        evidence_ids = []

        for report in validation_reports:
            for finding in report.findings:
                if not self._is_security_finding(finding):
                    continue

                agent_finding = self._to_agent_finding(finding)

                findings.append(agent_finding)

                for evidence_id in agent_finding.evidence_ids:
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)

        if not findings:
            return AgentResult(
                agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                message="No Checkov security findings detected.",
                confidence=1.0,
                findings=tuple(),
                evidence_ids=tuple(),
                metadata={
                    "report_count": len(validation_reports),
                    "security_finding_count": 0,
                    "checkov_report_count": sum(
                        1
                        for report in validation_reports
                        if any(
                            self._tool_name(f.tool) in self._CHECKOV_TOOLS
                            for f in report.findings
                        )
                    ),
                },
            )

        confidence = sum(
            finding.confidence for finding in findings
        ) / len(findings)

        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            message=(
                f"Detected {len(findings)} Checkov security finding(s) "
                f"across {len(validation_reports)} validation report(s)."
            ),
            confidence=confidence,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            metadata={
                "report_count": len(validation_reports),
                "security_finding_count": len(findings),
                "critical_count": sum(
                    finding.severity == AgentSeverity.CRITICAL
                    for finding in findings
                ),
                "high_count": sum(
                    finding.severity == AgentSeverity.HIGH
                    for finding in findings
                ),
                "medium_count": sum(
                    finding.severity == AgentSeverity.MEDIUM
                    for finding in findings
                ),
                "low_count": sum(
                    finding.severity == AgentSeverity.LOW
                    for finding in findings
                ),
                "info_count": sum(
                    finding.severity == AgentSeverity.INFO
                    for finding in findings
                ),
            },
        )
    @classmethod
    def _tool_name(cls, tool) -> str:
        return str(tool).strip().upper().replace(" ", "_")

    @classmethod
    def _is_security_finding(cls, finding: ValidationFinding) -> bool:
        """Return True only for Checkov findings.

        Checkov is the Module 3 security/policy validator. Other tools such
        as Terraform Validate, CFN-Lint, and TFLint belong to other agents.
        """

        return cls._tool_name(finding.tool) in cls._CHECKOV_TOOLS

    @staticmethod
    def _map_severity(severity: ValidationSeverity) -> AgentSeverity:
        mapping = {
            ValidationSeverity.CRITICAL: AgentSeverity.CRITICAL,
            ValidationSeverity.HIGH: AgentSeverity.HIGH,
            ValidationSeverity.MEDIUM: AgentSeverity.MEDIUM,
            ValidationSeverity.LOW: AgentSeverity.LOW,
            ValidationSeverity.INFO: AgentSeverity.INFO,
            ValidationSeverity.NONE: AgentSeverity.NONE,
        }
        return mapping.get(severity, AgentSeverity.MEDIUM)

    @classmethod
    def _confidence_for(cls, finding: ValidationFinding) -> float:
        severity = cls._map_severity(finding.severity)

        if finding.status == ValidationStatus.FAILED:
            return {
                AgentSeverity.CRITICAL: 0.99,
                AgentSeverity.HIGH: 0.96,
                AgentSeverity.MEDIUM: 0.92,
                AgentSeverity.LOW: 0.88,
                AgentSeverity.INFO: 0.80,
                AgentSeverity.NONE: 0.75,
            }.get(severity, 0.90)

        if finding.status == ValidationStatus.WARNING:
            return 0.85

        if finding.status == ValidationStatus.ERROR:
            return 0.90

        if finding.status == ValidationStatus.SKIPPED:
            return 0.50

        return 0.80

    @staticmethod
    def _evidence_id(finding: ValidationFinding) -> str:
        parts = [
            "CHECKOV",
            finding.rule_id or "NO_RULE",
            finding.resource_id or "NO_RESOURCE",
            finding.file_path or "NO_FILE",
            str(finding.line or 0),
            str(finding.column or 0),
        ]

        safe_parts = []
        for part in parts:
            text = str(part).strip()
            text = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in text
            )
            safe_parts.append(text or "UNKNOWN")

        return ":".join(safe_parts)

    @classmethod
    def _to_agent_finding(cls, finding: ValidationFinding) -> AgentFinding:
        evidence_id = cls._evidence_id(finding)

        return AgentFinding(
            agent_type=AgentType.SECURITY_VALIDATION,
            severity=cls._map_severity(finding.severity),
            message=finding.message,
            confidence=cls._confidence_for(finding),
            evidence_ids=(evidence_id,),
            resource_id=finding.resource_id,
            rule_id=finding.rule_id,
            # AgentFinding intentionally contains only the shared
            # finding-level fields defined by Module 4's schema.
        )


__all__ = [
    "SecurityValidationAgent",
    "SecurityValidationAgentError",
]
