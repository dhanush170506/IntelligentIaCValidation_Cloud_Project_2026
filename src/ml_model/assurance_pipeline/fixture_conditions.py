"""Controlled conditions for the ten independent benchmark fixtures.

Single source of truth for the per-fixture mock inputs that the independent
fixture harness (``test_independent_fixtures.py``) has always used:

    01 clean Terraform baseline
    02 custom security validator emitting a controlled HIGH finding
    03 controlled Module 3 validator failure
    04 confirmed drift  - runtime config differs from desired state
    05 possible drift   - exactly one supporting telemetry point
    06 likely drift     - two supporting telemetry points
    07 runtime unavailable - controlled collection error
    08 cost optimization with pricing data
    09 consensus scenario
    10 complex manufacturing scenario with pricing data

This module is consumed by BOTH:
  - src/ml_model/assurance_pipeline/test_independent_fixtures.py (harness)
  - src/backend/services/dataset_evaluation_service.py (benchmark/UI path)

so a fixture evaluated through the normal evaluation path runs under exactly
the same controlled conditions as in the harness.

IMPORTANT:
  - These are controlled *inputs* (mock providers, validators, pricing
    catalogs). They are never ground-truth labels and are never passed into
    the pipeline as expected outcomes; independent ground truth stays in the
    harness/evaluation layer.
  - No security/drift/confidence numbers are invented here. Every reported
    score is produced by the frozen M1-M9 pipeline itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.ml_model.assurance_pipeline import AssuranceOrchestrator
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module3_static_validation.validation_result import build_report
from src.ml_model.module3_static_validation.validation_schema import (
    ValidationFinding,
    ValidationSeverity,
    ValidationStatus,
)
from src.ml_model.module6_runtime_telemetry import (
    CollectionError,
    ConfigState,
    MockCloudWatchProvider,
    MockConfigProvider,
    RuntimeStateCollector,
    TelemetryDatum,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "benchmarks" / "independent_fixtures"

FIXTURE_NAMES = (
    "01_clean_terraform.tf",
    "02_security_failure_terraform.tf",
    "03_validator_failure_terraform.tf",
    "04_confirmed_drift_terraform.tf",
    "05_possible_drift_terraform.tf",
    "06_likely_drift_terraform.tf",
    "07_runtime_unavailable_terraform.tf",
    "08_cost_optimization_terraform.tf",
    "09_consensus_terraform.tf",
    "10_complex_manufacturing_terraform.tf",
)

# 1-based fixture index -> honest scenario label (recorded verbatim in
# evaluation output; it describes the controlled input, not the result).
SCENARIO_LABELS: Mapping[int, str] = {
    1: "clean_baseline",
    2: "controlled_security_finding",
    3: "controlled_validator_failure",
    4: "confirmed_drift_changed_runtime",
    5: "possible_drift_single_telemetry_point",
    6: "likely_drift_two_telemetry_points",
    7: "runtime_unavailable",
    8: "cost_optimization_with_pricing",
    9: "consensus_scenario",
    10: "complex_manufacturing_with_pricing",
}

# Pricing data used by fixtures 08 and 10 so the Cost Analysis Agent can
# produce real cost findings instead of "pricing unavailable" notices.
PRICING_CATALOG: Mapping[str, Any] = {
    "compute_instance": {
        "default": {
            "monthly": 250,
        }
    }
}


class BrokenValidator:
    """Validator whose validate() always raises - controlled Module 3 failure."""

    def validate(self, path):
        raise RuntimeError("controlled validator unavailable")


class SecurityValidator:
    """Validator emitting one controlled HIGH ingress finding (fixture 02)."""

    def validate(self, path):
        return build_report(
            provider="Terraform",
            findings=(
                ValidationFinding(
                    tool="checkov",
                    provider="Terraform",
                    rule_id="CKV_AWS_24",
                    message="Controlled public ingress finding",
                    severity=ValidationSeverity.HIGH,
                    status=ValidationStatus.FAILED,
                    resource_id="aws_security_group.public_control",
                ),
            ),
        )


def desired(path: Path | str) -> list[dict[str, Any]]:
    """Parse a fixture and return its UIR resources (desired state)."""
    return build_uir(process_iac_file(str(path)))["resources"]


def instance(resources: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the fixture's single aws_instance desired-state resource."""
    return next(x for x in resources if x["type"] == "aws_instance")


def runtime(
    path: Path | str,
    *,
    change: bool = False,
    points: int = 0,
    unavailable: bool = False,
) -> RuntimeStateCollector:
    """Build a RuntimeStateCollector with controlled mock state and telemetry.

    change      -> runtime instance_type differs from desired (confirmed drift)
    points      -> number of high-CPU telemetry points for the aws_instance
    unavailable -> providers return a controlled collection error instead
    """
    resources = desired(path)
    states = []
    errors = []
    target = instance(resources)
    for item in resources:
        props = dict(item["properties"])
        if change and item["id"] == target["id"]:
            props["instance_type"] = "t3.large"
        states.append(
            ConfigState(
                resource_id=item["id"],
                resource_type=item["type"],
                provider="AWS",
                configuration=props,
            )
        )
    if unavailable:
        states = []
        errors = [
            CollectionError(
                source="AWS_CONFIG",
                resource_id=None,
                code="UNAVAILABLE",
                message="controlled offline failure",
            )
        ]
    telemetry = tuple(
        TelemetryDatum(
            resource_id=target["id"],
            resource_type=target["type"],
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            timestamp=f"2026-01-01T0{i}:00:00Z",
            value=99 if points else 20,
        )
        for i in range(max(1, points))
    )
    return RuntimeStateCollector(
        MockConfigProvider(states, errors),
        MockCloudWatchProvider(telemetry, errors),
    )


def fixture_index(path: Path | str) -> int:
    """Return the 1-based fixture index for an exact fixture filename, else 0."""
    name = Path(path).name
    try:
        return FIXTURE_NAMES.index(name) + 1
    except ValueError:
        return 0


def fixture_options(path: Path | str) -> dict[str, Any]:
    """Orchestrator constructor kwargs reproducing one fixture's conditions.

    Returns an empty dict for files that are not one of the ten known
    fixtures, so every non-fixture sample keeps the default orchestrator
    behavior.
    """
    index = fixture_index(path)
    if index == 0:
        return {}

    options: dict[str, Any] = {}
    if index == 2:
        options["validators"] = (SecurityValidator(),)
    elif index == 3:
        options["validators"] = (BrokenValidator(),)

    if index in (4, 5, 6, 7):
        options["runtime_collector"] = runtime(
            Path(path),
            change=index == 4,
            points=1 if index == 5 else 2 if index == 6 else 0,
            unavailable=index == 7,
        )

    if index in (8, 10):
        options["pricing_catalog"] = dict(PRICING_CATALOG)

    return options


def build_fixture_orchestrator(path: Path | str) -> tuple[AssuranceOrchestrator, int]:
    """Build an orchestrator carrying the fixture's controlled conditions.

    Returns ``(orchestrator, fixture_index)`` where the index is 0 when
    ``path`` is not one of the ten known fixtures (in which case the
    orchestrator uses pure defaults).
    """
    index = fixture_index(path)
    return AssuranceOrchestrator(**fixture_options(path)), index


__all__ = [
    "BrokenValidator",
    "SCENARIO_LABELS",
    "FIXTURE_DIR",
    "FIXTURE_NAMES",
    "PRICING_CATALOG",
    "SecurityValidator",
    "build_fixture_orchestrator",
    "desired",
    "fixture_index",
    "fixture_options",
    "instance",
    "runtime",
]
