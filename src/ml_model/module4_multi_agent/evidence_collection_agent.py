"""evidence_collection_agent.py.

Module 4 Evidence Collection Agent.

Normalizes and packages supporting evidence produced by the other Module 4
agents. The agent is intentionally provider/API independent: it consumes
structured AgentResult objects and/or explicit evidence records and produces
deterministic evidence identifiers plus a standardized AgentResult.

This component does not call AWS, Terraform, Checkov, CloudWatch, Config,
Bedrock, or any external service. External evidence acquisition belongs to
the integrations that feed this agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Tuple

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


class EvidenceCollectionAgentError(Exception):
    """Raised for direct Evidence Collection Agent errors."""


class EvidenceCollectionAgent(BaseAgent):
    """Collect, normalize, deduplicate, and index agent evidence."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.EVIDENCE_COLLECTION

    def validate_input(
        self,
        *,
        agent_results: Any = None,
        evidence_records: Any = None,
        **kwargs: object,
    ) -> None:
        if agent_results is None and evidence_records is None:
            raise ValueError(
                "at least one of agent_results or evidence_records is required"
            )

        if agent_results is not None:
            if isinstance(agent_results, (str, bytes)) or not isinstance(
                agent_results, Iterable
            ):
                raise TypeError("agent_results must be an iterable of AgentResult")
            for index, result in enumerate(agent_results):
                if not isinstance(result, AgentResult):
                    raise TypeError(
                        f"agent_results[{index}] must be an AgentResult"
                    )

        if evidence_records is not None:
            if isinstance(evidence_records, (str, bytes)) or not isinstance(
                evidence_records, Iterable
            ):
                raise TypeError("evidence_records must be an iterable")
            for index, record in enumerate(evidence_records):
                self._validate_evidence_record(record, index)

    def execute(
        self,
        *,
        agent_results: Any = None,
        evidence_records: Any = None,
        **kwargs: object,
    ) -> AgentResult:
        results = list(agent_results or ())
        records = list(evidence_records or ())

        normalized: Dict[str, Dict[str, Any]] = {}

        # Evidence referenced by AgentFinding/AgentResult is preserved first.
        for result in results:
            for finding in result.findings:
                for evidence_id in finding.evidence_ids:
                    normalized.setdefault(
                        evidence_id,
                        self._record_from_finding(
                            evidence_id=evidence_id,
                            finding=finding,
                            source_status=result.status.value,
                        ),
                    )

            for evidence_id in result.evidence_ids:
                normalized.setdefault(
                    evidence_id,
                    {
                        "evidence_id": evidence_id,
                        "source": result.agent_type.value,
                        "status": result.status.value,
                        "resource_id": None,
                        "rule_id": None,
                        "severity": AgentSeverity.INFO.value,
                        "message": result.message,
                    },
                )

        # Explicit records may contain richer information. If an ID already
        # exists, merge non-empty fields without replacing deterministic IDs.
        for record in records:
            normalized_record = self._normalize_record(record)
            evidence_id = normalized_record["evidence_id"]

            if evidence_id not in normalized:
                normalized[evidence_id] = normalized_record
            else:
                normalized[evidence_id] = self._merge_records(
                    normalized[evidence_id], normalized_record
                )

        evidence_list = [
            normalized[key] for key in sorted(normalized)
        ]

        # Evidence itself is represented as metadata because AgentFinding's
        # schema is deliberately limited to observations.
        finding_count = sum(len(result.findings) for result in results)

        if evidence_list:
            confidence = min(
                0.98,
                0.90 + min(0.08, len(evidence_list) / 1000.0),
            )
            status = AgentStatus.COMPLETED
            message = (
                f"Evidence collection completed: {len(evidence_list)} "
                f"unique evidence item(s) indexed from {len(results)} "
                f"agent result(s) and {len(records)} explicit record(s)."
            )
        else:
            confidence = 1.0
            status = AgentStatus.COMPLETED
            message = "Evidence collection completed: no evidence items supplied."

        evidence_ids = tuple(item["evidence_id"] for item in evidence_list)

        return AgentResult(
            agent_type=self.agent_type,
            status=status,
            message=message,
            confidence=confidence,
            evidence_ids=evidence_ids,
            metadata={
                "evidence_count": len(evidence_list),
                "agent_result_count": len(results),
                "explicit_record_count": len(records),
                "finding_count": finding_count,
                "evidence": evidence_list,
            },
        )

    @staticmethod
    def _validate_evidence_record(record: Any, index: int) -> None:
        if not isinstance(record, Mapping):
            raise TypeError(
                f"evidence_records[{index}] must be a mapping"
            )

        evidence_id = record.get("evidence_id")
        if evidence_id is not None and (
            not isinstance(evidence_id, str) or not evidence_id.strip()
        ):
            raise ValueError(
                f"evidence_records[{index}]['evidence_id'] must be a non-empty string"
            )

        message = record.get("message")
        if message is not None and (
            not isinstance(message, str) or not message.strip()
        ):
            raise ValueError(
                f"evidence_records[{index}]['message'] must be a non-empty string"
            )

        # A record without an explicit ID is allowed. A deterministic ID will
        # be generated from its canonical content.
        for field in ("resource_id", "rule_id", "source"):
            value = record.get(field)
            if value is not None and not isinstance(value, str):
                raise TypeError(
                    f"evidence_records[{index}]['{field}'] must be a string"
                )

    @classmethod
    def _normalize_record(cls, record: Mapping[str, Any]) -> Dict[str, Any]:
        cleaned = {
            str(key): value
            for key, value in record.items()
            if value is not None
        }

        explicit_id = cleaned.get("evidence_id")
        if explicit_id:
            evidence_id = str(explicit_id).strip()
        else:
            evidence_id = cls._generated_evidence_id(cleaned)

        normalized: Dict[str, Any] = {
            "evidence_id": evidence_id,
            "source": str(cleaned.get("source", "EXPLICIT")).strip() or "EXPLICIT",
            "resource_id": cleaned.get("resource_id"),
            "rule_id": cleaned.get("rule_id"),
            "severity": cls._normalize_severity(cleaned.get("severity")),
            "message": str(
                cleaned.get("message", "Explicit evidence record")
            ).strip(),
        }

        # Preserve additional evidence attributes without changing the core
        # standardized fields.
        for key in sorted(cleaned):
            if key not in normalized and key != "evidence_id":
                normalized[key] = cleaned[key]

        return normalized

    @staticmethod
    def _normalize_severity(value: Any) -> str:
        if value is None:
            return AgentSeverity.INFO.value
        if isinstance(value, AgentSeverity):
            return value.value
        text = str(value).strip().upper()
        try:
            return AgentSeverity(text).value
        except ValueError:
            return AgentSeverity.INFO.value

    @staticmethod
    def _record_from_finding(
        *,
        evidence_id: str,
        finding: AgentFinding,
        source_status: str,
    ) -> Dict[str, Any]:
        return {
            "evidence_id": evidence_id,
            "source": finding.agent_type.value,
            "status": source_status,
            "resource_id": finding.resource_id,
            "rule_id": finding.rule_id,
            "severity": finding.severity.value,
            "message": finding.message,
            "confidence": finding.confidence,
        }

    @staticmethod
    def _merge_records(
        first: Mapping[str, Any],
        second: Mapping[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(first)

        for key, value in second.items():
            if key == "evidence_id":
                continue
            if value is not None and (
                key not in merged
                or merged[key] in (None, "", "UNKNOWN")
            ):
                merged[key] = value

        return merged

    @classmethod
    def _generated_evidence_id(cls, record: Mapping[str, Any]) -> str:
        canonical = cls._canonical_json(record)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        source = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(record.get("source", "EXPLICIT")).strip(),
        ).strip("_") or "EXPLICIT"
        return f"evidence:{source}:{digest}"

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )


__all__ = [
    "EvidenceCollectionAgent",
    "EvidenceCollectionAgentError",
]
