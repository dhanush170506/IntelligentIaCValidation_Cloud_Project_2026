"""Research-grade deterministic evaluation primitives for Modules 1-8."""
from .evaluation import (
    BenchmarkCase, CaseResult, ExperimentRunner, Metrics, ResearchReport, default_dataset
)
__all__ = [
    "BenchmarkCase", "CaseResult", "ExperimentRunner", "Metrics",
    "ResearchReport", "default_dataset"
]
