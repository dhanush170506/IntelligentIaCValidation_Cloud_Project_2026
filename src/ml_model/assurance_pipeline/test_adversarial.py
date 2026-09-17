"""Failure-boundary and determinism regressions for the composed system."""
from pathlib import Path
from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.module6_runtime_telemetry import *
from src.ml_model.module6_runtime_telemetry.analysis import TelemetryIntentDriftAnalyzer
from src.ml_model.module8_recommendation.engine import AssuranceRecommendationEngine

class BrokenValidator:
 def validate(self, path): raise RuntimeError("tool unavailable")

def main():
 root=Path(__file__).resolve().parents[3]; template=root/"src/ml_model/module1_iac_parser/sample_terraform.tf"
 result=AssuranceOrchestrator(validators=(BrokenValidator(),)).run(iac_path=template)
 assert result.warnings and any(x.status.value=="FAILED" for x in result.agent_results)
 assert result.assurance_report.deployment_readiness["components"]["agent_failure_penalty"] >= 15
 # An unavailable Config collection travels into Module 4 as uncertainty,
 # never as a fabricated critical missing resource.
 failure=CollectionError(source="AWS_CONFIG",resource_id="aws_instance.web_server",code="UNAVAILABLE",message="credentials missing")
 runtime=RuntimeState(resources=(),telemetry=(),collection_evidence=(),collection_errors=(failure,),timestamp="t")
 result=AssuranceOrchestrator(runtime_collector=RuntimeStateCollector(MockConfigProvider(failures=(failure,)),MockCloudWatchProvider())).run(iac_path=template)
 drift_agent=next(x for x in result.agent_results if x.agent_type.value=="DRIFT_DETECTION")
 assert any(x.rule_id=="DRIFT_INSUFFICIENT_EVIDENCE" for x in drift_agent.findings)
 # Possible drift has no M8 configuration remediation.
 uir={"provider":"Terraform","resources":[{"id":"r","type":"aws_instance","canonical_type":"compute_instance","properties":{"x":1}}],"graph":{"edges":[]}}
 metric=TelemetryDatum(resource_id="r",resource_type="aws_instance",metric_name="CPUUtilization",namespace="AWS/EC2",timestamp="2026-01-01T00:00:00Z",value=99)
 state=ConfigState(resource_id="r",resource_type="aws_instance",provider="AWS",configuration={"x":1})
 assessment=TelemetryIntentDriftAnalyzer().analyze(uir,RuntimeState(resources=(state,),telemetry=(metric,),collection_evidence=(),collection_errors=(),timestamp="t"))[0]
 assert assessment.category.value=="POSSIBLE_DRIFT"
 report=AssuranceRecommendationEngine().build(project="p",uir=uir,agent_results=(),evidence=(),drift_assessments=(assessment,))
 assert not report.recommendations
 # Identical executions have stable final artifacts.
 a=AssuranceOrchestrator().run(iac_path=template); b=AssuranceOrchestrator().run(iac_path=template)
 assert a.assurance_report.to_json()==b.assurance_report.to_json() and a.uir==b.uir
 print("PHASE 3 ADVERSARIAL REGRESSIONS: PASSED")
if __name__=="__main__": main()
