from src.ml_model.module6_runtime_telemetry import *
from src.ml_model.module6_runtime_telemetry.analysis import TelemetryIntentDriftAnalyzer
from src.ml_model.module4_multi_agent.drift_detection_agent import DriftDetectionAgent

def runtime(config=(), telemetry=(), errors=()): return RuntimeState(resources=tuple(config), telemetry=tuple(telemetry), collection_evidence=(), collection_errors=tuple(errors), timestamp="2026-01-01T00:00:00Z")
def uir(): return {"resources":[{"id":"aws_instance.web","type":"aws_instance","canonical_type":"compute_instance","properties":{"instance_type":"t3.micro"}}],"graph":{"edges":[]}}
def state(value, status=CollectionStatus.SUCCESS): return ConfigState(resource_id="aws_instance.web",resource_type="aws_instance",provider="AWS",configuration={"instance_type":value},collection_status=status)
def metric(value, stamp="2026-01-01T00:00:00Z"): return TelemetryDatum(resource_id="aws_instance.web",resource_type="aws_instance",metric_name="CPUUtilization",namespace="AWS/EC2",timestamp=stamp,value=value)
def main():
 a=TelemetryIntentDriftAnalyzer()
 assert a.analyze(uir(),runtime((state("t3.large"),),(metric(10),)))[0].category == DriftCategory.CONFIRMED_DRIFT
 assert a.analyze(uir(),runtime((state("t3.large",CollectionStatus.PARTIAL_SUCCESS),),(metric(10),)))[0].category == DriftCategory.LIKELY_DRIFT
 assert a.analyze(uir(),runtime((state("t3.micro"),),(metric(97),)))[0].category == DriftCategory.POSSIBLE_DRIFT
 assert a.analyze(uir(),runtime((state("t3.micro"),),(metric(10),)))[0].category == DriftCategory.NO_DRIFT
 assert a.analyze(uir(),runtime((state("t3.micro"),),()))[0].category == DriftCategory.INSUFFICIENT_EVIDENCE
 assert a.analyze(uir(),runtime((),(),(CollectionError(source="AWS_CONFIG",resource_id="aws_instance.web",code="UNAVAILABLE",message="no credentials"),)))[0].category == DriftCategory.INSUFFICIENT_EVIDENCE
 agent=DriftDetectionAgent().run(uir=uir(),runtime_state=runtime((),(),(CollectionError(source="AWS_CONFIG",resource_id="aws_instance.web",code="UNAVAILABLE",message="no credentials"),)))
 assert agent.findings[0].rule_id == "DRIFT_INSUFFICIENT_EVIDENCE"
 print("MODULE 6 SEMANTIC DRIFT TESTS: PASSED")
if __name__ == "__main__": main()
