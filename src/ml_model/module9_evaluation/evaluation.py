from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable, Mapping, Sequence


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return getattr(value, "value")
    return value


def _fingerprint(payload: Any, prefix: str = "module9") -> str:
    raw = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), default=str
    )
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


@dataclass(frozen=True, kw_only=True)
class BenchmarkCase:
    case_id: str
    provider: str
    iac_format: str
    ground_truth: dict[str, Any]
    iac_path: str | None = None
    iac_content: str | None = None
    project: str = "benchmark"

    def __post_init__(self) -> None:
        if not self.case_id or not self.provider or not self.iac_format:
            raise ValueError("case_id/provider/iac_format are required")
        if not isinstance(self.ground_truth, dict):
            raise ValueError("ground_truth must be a dictionary")
        if not isinstance(self.ground_truth.get("issue"), bool):
            raise ValueError("ground_truth['issue'] must be boolean")
        if self.iac_path is None and self.iac_content is None:
            raise ValueError("iac_path or iac_content is required")


@dataclass(frozen=True, kw_only=True)
class Metrics:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        return (
            2 * self.precision * self.recall / (self.precision + self.recall)
            if self.precision + self.recall
            else 0.0
        )

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "accuracy": round(self.accuracy, 6),
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
        }


@dataclass(frozen=True, kw_only=True)
class CaseResult:
    case_id: str
    category: str
    expected_issue: bool
    predicted_issue: bool
    probability: float
    correct: bool
    error_category: str | None
    latency_ms: float
    recommendation_count: int
    execution_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class ResearchReport:
    experiment_id: str
    case_count: int
    metrics: dict[str, Any]
    latency: dict[str, float]
    errors: dict[str, int]
    per_category: dict[str, Any]
    calibration: dict[str, float]
    confidence_intervals: dict[str, Any]
    configuration: dict[str, Any]
    cases: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def to_markdown(self) -> str:
        return (
            "# Module 9 Research Evaluation\n\n"
            f"Experiment: `{self.experiment_id}`\n\n"
            f"Cases: **{self.case_count}**\n\n"
            "| Metric | Value |\n|---|---:|\n"
            f"| Accuracy | {self.metrics['accuracy']} |\n"
            f"| Precision | {self.metrics['precision']} |\n"
            f"| Recall | {self.metrics['recall']} |\n"
            f"| F1 | {self.metrics['f1']} |\n"
            f"| Mean latency (ms) | {self.latency['mean_ms']} |\n"
            f"| Median latency (ms) | {self.latency['median_ms']} |\n"
            f"| Brier score | {self.calibration['brier_score']} |\n"
            f"| ECE | {self.calibration['ece']} |\n"
        )


