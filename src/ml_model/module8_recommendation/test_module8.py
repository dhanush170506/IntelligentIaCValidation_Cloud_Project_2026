from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.ml_model.module4_multi_agent.agent_result import AgentResult
from src.ml_model.module4_multi_agent.agent_schema import (
    AgentFinding,
    AgentSeverity,
    AgentStatus,
    AgentType,
)

from .engine import AssuranceRecommendationEngine


@dataclass(frozen=True)
class FakeDrift:
    category: str
    resource_id: str
    severity: str = "HIGH"
    confidence: float = 0.9
    telemetry_evidence_ids: tuple[str, ...] = ()

    def to_dict(self):
        return {
            "category": self.category,
            "resource_id": self.resource_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "telemetry_evidence_ids": self.telemetry_evidence_ids,
        }


class FakeDecision(str, Enum):
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class FakeProposal:
    resource_id: str
    decision: FakeDecision = FakeDecision.BLOCKED
    confidence: float = 0.9
    evidence_ids: tuple[str, ...] = ("e1",)
    evidence_id: str = "p1"
    blast_radius: dict = None

    def to_dict(self):
        return {
            "resource_id": self.resource_id,
            "decision": self.decision,
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "evidence_id": self.evidence_id,
            "blast_radius": self.blast_radius or {"evidence_id": "b1"},
        }


def security_result():
    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Security group permits unrestricted ingress",
        confidence=0.9,
        resource_id="sg",
        rule_id="SECURITY_INGRESS",
        evidence_ids=("e1",),
    )
    return AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.COMPLETED,
        message="ok",
        confidence=0.9,
        findings=(finding,),
    )


def build_engine():
    return AssuranceRecommendationEngine()


def main():
    engine = build_engine()
    evidence = ({"evidence_id": "e1", "source": "CHECKOV"},)

    # 1. Existing basic security path.
    result = security_result()
    report = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(result,),
        evidence=evidence,
    )
    assert report.security["score"] == 75
    assert len(report.recommendations) == 1
    assert report.recommendations[0]["evidence_ids"] == ["e1"]
    assert report.recommendations[0]["evidence_grounded"] is True

    # 2. Determinism.
    repeat = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(result,),
        evidence=evidence,
    )
    assert report.to_dict() == repeat.to_dict()

    # 3. Generator inputs must behave exactly like tuple inputs.
    generated = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(x for x in (result,)),
        evidence=(x for x in evidence),
        drift_assessments=(x for x in (FakeDrift(
            category="CONFIRMED_DRIFT",
            resource_id="server",
            telemetry_evidence_ids=("e2",),
        ),)),
    )
    assert generated.runtime["drift_count"] == 1
    assert generated.deployment_readiness["components"]["agent_failure_penalty"] == 0

    # 4. Unknown evidence IDs are never emitted in final recommendations.
    unknown = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Unknown evidence test",
        confidence=0.9,
        resource_id="sg",
        rule_id="SECURITY_INGRESS",
        evidence_ids=("e1", "UNKNOWN"),
    )
    unknown_result = AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.COMPLETED,
        message="ok",
        confidence=0.9,
        findings=(unknown,),
    )
    unknown_report = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(unknown_result,),
        evidence=evidence,
    )
    assert unknown_report.recommendations[0]["evidence_ids"] == ["e1"]
    # Verify evidence grounding directly instead of searching the entire JSON
    # for the literal token, which may legitimately occur in unrelated text.
    assert all(
        evidence_id in {"e1"}
        for evidence_id in unknown_report.recommendations[0]["evidence_ids"]
    )
    assert unknown_report.recommendations[0]["evidence_grounded"] is True

    # 5. POSSIBLE_DRIFT is intentionally suppressed as a configuration change.
    possible = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(),
        evidence=({"evidence_id": "e2", "source": "CLOUDWATCH"},),
        drift_assessments=(
            FakeDrift(
                category="POSSIBLE_DRIFT",
                resource_id="server",
                telemetry_evidence_ids=("e2",),
            ),
        ),
    )
    assert possible.recommendations == ()

    # 6. M7 remediation output is consumed and preserved by M8.
    proposal = FakeProposal(resource_id="server")
    m7 = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(),
        evidence=(
            {"evidence_id": "e1", "source": "CHECKOV"},
            {"evidence_id": "p1", "source": "MODULE7"},
            {"evidence_id": "b1", "source": "MODULE7"},
        ),
        proposals=(proposal,),
        rankings=(
            {
                "resource_id": "server",
                "option_id": "server-fix",
                "pareto_optimal": True,
                "evidence_id": "r1",
            },
        ),
        consensus=(
            {
                "resource_id": "server",
                "claim_key": "server|RULE1",
                "score": 0.9,
                "confidence": 0.9,
                "evidence_ids": ("e1",),
                "evidence_id": "c1",
            },
        ),
    )
    assert len(m7.recommendations) == 1
    m7_rec = m7.recommendations[0]
    assert m7_rec["module7_decision"] == "BLOCKED"
    assert m7_rec["pareto_optimal"] is True
    assert m7_rec["blast_radius"]["evidence_id"] == "b1"
    assert set(m7_rec["evidence_ids"]) == {"e1", "p1", "b1"}
    assert "r1" not in m7_rec["evidence_ids"]
    assert "c1" not in m7_rec["evidence_ids"]

    # 7. Failed agents affect deployment readiness.
    failed = AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.FAILED,
        message="validator failed",
        confidence=0.0,
        findings=(),
    )
    failed_report = engine.build(
        project="test",
        uir={"provider": "Terraform"},
        agent_results=(failed,),
        evidence=(),
    )
    assert failed_report.deployment_readiness["components"]["agent_failure_penalty"] == 15

    print("MODULE 8 UNIT TESTS: PASSED")


if __name__ == "__main__":
    main()
