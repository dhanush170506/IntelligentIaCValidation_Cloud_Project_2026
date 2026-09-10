"""syntax_validation_agent.py.

Module 4 Syntax Validation Agent.

Consumes normalized Module 3 ValidationReport objects and translates
syntax/structural validation findings into Module 4 AgentFinding objects.
It does not execute Terraform, CFN-Lint, or any external validation tool.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
    from ..module3_static_validation.validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]
    from validation_schema import (  # type: ignore[no-redef]
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )

logger = logging.getLogger(__name__)


class SyntaxValidationAgentError(Exception):
    """Raised when SyntaxValidationAgent receives invalid input."""


class SyntaxValidationAgent(BaseAgent):
    """Interpret Module 3 findings that represent syntax/structural issues.

    Tool ownership remains in Module 3. This agent is an interpretation
    layer and therefore never launches an external process.
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SYNTAX_VALIDATION

    def validate_input(
        self,
        *,
        validation_reports: Iterable[ValidationReport] | None = None,
        **kwargs: Any,
    ) -> None:
        """Validate the reports supplied by the coordinator."""
        if validation_reports is None:
            raise SyntaxValidationAgentError(
                "validation_reports is required"
            )

        try:
            reports = tuple(validation_reports)
        except TypeError as exc:
            raise SyntaxValidationAgentError(
                "validation_reports must be an iterable of ValidationReport"
            ) from exc

        for index, report in enumerate(reports):
            if not isinstance(report, ValidationReport):
                raise SyntaxValidationAgentError(
                    f"validation_reports[{index}] must be a ValidationReport, "
                    f"got {type(report).__name__}"
                )

    def execute(
        self,
        *,
        validation_reports: Iterable[ValidationReport] | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Convert syntax-related Module 3 findings into AgentResult."""
        reports = tuple(validation_reports or ())
        findings: list[AgentFinding] = []
        evidence_ids: list[str] = []

        for report in reports:
            for finding in report.findings:
                if not self._is_syntax_finding(finding):
                    continue

                evidence_id = self._evidence_id(report, finding)
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)

                findings.append(
                    AgentFinding(
                        agent_type=self.agent_type,
                        severity=self._map_severity(finding),
                        message=finding.message,
                        resource_id=finding.resource_id,
                        rule_id=finding.rule_id,
                        evidence_ids=(evidence_id,),
                        confidence=self._confidence(finding),
                    )
                )

        confidence = (
            sum(f.confidence for f in findings) / len(findings)
            if findings
            else 1.0
        )

        message = (
            f"Syntax validation identified {len(findings)} syntax/structural finding(s)."
            if findings
            else "Syntax validation completed with no syntax/structural findings."
        )

        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            confidence=confidence,
            message=message,
            metadata={
                "report_count": len(reports),
                "syntax_finding_count": len(findings),
            },
        )

    
    @staticmethod
    def _is_syntax_finding(finding: ValidationFinding) -> bool:
        """
        Determine whether a validation finding represents a syntax/parsing issue.

        Terraform Validate and CFN-Lint are syntax-oriented tools.
        TFLint is broader, so only explicitly syntax/parser-related TFLint
        findings are classified as syntax findings.
        """

        tool = str(finding.tool).strip().upper()

        # Tools whose primary purpose includes syntax/template validation.
        syntax_tools = {
            "TERRAFORM_VALIDATE",
            "CFN_LINT",
            "CFN-LINT",
            "CFNLINT",
        }

        if tool in syntax_tools:
            return True

        # TFLint performs many kinds of checks, so inspect the rule/message.
        if tool == "TFLINT":
            rule_id = str(finding.rule_id or "").strip().upper()
            message = str(finding.message or "").strip().upper()

            syntax_tokens = (
                "SYNTAX",
                "PARSE",
                "PARSER",
                "MALFORMED",
            )

            return any(
                token in rule_id or token in message
                for token in syntax_tokens
            )

        # Checkov findings are security/policy findings, not syntax findings.
        return False

    @staticmethod
    def _map_severity(finding: ValidationFinding) -> AgentSeverity:
        mapping = {
            ValidationSeverity.CRITICAL: AgentSeverity.CRITICAL,
            ValidationSeverity.HIGH: AgentSeverity.HIGH,
            ValidationSeverity.MEDIUM: AgentSeverity.MEDIUM,
            ValidationSeverity.LOW: AgentSeverity.LOW,
            ValidationSeverity.INFO: AgentSeverity.INFO,
            ValidationSeverity.NONE: AgentSeverity.NONE,
        }
        return mapping[finding.severity]

    @staticmethod
    def _confidence(finding: ValidationFinding) -> float:
        """Assign deterministic confidence from validation status/severity."""
        if finding.status is ValidationStatus.ERROR:
            return 0.95
        if finding.status is ValidationStatus.FAILED:
            return 0.95
        if finding.status is ValidationStatus.WARNING:
            return 0.85
        if finding.status is ValidationStatus.SKIPPED:
            return 0.50
        return 0.90

    @staticmethod
    def _evidence_id(
        report: ValidationReport,
        finding: ValidationFinding,
    ) -> str:
        """Create a stable, deterministic evidence identifier."""
        parts = [
            report.provider,
            finding.tool,
            finding.rule_id or "NO_RULE",
            finding.resource_id or "NO_RESOURCE",
            finding.file_path or "NO_FILE",
            str(finding.line or 0),
            str(finding.column or 0),
        ]
        return "syntax:" + ":".join(
            SyntaxValidationAgent._sanitize(part) for part in parts
        )

    @staticmethod
    def _sanitize(value: str) -> str:
        return (
            str(value)
            .replace(":", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )


__all__ = ["SyntaxValidationAgent", "SyntaxValidationAgentError"]
