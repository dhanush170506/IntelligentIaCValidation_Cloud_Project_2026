"""Real-project, fully offline Module 1-8 integration verification.

This test executes the real local implementations from Modules 1-8.
External validators, Bedrock transport, AWS Config, and CloudWatch are
represented by the project's deterministic/offline contracts and mock
providers; no cloud or destructive operation is performed.
"""
from __future__ import annotations

from pathlib import Path

from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.graph_builder import GraphBuilder
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module3_static_validation.validation_result import build_report
from src.ml_model.module4_multi_agent.drift_detection_agent import DriftDetectionAgent
from src.ml_model.module4_multi_agent.evidence_collection_agent import (
    EvidenceCollectionAgent,
)
from src.ml_model.module5_llm_integration.bedrock_schema import BedrockResponse
from src.ml_model.module5_llm_integration.recommendation_engine import (
    RecommendationEngine,
)
from src.ml_model.module5_llm_integration.confidence_scoring import ConfidenceScorer
from src.ml_model.module6_runtime_telemetry import (
    ConfigState,
    MockCloudWatchProvider,
    MockConfigProvider,
    RuntimeStateCollector,
    TelemetryDatum,
    TelemetryIntentDriftAnalyzer,
)
from src.ml_model.module7_research_algorithms.consensus import ConsensusEngine
from src.ml_model.module7_research_algorithms.remediation import (
    BlastRadiusEngine,
    RemediationGate,
    RemediationRanker,
)
from src.ml_model.module8_recommendation.engine import AssuranceRecommendationEngine


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    sample = root / "src/ml_model/module1_iac_parser/sample_terraform.tf"

    # ------------------------------------------------------------------
    # M1: parse real IaC.
    # ------------------------------------------------------------------
    normalized = process_iac_file(str(sample))
    assert normalized["provider"] == "Terraform"
    assert normalized["resources"]

    # ------------------------------------------------------------------
    # M2: build UIR and the shared ResourceGraph.
    # ------------------------------------------------------------------
    uir = GraphBuilder().attach_graph(build_uir(normalized))
    assert uir["resources"]
    assert "graph" in uir
    assert len(uir["graph"]["nodes"]) == len(uir["resources"])

    target = uir["resources"][0]
    target_id = target["id"]

    # ------------------------------------------------------------------
    # M3: verify the standardized validation contract.
    # Real external binaries are intentionally not required for this
    # offline integration test.
    # ------------------------------------------------------------------
    validation_report = build_report(provider="Terraform", findings=[])
    assert validation_report.provider == "Terraform"

    # ------------------------------------------------------------------
    # M6: deterministic runtime state + telemetry, using mock providers.
    # ------------------------------------------------------------------
    desired = uir["resources"]
    states = [
        ConfigState(
            resource_id=r["id"],
            resource_type=r["type"],
            provider="AWS",
            configuration=dict(r["properties"]),
            capture_timestamp="2026-01-01T00:00:00Z",
        )
        for r in desired
    ]

    # Introduce a controlled runtime mismatch on the target resource.
    states[0] = ConfigState(
        resource_id=target_id,
        resource_type=target["type"],
        provider="AWS",
        configuration={
            **target["properties"],
            "instance_type": "t3.large",
        },
        capture_timestamp="2026-01-01T00:00:00Z",
    )

    metrics = [
        TelemetryDatum(
            resource_id=target_id,
            resource_type=target["type"],
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            timestamp="2026-01-01T00:00:00Z",
            value=96.0,
            unit="Percent",
        )
    ]

    runtime = RuntimeStateCollector(
        MockConfigProvider(states),
        MockCloudWatchProvider(metrics),
        timestamp="2026-01-01T00:00:00Z",
    ).collect(uir)

    assessments = TelemetryIntentDriftAnalyzer().analyze(uir, runtime)
    assert runtime.resources
    assert runtime.telemetry
    assert any(x.score > 0 for x in assessments)

    # ------------------------------------------------------------------
    # M4: real drift/evidence agents consume the M2/M6 outputs.
    # ------------------------------------------------------------------
    observed = {
        "resources": [
            {"id": x.resource_id, "properties": x.configuration}
            for x in runtime.resources
        ]
    }

    drift_result = DriftDetectionAgent().run(
        uir=uir,
        observed_state=observed,
        runtime_assessments=assessments,
    )
    assert drift_result.findings
    assert drift_result.metadata["runtime_telemetry_finding_count"] >= 1

    evidence_result = EvidenceCollectionAgent().run(
        agent_results=(drift_result,),
        explicit_evidence=(
            runtime.collection_evidence
            + tuple(x.to_dict() for x in assessments)
        ),
    )
    evidence_records = tuple(evidence_result.metadata["evidence"])
    assert evidence_records

    # ------------------------------------------------------------------
    # M5: deterministic recommendation/confidence outputs.
    # ------------------------------------------------------------------
    bedrock_response = BedrockResponse(
        model_id="offline",
        text="offline evidence analysis",
        confidence=0.9,
    )
    m5_report = RecommendationEngine().generate(
        response=bedrock_response,
        agent_results=(drift_result,),
        evidence=evidence_records,
    )
    confidence = ConfidenceScorer().score(
        (drift_result,),
        evidence_records=evidence_records,
    )
    assert m5_report.recommendations
    assert confidence.score > 0

    # ------------------------------------------------------------------
    # M7: consensus -> blast radius -> remediation gate -> ranking.
    # ------------------------------------------------------------------
    consensus_results = ConsensusEngine().analyze(
        (drift_result,),
        evidence_records=evidence_records,
    )
    assert consensus_results

    blast = BlastRadiusEngine(
        criticality={target_id: 0.8}
    ).assess(uir, target_id)

    proposal = RemediationGate().propose(
        resource_id=target_id,
        proposed_change={"instance_type": "t3.micro"},
        blast_radius=blast,
        consensus=consensus_results[0],
        confidence=confidence.score,
        risk=0.10,
        evidence_ids=tuple(
            str(x.get("evidence_id"))
            for x in evidence_records
            if x.get("evidence_id")
        ),
    )
    assert proposal.dry_run is True
    assert proposal.decision.value in {
        "AUTONOMOUSLY_ELIGIBLE",
        "REQUIRES_APPROVAL",
        "BLOCKED",
        "INSUFFICIENT_EVIDENCE",
    }

    rankings = RemediationRanker().rank(
        (
            {
                "option_id": target_id,
                "resource_id": target_id,
                "security": 0.90,
                "reliability": 0.85,
                "cost_efficiency": 0.80,
                "risk": 0.10,
                "blast": blast.blast_radius_score,
                "confidence": confidence.score,
            },
            {
                "option_id": f"{target_id}:conservative",
                "resource_id": target_id,
                "security": 0.75,
                "reliability": 0.80,
                "cost_efficiency": 0.60,
                "risk": 0.05,
                "blast": min(1.0, blast.blast_radius_score + 0.05),
                "confidence": 0.80,
            },
        )
    )
    assert len(rankings) == 2
    assert all("ranking_score" in x for x in rankings)

    # ------------------------------------------------------------------
    # M8: consume actual M4/M5/M6/M7 outputs and render the final report.
    # ------------------------------------------------------------------
    m8 = AssuranceRecommendationEngine().build(
        project="module8-real-project-integration",
        uir=uir,
        agent_results=(drift_result,),
        evidence=evidence_records,
        drift_assessments=assessments,
        consensus=consensus_results,
        proposals=(proposal,),
        rankings=rankings,
        confidence_assessment=confidence,
    )

    assert m8.provider == "Terraform"
    assert m8.recommendations
    assert m8.evidence
    assert m8.confidence

    # Verify M7 data survives into the final M8 recommendation.
    m7_recs = [
        r for r in m8.recommendations
        if r.get("rule_id") == "MODULE7_REMEDIATION"
    ]
    assert m7_recs
    final_m7 = m7_recs[0]
    assert final_m7["module7_decision"] == proposal.decision.value
    assert final_m7["blast_radius"]["evidence_id"] == blast.evidence_id
    assert final_m7["pareto_optimal"] is not None

    # Every final recommendation evidence ID must be grounded in M8's
    # supplied evidence registry.
    valid_ids = {
        str(x["evidence_id"])
        for x in evidence_records
        if x.get("evidence_id")
    }
    for recommendation in m8.recommendations:
        assert set(recommendation["evidence_ids"]) <= valid_ids

    # Deterministic repeated execution.
    repeat = AssuranceRecommendationEngine().build(
        project="module8-real-project-integration",
        uir=uir,
        agent_results=(drift_result,),
        evidence=evidence_records,
        drift_assessments=assessments,
        consensus=consensus_results,
        proposals=(proposal,),
        rankings=rankings,
        confidence_assessment=confidence,
    )
    assert m8.to_dict() == repeat.to_dict()

    print("MODULE 8 REAL PROJECT INTEGRATION TEST: PASSED")


if __name__ == "__main__":
    main()
