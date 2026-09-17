from .confidence_scoring import ConfidenceScorer, ConfidenceScoringError
from ..module4_multi_agent.agent_result import AgentResult
from ..module4_multi_agent.agent_schema import (
    AgentFinding,
    AgentSeverity,
    AgentStatus,
    AgentType,
)

def result(agent_type, confidence=0.9, findings=(), evidence_ids=(), status=AgentStatus.COMPLETED):
    return AgentResult(agent_type=agent_type, status=status, message="ok", confidence=confidence,
                       findings=tuple(findings), evidence_ids=tuple(evidence_ids))


def finding(agent_type, resource="r1", rule="R1", evidence=("e1",), message="issue"):
    return AgentFinding(agent_type=agent_type, severity=AgentSeverity.HIGH, message=message,
                        confidence=0.9, resource_id=resource, rule_id=rule, evidence_ids=evidence)


def test_clean_high_confidence():
    s = ConfidenceScorer().score([
        result(AgentType.SYNTAX_VALIDATION, .95, evidence_ids=("syntax:1",)),
        result(AgentType.SECURITY_VALIDATION, .96, evidence_ids=("security:1",)),
    ], model_confidence=.92)
    assert s.score > .80
    assert s.label in {"HIGH", "VERY_HIGH"}
    assert s.model_confidence == .92


def test_evidence_improves_finding_confidence():
    f = finding(AgentType.SECURITY_VALIDATION)
    without = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9, findings=(f,))])
    with_evidence = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9, findings=(f,))],
                                              evidence_records=({"evidence_id": "e1", "source": "checkov"},))
    assert with_evidence.score > without.score


def test_missing_model_renormalizes_weights():
    s = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .8)])
    assert s.model_confidence is None
    assert abs(sum(s.metadata["weights"].values()) - 1.0) < 1e-9


def test_failed_agent_is_penalized():
    good = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9)])
    failed = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9),
                                       result(AgentType.COST_ANALYSIS, .9, status=AgentStatus.FAILED)])
    assert failed.score < good.score
    assert failed.execution_quality < 1.0


def test_same_finding_agrees():
    f1 = finding(AgentType.SECURITY_VALIDATION, message="Public ingress")
    f2 = finding(AgentType.DEPLOYMENT_VALIDATION, message="Public ingress")
    s = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, findings=(f1,)),
                                   result(AgentType.DEPLOYMENT_VALIDATION, findings=(f2,))])
    assert s.agent_agreement == 1.0


def test_unrelated_agents_are_neutral_not_disagreement():
    f1 = finding(AgentType.SECURITY_VALIDATION, rule="SEC", message="security")
    f2 = finding(AgentType.COST_ANALYSIS, rule="COST", message="cost")
    s = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, findings=(f1,)),
                                   result(AgentType.COST_ANALYSIS, findings=(f2,))])
    assert s.agent_agreement == .75


def test_recommendation_confidence_is_evidence_grounded():
    assessment = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9)])
    value = ConfidenceScorer().recommendation_confidence({"confidence": .5}, assessment)
    assert value == round((.5 + assessment.score) / 2, 6)


def test_stable_id():
    s = ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION, .9)])
    assert ConfidenceScorer.stable_assessment_id(s).startswith("confidence:")


def test_invalid_inputs():
    try:
        ConfidenceScorer().score([])
        assert False
    except ConfidenceScoringError:
        pass
    try:
        ConfidenceScorer().score([result(AgentType.SECURITY_VALIDATION)], model_confidence=1.1)
        assert False
    except ConfidenceScoringError:
        pass


if __name__ == "__main__":
    tests = [
        test_clean_high_confidence, test_evidence_improves_finding_confidence,
        test_missing_model_renormalizes_weights, test_failed_agent_is_penalized,
        test_same_finding_agrees, test_unrelated_agents_are_neutral_not_disagreement,
        test_recommendation_confidence_is_evidence_grounded, test_stable_id,
        test_invalid_inputs,
    ]
    for t in tests:
        t()
        print(f"[PASS] {t.__name__}")
    print("MODULE 5.4 UNIT TESTS: PASSED")
