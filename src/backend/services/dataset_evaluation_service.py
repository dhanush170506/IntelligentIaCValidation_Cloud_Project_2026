from __future__ import annotations

import csv
import json
import os
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.ml_model.assurance_pipeline.fixture_conditions import (
    SCENARIO_LABELS,
    build_fixture_orchestrator,
    fixture_index,
)
from src.ml_model.assurance_pipeline.orchestrator import AssuranceOrchestrator
from src.ml_model.module3_static_validation.checkov_adapter import CheckovAdapter
from src.ml_model.module3_static_validation.cfn_lint_adapter import CfnLintAdapter

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = REPO_ROOT / "dataset"
BENCHMARK_ROOT = REPO_ROOT / "benchmarks"

DEFAULT_DATASET_MAX_SAMPLES = int(os.getenv("DATASET_MAX_SAMPLES", "20"))


def _dataset_signal_path() -> Path:
    return DATASET_ROOT if DATASET_ROOT.exists() else REPO_ROOT / "dataset"


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _agent_finding_rows(agent_results: Any) -> list[dict[str, Any]]:
    """Flatten Module 4 AgentResults via their existing to_dict() schemas.

    Keeps agent_type, severity, rule_id, resource_id, message, evidence_ids
    and confidence. Fixes the previous behavior that silently dropped every
    finding because AgentFinding objects are not plain dicts.
    """
    rows: list[dict[str, Any]] = []
    for agent_result in agent_results or ():
        data = agent_result.to_dict() if hasattr(agent_result, "to_dict") else None
        if not isinstance(data, dict):
            continue
        agent_type = data.get("agent_type")
        for finding in data.get("findings", []) or []:
            if isinstance(finding, dict):
                row = dict(finding)
            elif hasattr(finding, "to_dict"):
                converted = finding.to_dict()
                row = dict(converted) if isinstance(converted, dict) else {}
            else:
                continue
            row.setdefault("agent_type", agent_type)
            rows.append(row)
    return rows


def _derive_drift_score(report: dict[str, Any], drift_assessments: Any) -> float:
    """Deterministic drift score (0-100), mirroring src/ml_model/api.py.

    Documented proxy mapping (not a learned score):
      - Preferred: average numeric DriftAssessment scores (pipeline 0..1)
        scaled to 0..100.
      - Fallback: AssuranceReport.runtime.drift_count -> 100 if > 0 else 0.
    """
    scores = [
        float(assessment.score)
        for assessment in (drift_assessments or ())
        if hasattr(assessment, "score") and isinstance(getattr(assessment, "score"), (int, float))
    ]
    if scores:
        return round(sum(scores) / len(scores) * 100, 1)
    runtime = report.get("runtime", {}) if isinstance(report.get("runtime"), dict) else {}
    try:
        drift_count = int(runtime.get("drift_count", 0) or 0)
    except (TypeError, ValueError):
        drift_count = 0
    return 100.0 if drift_count > 0 else 0.0


