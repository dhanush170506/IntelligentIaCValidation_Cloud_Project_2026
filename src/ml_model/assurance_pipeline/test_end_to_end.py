"""Architecture regression tests for the real Module 1--9 data path."""
from pathlib import Path
import json
import subprocess
from unittest.mock import patch

from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.module7_research_algorithms.consensus import ConsensusEngine
from src.ml_model.module7_research_algorithms.remediation import BlastRadiusEngine, RemediationGate, RemediationRanker
from src.ml_model.module8_recommendation.engine import AssuranceRecommendationEngine
from src.ml_model.module9_evaluation.evaluation import BenchmarkCase, ExperimentRunner
from src.ml_model.module3_static_validation.checkov_adapter import CheckovAdapter
from src.ml_model.module3_static_validation import checkov_adapter
from src.ml_model.module6_runtime_telemetry import ConfigState, TelemetryDatum, MockConfigProvider, MockCloudWatchProvider, RuntimeStateCollector


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    template = root / "src/ml_model/module1_iac_parser/sample_terraform.tf"
    config = ConfigState(resource_id="aws_instance.web_server", resource_type="aws_instance", provider="AWS", configuration={"instance_type": "drifted"})
    telemetry = TelemetryDatum(resource_id="aws_instance.web_server", resource_type="aws_instance", metric_name="CPUUtilization", namespace="AWS/EC2", timestamp="2026-01-01T00:00:00Z", value=97.0)
    collector = RuntimeStateCollector(MockConfigProvider((config,)), MockCloudWatchProvider((telemetry,)))
    payload = json.dumps({"check_type":"terraform","results":{"passed_checks":[],"skipped_checks":[],"parsing_errors":[],"failed_checks":[{"check_id":"CKV_AWS_24","check_name":"Security group unrestricted ingress","severity":"HIGH","resource":"aws_security_group.web_sg","file_path":"main.tf","file_line_range":[1,5]}]}})
    completed = subprocess.CompletedProcess(args=["checkov"], returncode=1, stdout=payload, stderr="")
    with patch.object(checkov_adapter.subprocess, "run", return_value=completed):
        pipeline = AssuranceOrchestrator(validators=(CheckovAdapter(),), runtime_collector=collector, pricing_catalog={"compute_instance":{"default":{"monthly":120}}}).run(iac_path=template, project="integration")

    assert pipeline.metadata["stages"] == ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8")
    assert pipeline.uir["resources"] and pipeline.graph["nodes"]
    assert pipeline.validation_reports and pipeline.agent_results and pipeline.evidence
    assert any(x.agent_type.value == "SECURITY_VALIDATION" and x.findings for x in pipeline.agent_results)
    assert pipeline.bedrock_response is not None and pipeline.confidence_assessment is not None
    assert pipeline.runtime_state.telemetry and pipeline.drift_assessments is not None
    assert pipeline.assurance_report.recommendations

    # Genuine Module 7 objects change a Module 8 recommendation and preserve
    # the decision, evidence, blast-radius, and Pareto traceability.
    consensus = ConsensusEngine().analyze(pipeline.agent_results, pipeline.evidence)
    item = next(x for x in consensus if x.claim_key.split("|", 1)[0] != "global")
    rid = item.claim_key.split("|", 1)[0]
    blast = BlastRadiusEngine().assess(pipeline.uir, rid)
    proposal = RemediationGate().propose(resource_id=rid, proposed_change={"test": True}, blast_radius=blast, consensus=item, confidence=item.score, risk=1.0-item.score, evidence_ids=item.evidence_ids)
    ranking = RemediationRanker().rank(({"option_id": rid, "resource_id": rid, "security": item.score, "reliability": item.score, "cost": .5, "risk": 1-item.score, "blast": blast.blast_radius_score, "confidence": item.score},))
    report = AssuranceRecommendationEngine().build(project="m7-influence", uir=pipeline.uir, agent_results=pipeline.agent_results, evidence=pipeline.evidence, consensus=(item,), proposals=(proposal,), rankings=ranking)
    m7 = [x for x in report.recommendations if x.get("rule_id") == "MODULE7_REMEDIATION"]
    assert len(m7) == 1 and m7[0]["module7_decision"] == proposal.decision.value and m7[0]["pareto_optimal"] == ranking[0]["pareto_optimal"]

    # Module 9 executes the orchestrator. The false ground truth deliberately
    # differs from the predicted output, proving it cannot be copied into it.
    case = BenchmarkCase(case_id="independent-negative", provider="Terraform", iac_format="terraform", iac_path=str(template), ground_truth={"issue": False})
    evaluation = ExperimentRunner().run_system((case,), AssuranceOrchestrator())
    assert evaluation.configuration["evaluation_path"] == "M1-M8-orchestrator"
    assert evaluation.metrics["fp"] == 1 and evaluation.metrics["f1"] == 0.0
    print("MODULE 1-9 ARCHITECTURE INTEGRATION: PASSED")


if __name__ == "__main__":
    main()
