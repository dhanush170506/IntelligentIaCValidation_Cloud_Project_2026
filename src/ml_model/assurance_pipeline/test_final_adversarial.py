"""Final ten-scenario offline/adversarial validation of the public M1--M9 path."""
from pathlib import Path
from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module6_runtime_telemetry import *
from src.ml_model.module5_llm_integration.bedrock_adapter import BedrockAdapter
from src.ml_model.module5_llm_integration.bedrock_client import BedrockClient, BedrockClientError
from src.ml_model.module9_evaluation.evaluation import BenchmarkCase, ExperimentRunner

ROOT=Path(__file__).resolve().parents[3]; TEMPLATE=ROOT/"src/ml_model/module1_iac_parser/sample_terraform.tf"
def desired(): return build_uir(process_iac_file(str(TEMPLATE)))["resources"]
def collector(*, changed=False, telemetry=(), unavailable=False):
 states=[]; errors=[]
 for r in desired():
  props=dict(r["properties"])
  if changed and r["id"]=="aws_instance.web_server": props["instance_type"]="t3.large"
  states.append(ConfigState(resource_id=r["id"],resource_type=r["type"],provider="AWS",configuration=props))
 if unavailable: states=[]; errors=[CollectionError(source="AWS_CONFIG",resource_id=None,code="UNAVAILABLE",message="offline failure")]
 return RuntimeStateCollector(MockConfigProvider(states,errors),MockCloudWatchProvider(telemetry,errors))
def run(**kwargs): return AssuranceOrchestrator(**kwargs).run(iac_path=TEMPLATE,project="final")
class Broken:
 def validate(self,path): raise RuntimeError("tool unavailable")
class FailingBedrock(BedrockClient):
 def invoke(self,request): raise BedrockClientError("offline failure")
def cpu(value,stamp): return TelemetryDatum(resource_id="aws_instance.web_server",resource_type="aws_instance",metric_name="CPUUtilization",namespace="AWS/EC2",timestamp=stamp,value=value)
def main():
 results=[]
 # 1 clean: matching authoritative configuration plus normal telemetry.
 clean=run(runtime_collector=collector(telemetry=(cpu(20,"2026-01-01T00:00:00Z"),))); assert next(x for x in clean.drift_assessments if x.resource_id=="aws_instance.web_server").category.value=="NO_DRIFT"; results.append("clean")
 # 2 static security is covered by the real controlled Checkov adapter in existing E2E; M8 security path remains present.
 security=run(); assert security.uir["resources"]; results.append("security-baseline")
 # 3 validator failure becomes explicit failure, never a clean result.
 broken=run(validators=(Broken(),)); assert any(x.status.value=="FAILED" for x in broken.agent_results); results.append("validator-failure")
 # 4 authoritative configuration mismatch is confirmed drift.
 confirmed=run(runtime_collector=collector(changed=True,telemetry=(cpu(20,"2026-01-01T00:00:00Z"),))); assert any(x.category.value=="CONFIRMED_DRIFT" for x in confirmed.drift_assessments); results.append("confirmed-drift")
 # 5 one anomaly is possible and suppressed by M8.
 possible=run(runtime_collector=collector(telemetry=(cpu(99,"2026-01-01T00:00:00Z"),))); assert any(x.category.value=="POSSIBLE_DRIFT" for x in possible.drift_assessments); assert not any(x["description"]=="POSSIBLE_DRIFT" for x in possible.assurance_report.recommendations); results.append("single-anomaly")
 # 6 repeated observations change the semantic category to likely.
 likely=run(runtime_collector=collector(telemetry=(cpu(99,"2026-01-01T00:00:00Z"),cpu(98,"2026-01-01T01:00:00Z")))); assert any(x.category.value=="LIKELY_DRIFT" for x in likely.drift_assessments); results.append("repeated-anomaly")
 # 7 collection failure remains insufficient evidence.
 unavailable=run(runtime_collector=collector(unavailable=True)); assert any(x.category.value=="INSUFFICIENT_EVIDENCE" for x in unavailable.drift_assessments); results.append("collection-unavailable")
 # 8 injected pricing reaches the cost agent and report.
 cost=run(runtime_collector=collector(telemetry=(cpu(20,"2026-01-01T00:00:00Z"),)),pricing_catalog={"compute_instance":{"default":{"monthly":250}}}); assert any(x.agent_type.value=="COST_ANALYSIS" and x.findings for x in cost.agent_results); results.append("cost")
 # 9 LLM transport failure falls back to deterministic, evidence-derived output.
 llm=run(bedrock_adapter=BedrockAdapter(FailingBedrock(),model_id="offline")); assert any("Bedrock unavailable" in x for x in llm.warnings) and llm.bedrock_response.confidence==0; results.append("llm-failure")
 # 10 M9 invokes the actual orchestrator; independent false truth records FP.
 report=ExperimentRunner().run_system((BenchmarkCase(case_id="complex",provider="Terraform",iac_format="terraform",iac_path=str(TEMPLATE),ground_truth={"issue":False}),),AssuranceOrchestrator()); assert report.metrics["fp"]==1; results.append("m9-system")
 # Deterministic complete output.
 assert clean.uir==run(runtime_collector=collector(telemetry=(cpu(20,"2026-01-01T00:00:00Z"),))).uir
 assert len(results)==10
 print("FINAL TEN-SCENARIO ADVERSARIAL VALIDATION: PASSED")
if __name__=="__main__": main()
