"""Independent on-disk benchmark fixtures exercising the frozen M1--M9 path."""
from pathlib import Path
from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.assurance_pipeline.fixture_conditions import (
    FIXTURE_DIR as FIXTURES,
    FIXTURE_NAMES as NAMES,
    BrokenValidator,
    SecurityValidator,
    desired,
    fixture_options,
    instance,
    runtime,
)
from src.ml_model.module9_evaluation.evaluation import BenchmarkCase, ExperimentRunner
def execute(path,**kwargs): return AssuranceOrchestrator(**kwargs).run(iac_path=path,project=path.stem)
def category(result,path): return next(x.category.value for x in result.drift_assessments if x.resource_id==instance(desired(path))["id"])
def main():
    paths = [FIXTURES / x for x in NAMES]

    assert all(x.is_file() for x in paths)
    assert len({x.read_text() for x in paths}) == 10

    results = []

    for index, path in enumerate(paths, 1):
        options = fixture_options(path)

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