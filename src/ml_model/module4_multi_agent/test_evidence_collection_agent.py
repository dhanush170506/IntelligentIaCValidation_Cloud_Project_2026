"""Tests for Module 4 Evidence Collection Agent."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_result import AgentResult
from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
from evidence_collection_agent import EvidenceCollectionAgent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def make_result(
    *,
    resource_id: str = "aws_instance.web",
    evidence_id: str = "security:aws_instance.web",
) -> AgentResult:
    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Example security evidence",
        confidence=0.96,
        resource_id=resource_id,
        rule_id="CKV_TEST_001",
        evidence_ids=(evidence_id,),
    )
    return AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.COMPLETED,
        message="Security analysis completed.",
        confidence=0.96,
        findings=(finding,),
        evidence_ids=(evidence_id,),
    )


def main() -> None:
    agent = EvidenceCollectionAgent()

    result = agent.run(agent_results=[make_result()])
    check(result.agent_type == AgentType.EVIDENCE_COLLECTION, "Agent type is correct")
    check(result.status == AgentStatus.COMPLETED, "Evidence collection completes")
    check(result.metadata["evidence_count"] == 1, "Finding evidence is collected")
    check(
        result.evidence_ids == ("security:aws_instance.web",),
        "Existing evidence ID is preserved",
    )

    explicit = {
        "evidence_id": "telemetry:resource-001",
        "source": "AWS_CONFIG",
        "resource_id": "aws_instance.web",
        "rule_id": "CONFIG_DRIFT",
        "severity": "HIGH",
        "message": "Observed instance type differs from desired state.",
        "region": "us-east-1",
    }
    result = agent.run(evidence_records=[explicit])
    check(result.metadata["evidence_count"] == 1, "Explicit evidence record is collected")
    evidence = result.metadata["evidence"][0]
    check(evidence["region"] == "us-east-1", "Additional evidence fields are preserved")
    check(evidence["severity"] == "HIGH", "Evidence severity is normalized")

    # Duplicate evidence from a finding and explicit record is deduplicated
    # and enriched rather than counted twice.
    result = agent.run(
        agent_results=[make_result(evidence_id="shared-evidence")],
        evidence_records=[
            {
                "evidence_id": "shared-evidence",
                "source": "AWS_CONFIG",
                "region": "us-east-1",
            }
        ],
    )
    check(result.metadata["evidence_count"] == 1, "Duplicate evidence IDs are deduplicated")
    check(
        result.metadata["evidence"][0]["region"] == "us-east-1",
        "Duplicate evidence is enriched with explicit fields",
    )

    # Deterministic ID for records without an explicit ID.
    record = {
        "source": "CLOUDWATCH",
        "resource_id": "aws_instance.web",
        "rule_id": "CPU_SPIKE",
        "message": "CPU exceeded threshold.",
    }
    result1 = agent.run(evidence_records=[record])
    result2 = agent.run(evidence_records=[record])
    check(
        result1.evidence_ids == result2.evidence_ids,
        "Generated evidence IDs are deterministic",
    )

    # Input can contain both result-derived and explicit evidence.
    result = agent.run(
        agent_results=[make_result(evidence_id="agent-evidence")],
        evidence_records=[{"evidence_id": "runtime-evidence", "source": "AWS_CONFIG"}],
    )
    check(result.metadata["evidence_count"] == 2, "Multiple evidence sources are collected")
    check(result.metadata["agent_result_count"] == 1, "Agent result count is tracked")
    check(result.metadata["explicit_record_count"] == 1, "Explicit record count is tracked")
    check(result.metadata["finding_count"] == 1, "Finding count is tracked")

    empty = agent.run(evidence_records=[])
    check(empty.status == AgentStatus.COMPLETED, "Empty evidence set completes")
    check(empty.metadata["evidence_count"] == 0, "Empty evidence count is zero")
    check(empty.confidence == 1.0, "Empty evidence confidence is 1.0")

    invalid = agent.run(agent_results=[object()])
    check(invalid.status == AgentStatus.FAILED, "Invalid AgentResult input returns FAILED")

    invalid = agent.run(
        evidence_records=[
            {"evidence_id": "", "message": "invalid"}
        ]
    )
    check(invalid.status == AgentStatus.FAILED, "Invalid evidence ID returns FAILED")

    invalid = agent.run(
        evidence_records=[
            {"source": 123}
        ]
    )
    check(invalid.status == AgentStatus.FAILED, "Invalid evidence source returns FAILED")

    invalid = agent.run()
    check(invalid.status == AgentStatus.FAILED, "Missing all inputs returns FAILED")

    print("All Evidence Collection Agent tests PASSED.")


if __name__ == "__main__":
    main()
