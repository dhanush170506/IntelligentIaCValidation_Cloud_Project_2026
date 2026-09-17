from __future__ import annotations

from .bedrock_schema import BedrockResponse
from .recommendation_engine import RecommendationEngine
from .recommendation_schema import (
    RecommendationAction,
    RecommendationPriority,
    RecommendationReport,
)

from ..module4_multi_agent.agent_schema import (
    AgentFinding,
    AgentSeverity,
    AgentType,
)


FAILURES = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        FAILURES.append(message)


def make_response() -> BedrockResponse:
    return BedrockResponse(
        model_id="mock-model",
        text="Infrastructure requires remediation.",
        confidence=0.90,
    )


def test_schema() -> None:
    from .recommendation_schema import Recommendation

    recommendation = Recommendation(
        recommendation_id="recommendation:test",
        title="Fix security issue",
        description="Review the security configuration.",
        priority=RecommendationPriority.HIGH,
        action=RecommendationAction.FIX,
        rationale="A high-severity security finding was detected.",
        evidence_ids=("evidence:1",),
        resource_id="aws_security_group.web",
        confidence=0.95,
    )

    check(
        recommendation.to_dict()["priority"] == "HIGH",
        "Recommendation serializes priority",
    )

    check(
        recommendation.to_dict()["action"] == "FIX",
        "Recommendation serializes action",
    )

    check(
        recommendation.to_dict()["evidence_ids"]
        == ["evidence:1"],
        "Recommendation preserves evidence IDs",
    )


def test_generate_from_finding() -> None:
    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.HIGH,
        message="Security group allows unrestricted ingress.",
        confidence=0.95,
        evidence_ids=("evidence:security:1",),
        resource_id="aws_security_group.web",
    )

    result = type(
        "AgentResultFixture",
        (),
        {
            "findings": (finding,),
            "evidence_ids": (),
        },
    )()

    engine = RecommendationEngine()

    report = engine.generate(
        response=make_response(),
        agent_results=(result,),
        evidence=(
            {
                "evidence_id": "evidence:security:1",
                "severity": "HIGH",
                "message": "Unrestricted ingress",
            },
        ),
    )

    check(
        isinstance(report, RecommendationReport),
        "Returns RecommendationReport",
    )

    check(
        len(report.recommendations) == 1,
        "One recommendation generated",
    )

    recommendation = report.recommendations[0]

    check(
        recommendation.priority
        == RecommendationPriority.HIGH,
        "HIGH finding produces HIGH recommendation",
    )

    check(
        recommendation.action
        == RecommendationAction.FIX,
        "HIGH finding produces FIX action",
    )

    check(
        "evidence:security:1"
        in recommendation.evidence_ids,
        "Recommendation is evidence-grounded",
    )

    check(
        recommendation.resource_id
        == "aws_security_group.web",
        "Resource ID preserved",
    )


def test_invalid_evidence_not_invented() -> None:
    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.CRITICAL,
        message="Critical security issue.",
        confidence=0.99,
        evidence_ids=("real:evidence", "fake:evidence"),
    )

    result = type(
        "AgentResultFixture",
        (),
        {
            "findings": (finding,),
            "evidence_ids": (),
        },
    )()

    engine = RecommendationEngine()

    report = engine.generate(
        response=make_response(),
        agent_results=(result,),
        evidence=(
            {
                "evidence_id": "real:evidence",
            },
        ),
    )

    recommendation = report.recommendations[0]

    check(
        "real:evidence"
        in recommendation.evidence_ids,
        "Valid evidence ID preserved",
    )

    check(
        "fake:evidence"
        not in recommendation.evidence_ids,
        "Unknown evidence ID rejected",
    )


def test_confidence() -> None:
    finding = AgentFinding(
        agent_type=AgentType.SECURITY_VALIDATION,
        severity=AgentSeverity.MEDIUM,
        message="Review security configuration.",
        confidence=0.80,
    )

    result = type(
        "AgentResultFixture",
        (),
        {
            "findings": (finding,),
            "evidence_ids": (),
        },
    )()

    engine = RecommendationEngine()

    report = engine.generate(
        response=make_response(),
        agent_results=(result,),
    )

    check(
        0.80 <= report.overall_confidence <= 0.90,
        "Overall confidence combines model and finding confidence",
    )


def test_empty_results_rejected() -> None:
    engine = RecommendationEngine()

    try:
        engine.generate(
            response=make_response(),
            agent_results=(),
        )
        check(False, "Empty agent results rejected")
    except Exception:
        check(True, "Empty agent results rejected")


def test_deterministic_ids() -> None:
    finding = AgentFinding(
        agent_type=AgentType.COST_ANALYSIS,
        severity=AgentSeverity.LOW,
        message="Resource may be oversized.",
        confidence=0.75,
        evidence_ids=("cost:evidence:1",),
    )

    result = type(
        "AgentResultFixture",
        (),
        {
            "findings": (finding,),
            "evidence_ids": (),
        },
    )()

    engine = RecommendationEngine()

    report_a = engine.generate(
        response=make_response(),
        agent_results=(result,),
    )

    report_b = engine.generate(
        response=make_response(),
        agent_results=(result,),
    )

    check(
        report_a.recommendations[0].recommendation_id
        == report_b.recommendations[0].recommendation_id,
        "Recommendation IDs are deterministic",
    )


def main() -> int:
    print("=" * 72)
    print("MODULE 5.3 - RECOMMENDATION ENGINE UNIT TEST")
    print("=" * 72)

    test_schema()
    test_generate_from_finding()
    test_invalid_evidence_not_invented()
    test_confidence()
    test_empty_results_rejected()
    test_deterministic_ids()

    print()

    if FAILURES:
        print("FAILED")
        for failure in FAILURES:
            print(" -", failure)
        return 1

    print("ALL MODULE 5.3 RECOMMENDATION ENGINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())