def _collect_pipeline_evidence(result: Any, fixture_idx: int) -> dict[str, Any]:
    """Honest per-sample evidence recorded from the frozen M1-M9 pipeline.

    No invented numbers: only statuses, categories and counts actually
    produced by the run, plus the fixture scenario label describing the
    controlled inputs (never a ground-truth label).
    """
    agent_statuses: dict[str, str] = {}
    for agent_result in getattr(result, "agent_results", ()) or ():
        data = agent_result.to_dict() if hasattr(agent_result, "to_dict") else None
        if isinstance(data, dict) and data.get("agent_type"):
            agent_statuses[str(data["agent_type"])] = str(data.get("status", ""))

    drift_categories: list[str] = []
    for assessment in getattr(result, "drift_assessments", ()) or ():
        data = assessment.to_dict() if hasattr(assessment, "to_dict") else None
        if isinstance(data, dict) and data.get("category"):
            drift_categories.append(str(data["category"]))

    evidence = {
        "metric_type": "pipeline_generated",
        "fixture_index": fixture_idx or None,
        "scenario": SCENARIO_LABELS.get(fixture_idx),
        "agent_statuses": agent_statuses,
        "drift_categories": sorted(set(drift_categories)),
        "has_consensus": bool(getattr(result, "consensus", None)),
        "blast_radius_count": len(getattr(result, "blast_radius_assessments", ()) or ()),
        "remediation_ranking_count": len(getattr(result, "remediation_rankings", ()) or ()),
        "pipeline_warning_count": len(getattr(result, "warnings", ()) or ()),
        "pipeline_error_count": len(getattr(result, "errors", ()) or ()),
    }
    return {key: value for key, value in evidence.items() if value is not None}


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def discover_dataset_samples(
    dataset_name: str | None = None,
    max_samples: int | None = None,
) -> list[dict[str, Any]]:
    """Discover repository dataset inputs that are compatible with the assurance pipeline.

    The repository includes two dataset forms:
      1. real IaC resources under dataset/terragoat-master/terraform and benchmarks/
      2. embedded metadata prompts in dataset/data.csv and dataset/test.csv.

    The CSV files are not directly executable IaC, but they still carry actual
    Terraform/CloudFormation source fragments that can be adapted into pipeline
    input. This function keeps the original source and path metadata while
    exposing a deterministic sample list for evaluation.
    """
    limit = max_samples if max_samples is not None else DEFAULT_DATASET_MAX_SAMPLES
    if limit is not None and limit <= 0:
        return []

    samples: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_sample(sample: dict[str, Any]) -> None:
        key = sample.get("sample_id") or sample.get("path") or sample.get("filename") or sample.get("source")
        if key and key in seen:
            return
        if key:
            seen.add(key)
        samples.append(sample)

    for tf_path in sorted(_dataset_signal_path().joinpath("terragoat-master", "terraform").rglob("*.tf")):
        rel = tf_path.relative_to(REPO_ROOT).as_posix()
        add_sample(
            {
                "sample_id": f"terragoat-{rel}",
                "dataset_name": "terragoat-master",
                "file_type": "terraform",
                "filename": tf_path.name,
                "path": str(tf_path),
                "relative_path": rel,
                "source": "terragoat-master/terraform",
                "content": None,
            }
        )

    for tf_path in sorted(BENCHMARK_ROOT.joinpath("independent_fixtures").glob("*.tf")):
        rel = tf_path.relative_to(REPO_ROOT).as_posix()
        add_sample(
            {
                "sample_id": f"benchmark-{rel}",
                "dataset_name": "independent_fixtures",
                "file_type": "terraform",
                "filename": tf_path.name,
                "path": str(tf_path),
                "relative_path": rel,
                "source": "benchmarks/independent_fixtures",
                "content": None,
            }
        )

    for csv_name in ("test.csv", "data.csv"):
        csv_path = DATASET_ROOT / csv_name
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                content = row.get("initial") or row.get("Reference output") or row.get("source")
                if not content:
                    continue
                if "resource " not in content and "AWSTemplateFormatVersion" not in content and "terraform {" not in content:
                    continue
                is_cloudformation = "AWSTemplateFormatVersion" in content or "Resources:" in content
                file_type = "cloudformation" if is_cloudformation else "terraform"
                filename = row.get("source") or row.get("filename") or f"{csv_name}-{index}.{ 'yaml' if is_cloudformation else 'tf'}"
                relative = f"dataset/{csv_name}#{index}"
                ground_truth_raw = row.get("expected") if row.get("expected") is not None else None
                add_sample(
                    {
                        "sample_id": f"csv-{csv_name}-{index}",
                        "dataset_name": csv_name,
                        "file_type": file_type,
                        "filename": filename,
                        "path": str(csv_path),
                        "relative_path": relative,
                        "source": csv_name,
                        "content": content,
                        "ground_truth": _as_bool(ground_truth_raw) if ground_truth_raw is not None else None,
                    }
                )

    ordered = sorted(samples, key=lambda item: item.get("relative_path") or item.get("filename") or item.get("sample_id"))
    if dataset_name:
        ordered = [sample for sample in ordered if sample.get("dataset_name") == dataset_name or sample.get("source") == dataset_name]
    if limit is not None:
        ordered = ordered[:limit]
    return ordered


