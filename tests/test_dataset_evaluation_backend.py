from src.backend.services.dataset_evaluation_service import aggregate_dataset_results, discover_dataset_samples


def test_discover_dataset_samples_finds_repository_terraform_inputs():
    samples = discover_dataset_samples()
    assert samples
    assert any(sample["file_type"] == "terraform" for sample in samples)
    assert all("path" in sample for sample in samples)


def test_aggregate_dataset_results_counts_successful_samples():
    results = [
        {"status": "PASS", "security_score": 90.0, "confidence": 0.91, "drift_score": 12.0},
        {"status": "FAIL", "security_score": 40.0, "confidence": 0.61, "drift_score": 33.0},
        {"status": "ERROR", "security_score": None, "confidence": None, "drift_score": None},
    ]

    summary = aggregate_dataset_results(results)

    assert summary["total_samples"] == 3
    assert summary["successful_samples"] == 2
    assert summary["failed_samples"] == 1
    assert summary["average_security_score"] == 65.0
    assert summary["average_confidence"] == 0.76
