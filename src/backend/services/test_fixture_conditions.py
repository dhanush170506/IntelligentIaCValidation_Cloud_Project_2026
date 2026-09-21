"""Per-fixture assertions for the benchmark evaluation path.

These tests run the ten independent fixtures through
``dataset_evaluation_service.evaluate_single_sample`` - i.e. the same code
path used by the backend benchmark evaluation - and prove that the
fixture-specific controlled conditions (shared with
``test_independent_fixtures.py`` via ``fixture_conditions.py``) actually
change the pipeline outcome.

No ground truth is passed into the pipeline: every assertion inspects what
the frozen M1-M9 pipeline produced under the controlled *inputs*.

Run from the project root:
    python -m pytest src/backend/services/test_fixture_conditions.py -v
"""
from __future__ import annotations

import pytest

from src.backend.services.dataset_evaluation_service import (
    aggregate_dataset_results,
    discover_dataset_samples,
    evaluate_single_sample,
)
from src.ml_model.assurance_pipeline.fixture_conditions import (
    FIXTURE_NAMES,
    SCENARIO_LABELS,
)


def _benchmark_samples() -> list[dict]:
    samples = discover_dataset_samples(dataset_name="independent_fixtures")
    assert len(samples) == 10
    return samples


@pytest.fixture(scope="module")
def evaluated() -> dict[str, dict]:
    """Evaluate all ten fixtures once; tests index by fixture filename."""
    return {
        sample["filename"]: evaluate_single_sample(sample)
        for sample in _benchmark_samples()
    }


def _agent_types(result: dict) -> set[str]:
    return {str(row.get("agent_type")) for row in result.get("findings", []) or []}


def _drift_categories(result: dict) -> set[str]:
    return set(result["evaluation_metrics"].get("drift_categories") or [])


def _agent_statuses(result: dict) -> dict[str, str]:
    return dict(result["evaluation_metrics"].get("agent_statuses") or {})


def test_discovery_covers_all_ten_fixtures():
    samples = _benchmark_samples()
    assert {sample["filename"] for sample in samples} == set(FIXTURE_NAMES)


# --- The nine required scenario assertions -------------------------------


def test_fixture_02_produces_security_finding(evaluated):
    result = evaluated["02_security_failure_terraform.tf"]
    assert "SECURITY_VALIDATION" in _agent_types(result)
    assert any(
        row.get("rule_id") == "CKV_AWS_24" and str(row.get("severity")).upper() == "HIGH"
        for row in result["findings"]
    )


def test_fixture_03_produces_validator_failure(evaluated):
    result = evaluated["03_validator_failure_terraform.tf"]
    statuses = _agent_statuses(result)
    # The controlled validator failure surfaces as a FAILED agent status and
    # an orchestrator warning - the same signals the fixture harness asserts.
    assert "FAILED" in statuses.values()
    assert statuses.get("SYNTAX_VALIDATION") == "FAILED"
    assert any(
        "controlled validator unavailable" in str(warning)
        for warning in result.get("warnings", [])
    )
    # The controlled failure is reported honestly; no fake findings appear.
    assert not [
        row for row in result["findings"]
        if row.get("agent_type") == "SECURITY_VALIDATION"
    ]


def test_fixture_04_produces_confirmed_drift(evaluated):
    result = evaluated["04_confirmed_drift_terraform.tf"]
    assert "CONFIRMED_DRIFT" in _drift_categories(result)
    assert (result["drift_score"] or 0) > 0


def test_fixture_05_produces_possible_drift(evaluated):
    result = evaluated["05_possible_drift_terraform.tf"]
    assert "POSSIBLE_DRIFT" in _drift_categories(result)
    assert "CONFIRMED_DRIFT" not in _drift_categories(result)


def test_fixture_06_produces_likely_drift(evaluated):
    result = evaluated["06_likely_drift_terraform.tf"]
    assert "LIKELY_DRIFT" in _drift_categories(result)


def test_fixture_07_produces_insufficient_evidence(evaluated):
    result = evaluated["07_runtime_unavailable_terraform.tf"]
    assert "INSUFFICIENT_EVIDENCE" in _drift_categories(result)
    assert (result["drift_score"] or 0) == 0


def test_fixture_08_produces_cost_findings(evaluated):
    result = evaluated["08_cost_optimization_terraform.tf"]
    assert "COST_ANALYSIS" in _agent_types(result)


def test_fixture_09_produces_consensus_output(evaluated):
    result = evaluated["09_consensus_terraform.tf"]
    assert result["evaluation_metrics"]["has_consensus"] is True


def test_fixture_10_produces_blast_radius_and_remediation(evaluated):
    result = evaluated["10_complex_manufacturing_terraform.tf"]
    metrics = result["evaluation_metrics"]
    assert metrics["blast_radius_count"] > 0
    assert metrics["remediation_ranking_count"] > 0


# --- Distinctness and honesty guarantees ---------------------------------


def test_fixtures_produce_genuinely_different_results(evaluated):
    """Reproduce the reported bug condition and assert it no longer holds."""
    signatures = {
        (
            result["status"],
            result["security_score"],
            result["drift_score"],
            round(result["confidence"], 2),
        )
        for result in evaluated.values()
    }
    # The old behavior: identical status/scores/confidence for every fixture.
    assert len(signatures) > 1, "all ten fixtures produced identical results"
    assert signatures != {("REVIEW_REQUIRED", 100, 0.0, 0.59)}


def test_fixture_04_drift_differs_from_clean_baseline(evaluated):
    clean = evaluated["01_clean_terraform.tf"]
    drift = evaluated["04_confirmed_drift_terraform.tf"]
    assert (clean["drift_score"] or 0) == 0
    assert (drift["drift_score"] or 0) > (clean["drift_score"] or 0)


def test_every_fixture_records_scenario_and_no_ground_truth(evaluated):
    for filename, result in evaluated.items():
        metrics = result["evaluation_metrics"]
        index = FIXTURE_NAMES.index(filename) + 1
        assert metrics["metric_type"] == "pipeline_generated"
        assert metrics["scenario"] == SCENARIO_LABELS[index]
        # Independent ground truth never enters the pipeline/evaluation input.
        assert result.get("ground_truth") is None


def test_evaluation_is_deterministic_per_fixture():
    samples = {s["filename"]: s for s in _benchmark_samples()}
    first = evaluate_single_sample(samples["04_confirmed_drift_terraform.tf"])
    second = evaluate_single_sample(samples["04_confirmed_drift_terraform.tf"])
    for key in ("status", "security_score", "drift_score", "confidence"):
        assert first[key] == second[key]


def test_aggregation_reflects_distinct_fixture_outcomes(evaluated):
    summary = aggregate_dataset_results(evaluated.values())
    assert summary["total_samples"] == 10
    assert summary["failed_samples"] == 0
    # Drift detections must reflect the real drift scenarios (04/05/06), not 0.
    assert summary["drift_detections"] >= 3
    assert summary["status_distribution"]
