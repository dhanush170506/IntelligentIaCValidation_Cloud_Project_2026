"""Independent on-disk benchmark fixtures exercising the frozen M1--M9 path."""
from pathlib import Path
from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module6_runtime_telemetry import *
from src.ml_model.module9_evaluation.evaluation import BenchmarkCase, ExperimentRunner

ROOT=Path(__file__).resolve().parents[3]; FIXTURES=ROOT/"benchmarks/independent_fixtures"
NAMES=("01_clean_terraform.tf","02_security_failure_terraform.tf","03_validator_failure_terraform.tf","04_confirmed_drift_terraform.tf","05_possible_drift_terraform.tf","06_likely_drift_terraform.tf","07_runtime_unavailable_terraform.tf","08_cost_optimization_terraform.tf","09_consensus_terraform.tf","10_complex_manufacturing_terraform.tf")
class BrokenValidator:
 def validate(self,path): raise RuntimeError("controlled validator unavailable")
class SecurityValidator:
 def validate(self,path):
  from src.ml_model.module3_static_validation.validation_schema import ValidationFinding,ValidationSeverity,ValidationStatus
  from src.ml_model.module3_static_validation.validation_result import build_report
  return build_report(provider="Terraform",findings=(ValidationFinding(tool="checkov",provider="Terraform",rule_id="CKV_AWS_24",message="Controlled public ingress finding",severity=ValidationSeverity.HIGH,status=ValidationStatus.FAILED,resource_id="aws_security_group.public_control"),))
def desired(path): return build_uir(process_iac_file(str(path)))["resources"]
def instance(resources): return next(x for x in resources if x["type"]=="aws_instance")
def runtime(path,*,change=False,points=0,unavailable=False):
 resources=desired(path); states=[]; errors=[]; target=instance(resources)
 for item in resources:
  props=dict(item["properties"])
  if change and item["id"]==target["id"]: props["instance_type"]="t3.large"
  states.append(ConfigState(resource_id=item["id"],resource_type=item["type"],provider="AWS",configuration=props))
 if unavailable: states=[]; errors=[CollectionError(source="AWS_CONFIG",resource_id=None,code="UNAVAILABLE",message="controlled offline failure")]
 telemetry=tuple(TelemetryDatum(resource_id=target["id"],resource_type=target["type"],metric_name="CPUUtilization",namespace="AWS/EC2",timestamp=f"2026-01-01T0{i}:00:00Z",value=99 if points else 20) for i in range(max(1,points)))
 return RuntimeStateCollector(MockConfigProvider(states,errors),MockCloudWatchProvider(telemetry,errors))
def execute(path,**kwargs): return AssuranceOrchestrator(**kwargs).run(iac_path=path,project=path.stem)
def category(result,path): return next(x.category.value for x in result.drift_assessments if x.resource_id==instance(desired(path))["id"])
def main():
    paths = [FIXTURES / x for x in NAMES]

    assert all(x.is_file() for x in paths)
    assert len({x.read_text() for x in paths}) == 10

    results = []

    for index, path in enumerate(paths, 1):
        options = {
            "runtime_collector": runtime(
                path,
                change=index == 4,
                points=1 if index == 5 else 2 if index == 6 else 0,
                unavailable=index == 7,
            )
        }

        if index == 2:
            options["validators"] = (SecurityValidator(),)

        if index == 3:
            options["validators"] = (BrokenValidator(),)

        if index in (8, 10):
            options["pricing_catalog"] = {
                "compute_instance": {
                    "default": {
                        "monthly": 250
                    }
                }
            }

        result = execute(path, **options)

        assert result.uir["resources"]
        assert result.graph["nodes"]
        assert result.assurance_report

        results.append(result)

    assert any(
        x.agent_type.value == "SECURITY_VALIDATION" and x.findings
        for x in results[1].agent_results
    )

    assert any(
        x.status.value == "FAILED"
        for x in results[2].agent_results
    )

    assert category(results[3], paths[3]) == "CONFIRMED_DRIFT"
    assert category(results[4], paths[4]) == "POSSIBLE_DRIFT"
    assert category(results[5], paths[5]) == "LIKELY_DRIFT"
    assert category(results[6], paths[6]) == "INSUFFICIENT_EVIDENCE"

    assert any(
        x.agent_type.value == "COST_ANALYSIS" and x.findings
        for x in results[7].agent_results
    )

    assert results[8].consensus
    assert results[9].blast_radius_assessments
    assert results[9].remediation_rankings

    # Independent truth is deliberately authored false and is never
    # read from or passed into the assurance pipeline.
    eval_report = ExperimentRunner().run_system(
        tuple(
            BenchmarkCase(
                case_id=f"fixture-{i}",
                provider="Terraform",
                iac_format="terraform",
                iac_path=str(path),
                ground_truth={"issue": False},
            )
            for i, path in enumerate(paths, 1)
        ),
        AssuranceOrchestrator(),
    )

    assert eval_report.case_count == 10
    assert eval_report.configuration["evaluation_path"] == "M1-M8-orchestrator"

    # Each fixture is deterministic under identical mock inputs.
    again = execute(
        paths[3],
        runtime_collector=runtime(paths[3], change=True),
    )

    assert results[3].uir == again.uir
    assert (
        results[3].assurance_report.to_json()
        == again.assurance_report.to_json()
    )

    print("INDEPENDENT FIXTURE VALIDATION: PASSED")


if __name__ == "__main__":
    main()