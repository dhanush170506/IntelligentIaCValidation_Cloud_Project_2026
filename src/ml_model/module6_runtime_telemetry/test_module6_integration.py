"""Real-project, fully offline Module 1-6 integration verification."""
from __future__ import annotations

from pathlib import Path
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module2_uir.graph_builder import GraphBuilder
from src.ml_model.module3_static_validation.validation_result import build_report
from src.ml_model.module4_multi_agent.drift_detection_agent import DriftDetectionAgent
from src.ml_model.module4_multi_agent.evidence_collection_agent import EvidenceCollectionAgent
from src.ml_model.module5_llm_integration.bedrock_schema import BedrockResponse
from src.ml_model.module5_llm_integration.recommendation_engine import RecommendationEngine
from src.ml_model.module5_llm_integration.confidence_scoring import ConfidenceScorer
from src.ml_model.module6_runtime_telemetry import *


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    normalized = process_iac_file(str(root / "src/ml_model/module1_iac_parser/sample_terraform.tf"))
    uir = GraphBuilder().attach_graph(build_uir(normalized))
    assert build_report(provider="Terraform", findings=[]).provider == "Terraform"  # Module 3 contract
    desired = uir["resources"]
    states = [ConfigState(resource_id=r["id"], resource_type=r["type"], provider="AWS", configuration=dict(r["properties"]), capture_timestamp="2026-01-01T00:00:00Z") for r in desired]
    states[0] = ConfigState(resource_id=desired[0]["id"], resource_type=desired[0]["type"], provider="AWS", configuration={**desired[0]["properties"], "instance_type": "t3.large"}, capture_timestamp="2026-01-01T00:00:00Z")
    metrics = [TelemetryDatum(resource_id=desired[0]["id"], resource_type=desired[0]["type"], metric_name="CPUUtilization", namespace="AWS/EC2", timestamp="2026-01-01T00:00:00Z", value=96.0, unit="Percent")]
    runtime = RuntimeStateCollector(MockConfigProvider(states), MockCloudWatchProvider(metrics), timestamp="2026-01-01T00:00:00Z").collect(uir)
    assessments = TelemetryIntentDriftAnalyzer().analyze(uir, runtime)
    observed = {"resources": [{"id": x.resource_id, "properties": x.configuration} for x in runtime.resources]}
    drift = DriftDetectionAgent().run(uir=uir, observed_state=observed, runtime_assessments=assessments)
    evidence = EvidenceCollectionAgent().run(agent_results=(drift,), explicit_evidence=runtime.collection_evidence + tuple(x.to_dict() for x in assessments))
    records = tuple(evidence.metadata["evidence"])
    report = RecommendationEngine().generate(response=BedrockResponse(model_id="offline", text="offline evidence analysis", confidence=.9), agent_results=(drift,), evidence=records)
    confidence = ConfidenceScorer().score((drift,), evidence_records=records)
    assert runtime.resources and runtime.telemetry and any(x.score > 0 for x in assessments)
    assert drift.metadata["runtime_telemetry_finding_count"] >= 1 and report.recommendations and confidence.score > 0
    print("MODULE 6 REAL PROJECT INTEGRATION TEST: PASSED")


if __name__ == "__main__": main()
