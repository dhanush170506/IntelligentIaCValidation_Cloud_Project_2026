from __future__ import annotations
from src.ml_model.module4_multi_agent.agent_result import AgentResult
from src.ml_model.module4_multi_agent.agent_schema import AgentFinding,AgentSeverity,AgentStatus,AgentType
from .consensus import ConsensusEngine,ConsensusLevel
from .remediation import BlastRadiusEngine,RemediationGate,RemediationRanker,GateDecision

def uir(): return {"provider":"Terraform","resources":[{"id":"db","provider":"Terraform","type":"aws_db_instance","canonical_type":"database","name":"db","properties":{}},{"id":"app","provider":"Terraform","type":"aws_instance","canonical_type":"compute_instance","name":"app","properties":{}},{"id":"api","provider":"Terraform","type":"aws_instance","canonical_type":"compute_instance","name":"api","properties":{}}],"dependencies":[{"source":"app","target":"db","relationship":"depends_on","provider":"Terraform"},{"source":"api","target":"app","relationship":"depends_on","provider":"Terraform"}]}
def finding(agent,evidence="e1",severity=AgentSeverity.HIGH): return AgentResult(agent_type=agent,status=AgentStatus.COMPLETED,message="ok",confidence=.9,findings=(AgentFinding(agent_type=agent,severity=severity,message="Database configuration insecure",confidence=.9,resource_id="db",rule_id="SEC",evidence_ids=(evidence,)),))
def test_evidence_quality_affects_score():
    """Evidence quality must be a real scoring factor, not display-only."""
    from .consensus import ConsensusEngine

    class Result:
        agent_type = type("Agent", (), {"value": "SECURITY_VALIDATION"})()

        def __init__(self, confidence=0.9):
            self.findings = (
                {
                    "resource_id": "r1",
                    "rule_id": "RULE-1",
                    "message": "security finding",
                    "severity": "HIGH",
                    "confidence": confidence,
                    "evidence_ids": ("high-quality",),
                },
            )

    engine = ConsensusEngine()

    high = engine.analyze(
        (Result(),),
        evidence_records=(
            {"evidence_id": "high-quality", "source": "CHECKOV", "quality": 1.0},
        ),
    )[0]

    low = engine.analyze(
        (Result(),),
        evidence_records=(
            {"evidence_id": "high-quality", "source": "CHECKOV", "quality": 0.0},
        ),
    )[0]

    assert high.factors["evidence_quality"] == 1.0
    assert low.factors["evidence_quality"] == 0.0
    assert high.score > low.score


def main():
 evidence=({"evidence_id":"e1","source":"AWS_CONFIG"},{"evidence_id":"e2","source":"CLOUDWATCH"})
 result=ConsensusEngine().analyze((finding(AgentType.SECURITY_VALIDATION,"e1"),finding(AgentType.DRIFT_DETECTION,"e2")),evidence)[0]
 assert result.level in (ConsensusLevel.CONSENSUS,ConsensusLevel.STRONG_CONSENSUS) and result.score<=1
 duplicate=ConsensusEngine().analyze((finding(AgentType.SECURITY_VALIDATION),finding(AgentType.DRIFT_DETECTION)),evidence)[0]
 assert len(duplicate.evidence_ids)==1
 blast=BlastRadiusEngine({"app":.9,"api":.2}).assess(uir(),"db")
 assert blast.direct_dependents==("app",) and blast.transitive_dependents==("api","app")
 proposal=RemediationGate().propose(resource_id="db",proposed_change={"desired":"encrypted"},blast_radius=blast,consensus=result,confidence=.95,risk=.1,evidence_ids=result.evidence_ids)
 assert proposal.decision in (GateDecision.REQUIRES_APPROVAL,GateDecision.AUTONOMOUSLY_ELIGIBLE)
 ranked=RemediationRanker().rank(({"option_id":"secure","security":.9,"reliability":.8,"cost":.2,"risk":.1,"blast":.1,"confidence":.9},{"option_id":"cheap","security":.3,"reliability":.4,"cost":.9,"risk":.5,"blast":.6,"confidence":.6}))
 assert ranked[0]["rank"]==1 and any(x["pareto_optimal"] for x in ranked)
 print("MODULE 7 UNIT TESTS: PASSED")
if __name__=="__main__":main()
