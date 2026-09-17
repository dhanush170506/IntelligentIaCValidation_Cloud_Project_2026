from .evaluation import BenchmarkCase, ExperimentRunner, Metrics, default_dataset


def test_metrics():
    m = Metrics(tp=3, fp=1, fn=1, tn=5)
    assert round(m.precision, 6) == 0.75
    assert round(m.recall, 6) == 0.75
    assert round(m.f1, 6) == 0.75
    assert round(m.accuracy, 6) == 0.8


def test_dataset_is_independent():
    cases = default_dataset()
    assert len(cases) == 5
    assert all(c.iac_content for c in cases)
    assert all(isinstance(c.ground_truth["issue"], bool) for c in cases)


def test_independent_baseline():
    cases = default_dataset()

    def public_ingress_baseline(case):
        found = "0.0.0.0/0" in (case.iac_content or "")
        return {"issue": found, "probability": 0.9 if found else 0.1}

    report = ExperimentRunner().run(
        cases,
        public_ingress_baseline,
        configuration={"mode": "offline", "baseline": "public_ingress_rule"},
    )
    assert report.case_count == 5
    assert report.configuration["system_execution"] is False
    assert "brier_score" in report.calibration
    assert "security" in report.per_category


def test_deterministic_statistics():
    cases = default_dataset()

    def predictor(case):
        return {"issue": "security" in case.case_id, "probability": 0.8}

    runner = ExperimentRunner()
    a = runner.run(cases, predictor, configuration={"mode": "offline"})
    b = runner.run(cases, predictor, configuration={"mode": "offline"})
    assert a.experiment_id == b.experiment_id
    assert a.metrics == b.metrics
    assert a.per_category == b.per_category
    assert a.calibration == b.calibration
    assert a.confidence_intervals == b.confidence_intervals


def test_system_path_uses_module8_result_only():
    cases = default_dataset()[:1]

    class Recommendation:
        confidence = 0.9

    class AssuranceReport:
        recommendations = (Recommendation(),)

    class Result:
        assurance_report = AssuranceReport()

    class Orchestrator:
        def run(self, *, iac_path, project):
            assert iac_path
            return Result()

    report = ExperimentRunner().run_system(
        cases, Orchestrator(), configuration={"mode": "offline"}
    )
    assert report.configuration["evaluation_path"] == "M1-M8-orchestrator"
    assert report.configuration["prediction_source"] == "module8_assurance_report"
    assert report.cases[0]["predicted_issue"] is True
    assert report.cases[0]["probability"] == 0.9


def main():
    test_metrics()
    test_dataset_is_independent()
    test_independent_baseline()
    test_deterministic_statistics()
    test_system_path_uses_module8_result_only()
    print("MODULE 9 TESTS: PASSED")


if __name__ == "__main__":
    main()