class ExperimentRunner:
    """Research evaluator.

    ``run_system`` is the authoritative path for evaluating Modules 1-8.
    Ground truth is never passed to the orchestrator or used to construct the
    prediction. ``run`` is retained for independent baselines.
    """

    def run(
        self,
        cases: Iterable[BenchmarkCase],
        predict: Callable[[BenchmarkCase], Mapping[str, Any]],
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> ResearchReport:
        return self._evaluate(cases, predict, configuration=configuration, system=False)

    def run_system(
        self,
        cases: Iterable[BenchmarkCase],
        orchestrator: Any,
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> ResearchReport:
        cases = tuple(cases)

        def predict(case: BenchmarkCase) -> Mapping[str, Any]:
            with self._materialize(case) as path:
                result = orchestrator.run(iac_path=path, project=case.project)

            assurance = getattr(result, "assurance_report", None)
            recommendations = tuple(
                getattr(assurance, "recommendations", ()) or ()
            )
            values = []
            for rec in recommendations:
                raw = (
                    rec.get("confidence")
                    if isinstance(rec, Mapping)
                    else getattr(rec, "confidence", None)
                )
                if raw is None:
                    raw = rec.get("score") if isinstance(rec, Mapping) else getattr(rec, "score", None)
                if raw is not None:
                    try:
                        values.append(_clip(float(raw)))
                    except (TypeError, ValueError):
                        pass

            probability = statistics.mean(values) if values else (1.0 if recommendations else 0.0)
            return {
                "issue": bool(recommendations),
                "probability": probability,
                "recommendation_count": len(recommendations),
            }

        cfg = {
            **dict(configuration or {}),
            "evaluation_path": "M1-M8-orchestrator",
            "prediction_source": "module8_assurance_report",
            "ground_truth_source": "independent_benchmark_metadata",
        }
        return self._evaluate(cases, predict, configuration=cfg, system=True)

    def compare_baselines(
        self,
        cases: Iterable[BenchmarkCase],
        predictors: Mapping[str, Callable[[BenchmarkCase], Mapping[str, Any]]],
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> dict[str, ResearchReport]:
        return {
            name: self.run(
                cases,
                predictors[name],
                configuration={**dict(configuration or {}), "baseline": name},
            )
            for name in sorted(predictors)
        }

    def ablation(
        self,
        cases: Iterable[BenchmarkCase],
        orchestrators: Mapping[str, Any],
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> dict[str, ResearchReport]:
        return {
            name: self.run_system(
                cases,
                orchestrators[name],
                configuration={**dict(configuration or {}), "ablation": name},
            )
            for name in sorted(orchestrators)
        }

    def _evaluate(
        self,
        cases: Iterable[BenchmarkCase],
        predict: Callable[[BenchmarkCase], Mapping[str, Any]],
        *,
        configuration: Mapping[str, Any] | None,
        system: bool,
    ) -> ResearchReport:
        cases = tuple(cases)
        if not cases:
            raise ValueError("At least one benchmark case is required")

        counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        rows = []
        errors: dict[str, int] = {}
        latencies = []

        for case in cases:
            start = time.perf_counter()
            execution_ok = True
            recommendation_count = 0
            probability = 0.5
            error_category = None

            try:
                prediction = dict(predict(case))
                found = bool(prediction.get("issue", False))
                probability = _clip(
                    float(prediction.get("probability", 1.0 if found else 0.0))
                )
                recommendation_count = int(
                    prediction.get("recommendation_count", 0)
                )
            except Exception as exc:
                execution_ok = False
                found = False
                probability = 0.0
                error_category = type(exc).__name__
                errors[error_category] = errors.get(error_category, 0) + 1

            latency = (time.perf_counter() - start) * 1000.0
            latencies.append(latency)

            actual = bool(case.ground_truth["issue"])
            key = (
                "tp" if actual and found
                else "fp" if found
                else "fn" if actual
                else "tn"
            )
            counts[key] += 1

            if error_category is None and actual != found:
                error_category = "false_positive" if found else "false_negative"
                errors[error_category] = errors.get(error_category, 0) + 1

            if not execution_ok:
                errors["execution_error"] = errors.get("execution_error", 0) + 1

            rows.append(
                CaseResult(
                    case_id=case.case_id,
                    category=str(case.ground_truth.get("category", "unspecified")),
                    expected_issue=actual,
                    predicted_issue=found,
                    probability=probability,
                    correct=actual == found,
                    error_category=error_category,
                    latency_ms=round(latency, 6),
                    recommendation_count=recommendation_count,
                    execution_ok=execution_ok,
                )
            )

        metrics = Metrics(**counts)
        config = {
            **dict(configuration or {}),
            "system_execution": system,
            "case_order": [c.case_id for c in cases],
        }

        return ResearchReport(
            experiment_id=_fingerprint(
                {
                    "cases": [
                        {
                            "case_id": c.case_id,
                            "provider": c.provider,
                            "format": c.iac_format,
                            "ground_truth": c.ground_truth,
                            "iac_content": c.iac_content,
                        }
                        for c in cases
                    ],
                    "configuration": config,
                }
            ),
            case_count=len(rows),
            metrics=metrics.to_dict(),
            latency=self._latency(latencies),
            errors=dict(sorted(errors.items())),
            per_category=self._per_category(rows),
            calibration=self._calibration(rows),
            confidence_intervals=self._bootstrap(rows, seed=config),
            configuration=config,
            cases=tuple(r.to_dict() for r in rows),
        )

    @staticmethod
    def _per_category(rows: Sequence[CaseResult]) -> dict[str, Any]:
        grouped: dict[str, list[CaseResult]] = {}
        for row in rows:
            grouped.setdefault(row.category, []).append(row)

        output = {}
        for category in sorted(grouped):
            group = grouped[category]
            m = Metrics(
                tp=sum(r.expected_issue and r.predicted_issue for r in group),
                fp=sum((not r.expected_issue) and r.predicted_issue for r in group),
                fn=sum(r.expected_issue and (not r.predicted_issue) for r in group),
                tn=sum((not r.expected_issue) and (not r.predicted_issue) for r in group),
            )
            output[category] = m.to_dict()
        return output

    @staticmethod
    def _calibration(rows: Sequence[CaseResult]) -> dict[str, float]:
        n = len(rows)
        brier = sum(
            (r.probability - float(r.expected_issue)) ** 2 for r in rows
        ) / n

        bins: list[list[CaseResult]] = [[] for _ in range(10)]
        for row in rows:
            bins[min(9, int(row.probability * 10))].append(row)

        ece = 0.0
        for bucket in bins:
            if not bucket:
                continue
            confidence = statistics.mean(r.probability for r in bucket)
            observed = statistics.mean(float(r.expected_issue) for r in bucket)
            ece += len(bucket) / n * abs(confidence - observed)

        return {"brier_score": round(brier, 6), "ece": round(ece, 6)}

    @staticmethod
    def _bootstrap(
        rows: Sequence[CaseResult],
        *,
        seed: Mapping[str, Any],
        samples: int = 1000,
    ) -> dict[str, Any]:
        n = len(rows)
        if not n:
            return {}

        state = int(
            hashlib.sha256(
                json.dumps(_canonical(seed), sort_keys=True, default=str).encode()
            ).hexdigest()[:16],
            16,
        )
        series = {k: [] for k in ("accuracy", "precision", "recall", "f1")}

        for _ in range(samples):
            sample = []
            for _j in range(n):
                state = (1103515245 * state + 12345) & 0x7FFFFFFF
                sample.append(rows[state % n])

            m = Metrics(
                tp=sum(r.expected_issue and r.predicted_issue for r in sample),
                fp=sum((not r.expected_issue) and r.predicted_issue for r in sample),
                fn=sum(r.expected_issue and (not r.predicted_issue) for r in sample),
                tn=sum((not r.expected_issue) and (not r.predicted_issue) for r in sample),
            )
            series["accuracy"].append(m.accuracy)
            series["precision"].append(m.precision)
            series["recall"].append(m.recall)
            series["f1"].append(m.f1)

        result = {}
        for name, values in series.items():
            values.sort()
            result[name] = {
                "lower": round(values[int(0.025 * samples)], 6),
                "upper": round(values[min(samples - 1, int(0.975 * samples))], 6),
                "method": "deterministic_bootstrap_95pct",
            }
        return result

    @staticmethod
    def _latency(values: Sequence[float]) -> dict[str, float]:
        return {
            "mean_ms": round(statistics.mean(values), 6),
            "median_ms": round(statistics.median(values), 6),
            "min_ms": round(min(values), 6),
            "max_ms": round(max(values), 6),
        }

    @staticmethod
    def _materialize(case: BenchmarkCase):
        if case.iac_path:
            class Existing:
                def __enter__(self):
                    return case.iac_path
                def __exit__(self, *args):
                    return False
            return Existing()

        suffix = {
            "terraform": ".tf",
            "cloudformation": ".yaml",
            "yaml": ".yaml",
            "yml": ".yml",
            "json": ".json",
        }.get(case.iac_format.lower(), ".txt")

        class TemporaryCase:
            def __enter__(self):
                self.tmp = TemporaryDirectory()
                self.path = Path(self.tmp.name) / f"{case.case_id}{suffix}"
                self.path.write_text(case.iac_content or "", encoding="utf-8")
                return str(self.path)

            def __exit__(self, *args):
                return self.tmp.__exit__(*args)

        return TemporaryCase()


def default_dataset() -> tuple[BenchmarkCase, ...]:
    """Independent offline benchmark fixtures with explicit labels."""
    tf_clean = 'resource "aws_instance" "web" { ami = "ami-123456" instance_type = "t3.micro" }'
    tf_security = (
        'resource "aws_security_group" "web" { name = "web" '
        'ingress { from_port = 22 to_port = 22 protocol = "tcp" '
        'cidr_blocks = ["0.0.0.0/0"] } }'
    )
    tf_dependency = (
        'resource "aws_security_group" "web" { name = "web" } '
        'resource "aws_instance" "web" { ami = "ami-123456" '
        'instance_type = "t3.micro" '
        'vpc_security_group_ids = [aws_security_group.web.id] }'
    )
    cfn_clean = (
        'AWSTemplateFormatVersion: "2010-09-09"\n'
        'Resources:\n  Web:\n    Type: AWS::EC2::Instance\n'
        '    Properties:\n      ImageId: ami-123456\n'
        '      InstanceType: t3.micro\n'
    )
    cfn_security = (
        'AWSTemplateFormatVersion: "2010-09-09"\n'
        'Resources:\n  WebSG:\n    Type: AWS::EC2::SecurityGroup\n'
        '    Properties:\n      GroupDescription: web\n'
        '      SecurityGroupIngress:\n'
        '        - IpProtocol: tcp\n          FromPort: 22\n'
        '          ToPort: 22\n          CidrIp: 0.0.0.0/0\n'
    )

    return (
        BenchmarkCase(
            case_id="tf_clean", provider="Terraform", iac_format="terraform",
            ground_truth={"issue": False, "category": "clean"},
            iac_content=tf_clean,
        ),
        BenchmarkCase(
            case_id="tf_security", provider="Terraform", iac_format="terraform",
            ground_truth={"issue": True, "category": "security"},
            iac_content=tf_security,
        ),
        BenchmarkCase(
            case_id="tf_dependency", provider="Terraform", iac_format="terraform",
            ground_truth={"issue": True, "category": "dependency"},
            iac_content=tf_dependency,
        ),
        BenchmarkCase(
            case_id="cfn_clean", provider="CloudFormation", iac_format="cloudformation",
            ground_truth={"issue": False, "category": "clean"},
            iac_content=cfn_clean,
        ),
        BenchmarkCase(
            case_id="cfn_security", provider="CloudFormation", iac_format="cloudformation",
            ground_truth={"issue": True, "category": "security"},
            iac_content=cfn_security,
        ),
    )