def _get_sample_content(sample: dict[str, Any]) -> str:
    if sample.get("content"):
        return str(sample["content"])
    path = sample.get("path")
    if path:
        full_path = Path(path)
        if full_path.exists():
            return full_path.read_text(encoding="utf-8", errors="replace")
    raise FileNotFoundError(f"No evaluable content found for sample {sample.get('sample_id')}")


def evaluate_single_sample(sample: dict[str, Any], orchestrator: AssuranceOrchestrator | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    sample_path = sample.get("path")
    fixture_idx = fixture_index(sample_path) if sample_path else 0
    if orchestrator is None:
        if fixture_idx:
            # Benchmark fixture: run under the fixture's controlled conditions
            # (same mock inputs as the independent fixture harness).
            orchestrator, fixture_idx = build_fixture_orchestrator(sample_path)
        else:
            orchestrator = AssuranceOrchestrator(
                validators=(
                    CheckovAdapter(checkov_executable=os.getenv("CHECKOV_EXECUTABLE", "checkov")),
                    CfnLintAdapter(),
                )
            )

    sample_id = str(sample.get("sample_id") or uuid.uuid4())
    file_type = str(sample.get("file_type") or "terraform")
    filename = str(sample.get("filename") or sample.get("sample_id") or "dataset-sample")
    try:
        content = _get_sample_content(sample)
        suffix = ".yaml" if file_type == "cloudformation" else ".tf"
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            result = orchestrator.run(iac_path=temp_path, project=f"dataset-{sample_id}")
            report = result.assurance_report.to_dict()
            outcome = str(report.get("outcome") or "").upper()
            if outcome == "PASS":
                status = "PASS"
            elif outcome == "REVIEW":
                status = "REVIEW_REQUIRED"
            elif outcome == "FAIL":
                status = "FAIL"
            else:
                status = "PASS" if report.get("deployment_readiness", {}).get("score", 0) >= 80 else "REVIEW_REQUIRED" if report.get("deployment_readiness", {}).get("score", 0) >= 50 else "FAIL"
            security_score = report.get("security", {}).get("score", 0)
            drift_score = _derive_drift_score(report, result.drift_assessments)
            confidence = 0.0
            if result.confidence_assessment is not None:
                confidence = float(result.confidence_assessment.to_dict().get("score", 0.0) or 0.0)
            findings = _agent_finding_rows(result.agent_results)
            recommendations = report.get("recommendations", []) or []
            return {
                "sample_id": sample_id,
                "dataset_name": sample.get("dataset_name"),
                "filename": filename,
                "relative_path": sample.get("relative_path"),
                "file_type": file_type,
                "path": sample.get("path"),
                "source": sample.get("source"),
                "status": status,
                "security_score": _coerce_number(security_score),
                "drift_score": _coerce_number(drift_score),
                "confidence": _coerce_number(confidence),
                "findings": findings,
                "recommendations": recommendations,
                "ground_truth": sample.get("ground_truth"),
                "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
                "warnings": list(result.warnings),
                "errors": list(result.errors),
                "evaluation_metrics": _collect_pipeline_evidence(result, fixture_idx),
            }
        finally:
            temp_path.unlink(missing_ok=True)
    except Exception as exc:  # pragma: no cover - defensive behavior for large datasets
        return {
            "sample_id": sample_id,
            "dataset_name": sample.get("dataset_name"),
            "filename": filename,
            "relative_path": sample.get("relative_path"),
            "file_type": file_type,
            "path": sample.get("path"),
            "source": sample.get("source"),
            "status": "ERROR",
            "security_score": None,
            "drift_score": None,
            "confidence": None,
            "findings": [],
            "recommendations": [],
            "ground_truth": sample.get("ground_truth"),
            "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
            "warnings": [],
            "errors": [str(exc)],
            "evaluation_metrics": {
                "metric_type": "pipeline_generated",
                "fixture_index": fixture_idx or None,
                "scenario": SCENARIO_LABELS.get(fixture_idx),
            },
        }


def evaluate_dataset_samples(
    samples: Iterable[dict[str, Any]],
    *,
    dataset_name: str = "repository-dataset",
    max_samples: int | None = None,
) -> list[dict[str, Any]]:
    ordered = list(samples)
    if max_samples is not None and max_samples > 0:
        ordered = ordered[:max_samples]
    return [evaluate_single_sample(sample) for sample in ordered]


def aggregate_dataset_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    total = len(rows)
    status_counts = Counter(str(item.get("status") or "UNKNOWN").upper() for item in rows)
    successful = sum(1 for item in rows if str(item.get("status") or "").upper() not in {"ERROR", "UNKNOWN"})
    failed = sum(1 for item in rows if str(item.get("status") or "").upper() == "ERROR")

    security_values = [value for value in (_coerce_number(item.get("security_score")) for item in rows) if value is not None]
    confidence_values = [value for value in (_coerce_number(item.get("confidence")) for item in rows) if value is not None]
    drift_values = [value for value in (_coerce_number(item.get("drift_score")) for item in rows) if value is not None]

    severity_counts = Counter()
    for item in rows:
        for finding in item.get("findings", []) or []:
            severity = str(finding.get("severity") or finding.get("level") or "UNKNOWN").upper()
            severity_counts[severity] += 1
    drift_detections = sum(1 for item in rows if _coerce_number(item.get("drift_score")) not in (None, 0))

    summary = {
        "total_samples": total,
        "successful_samples": successful,
        "failed_samples": failed,
        "status_distribution": dict(sorted(status_counts.items())),
        "security_findings": sum(severity_counts.values()),
        "critical_findings": severity_counts.get("CRITICAL", 0),
        "high_findings": severity_counts.get("HIGH", 0),
        "medium_findings": severity_counts.get("MEDIUM", 0),
        "low_findings": severity_counts.get("LOW", 0),
        "average_security_score": round(sum(security_values) / len(security_values), 2) if security_values else None,
        "average_confidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None,
        "average_drift_score": round(sum(drift_values) / len(drift_values), 2) if drift_values else None,
        "drift_detections": drift_detections,
        "recommendations_total": sum(len(item.get("recommendations") or []) for item in rows),
        "processing_time_ms": round(sum(float(item.get("processing_time_ms") or 0) for item in rows), 2),
        "dataset_ground_truth_supported": False,
        "ground_truth_metrics": {},
    }

    labels = []
    for item in rows:
        value = _as_bool(item.get("ground_truth"))
        if value is not None:
            labels.append((value, str(item.get("status") or "").upper() in {"FAIL", "REVIEW_REQUIRED"}))
    if labels:
        tp = sum(1 for expected, predicted in labels if expected and predicted)
        fp = sum(1 for expected, predicted in labels if (not expected) and predicted)
        fn = sum(1 for expected, predicted in labels if expected and (not predicted))
        tn = sum(1 for expected, predicted in labels if (not expected) and (not predicted))
        total_predictions = tp + fp + fn + tn
        if total_predictions:
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            accuracy = (tp + tn) / total_predictions if total_predictions else 0.0
            summary["dataset_ground_truth_supported"] = True
            summary["ground_truth_metrics"] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "accuracy": round(accuracy, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            }
    return summary


def default_dataset_catalog() -> dict[str, list[str]]:
    available: dict[str, list[str]] = {}
    for dataset_name in ("terragoat-master", "independent_fixtures", "test.csv", "data.csv"):
        sample_ids = [
            sample.get("sample_id") or sample.get("relative_path") or sample.get("path") or sample.get("filename")
            for sample in discover_dataset_samples(dataset_name=dataset_name)
        ]
        available[dataset_name] = [str(item) for item in sample_ids if item is not None]
    return available
