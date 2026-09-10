"""Tests for Module 4 Cost Analysis Agent."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_schema import AgentSeverity, AgentStatus, AgentType
from cost_analysis_agent import CostAnalysisAgent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


CATALOG = {
    "aws_instance": {
        "t3.micro": {"hourly": 0.0104},
        "t3.small": {"hourly": 0.0208},
        "t3.medium": {"hourly": 0.0416},
        "t3.large": {"hourly": 0.0832},
    },
    "aws_ebs_volume": {
        "default": {"price_per_gb_month": 0.10},
    },
    "aws_db_instance": {
        "db.t3.micro": {"hourly": 0.017},
    },
}


def make_uir(resources=None):
    if resources is None:
        resources = [
            {
                "id": "aws_instance.web",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "web",
                "properties": {"instance_type": "t3.micro"},
            }
        ]
    return {
        "provider": "Terraform",
        "resources": resources,
        "dependencies": [],
    }


def test_canonical_type_catalog_lookup() -> None:
    agent = CostAnalysisAgent()
    canonical_catalog = {
        "compute_instance": {
            "t3.micro": {"hourly": 0.0104},
        },
    }
    result = agent.run(
        uir=make_uir(),
        pricing_catalog=canonical_catalog,
    )
    check(
        result.metadata["priced_resource_count"] == 1,
        "Canonical UIR type is used for pricing lookup",
    )
    check(
        result.metadata["estimated_monthly_cost"] == 7.59,
        "Canonical type pricing produces the expected monthly cost",
    )


def main() -> None:
    test_canonical_type_catalog_lookup()
    agent = CostAnalysisAgent()

    result = agent.run(
        uir=make_uir(),
        pricing_catalog=CATALOG,
    )
    check(result.agent_type == AgentType.COST_ANALYSIS, "Agent type is correct")
    check(result.status == AgentStatus.COMPLETED, "Cost analysis completes")
    check(
        result.metadata["estimated_monthly_cost"] == 7.59,
        "Monthly compute calculation is correct",
    )
    check(
        result.metadata["priced_resource_count"] == 1,
        "Priced resource count is correct",
    )

    resources = [
        make_uir()["resources"][0],
        {
            "id": "aws_instance.worker",
            "provider": "Terraform",
            "type": "aws_instance",
            "canonical_type": "compute_instance",
            "properties": {"instance_type": "t3.micro", "count": 3},
        },
    ]
    result = agent.run(uir=make_uir(resources), pricing_catalog=CATALOG)
    expected = round(7.592 + (0.0104 * 730 * 3), 2)
    check(
        result.metadata["estimated_monthly_cost"] == expected,
        "Multiple resources and quantity are calculated correctly",
    )

    resources = [
        {
            "id": "aws_ebs_volume.data",
            "provider": "Terraform",
            "type": "aws_ebs_volume",
            "canonical_type": "storage_volume",
            "properties": {"size_gb": 100},
        }
    ]
    result = agent.run(uir=make_uir(resources), pricing_catalog=CATALOG)
    check(
        result.metadata["estimated_monthly_cost"] == 10.0,
        "Storage monthly cost is calculated correctly",
    )

    resources = [
        {
            "id": "aws_db_instance.db",
            "provider": "Terraform",
            "type": "aws_db_instance",
            "canonical_type": "database",
            "properties": {"instance_class": "db.t3.micro"},
        }
    ]
    # The catalog lookup recognizes "engine" etc.; make this explicitly
    # test the generic/default mechanism by adding a default catalog entry.
    db_catalog = {
        "aws_db_instance": {
            "default": {"hourly": 0.017},
        }
    }
    result = agent.run(uir=make_uir(resources), pricing_catalog=db_catalog)
    check(
        result.metadata["estimated_monthly_cost"] == round(0.017 * 730, 2),
        "Database hourly cost is calculated correctly",
    )

    resources = [
        {
            "id": "aws_unknown.resource",
            "provider": "Terraform",
            "type": "aws_unknown",
            "canonical_type": "unknown",
            "properties": {},
        }
    ]
    result = agent.run(uir=make_uir(resources), pricing_catalog=CATALOG)
    check(
        result.metadata["unpriced_resource_count"] == 1,
        "Unknown pricing is tracked",
    )
    check(
        any(f.rule_id == "COST_PRICING_UNAVAILABLE" for f in result.findings),
        "Unknown pricing produces an informational finding",
    )

    resources = [
        {
            "id": "aws_instance.expensive",
            "provider": "Terraform",
            "type": "aws_instance",
            "canonical_type": "compute_instance",
            "properties": {"instance_type": "t3.large"},
        }
    ]
    result = agent.run(
        uir=make_uir(resources),
        pricing_catalog=CATALOG,
        high_cost_threshold=50,
    )
    high = [f for f in result.findings if f.rule_id == "COST_HIGH_RESOURCE"]
    check(len(high) == 1, "High-cost resource is detected")
    check(high[0].severity == AgentSeverity.HIGH, "High-cost finding is HIGH severity")

    result = agent.run(
        uir=make_uir(resources),
        pricing_catalog=CATALOG,
    )
    check(
        any(f.rule_id == "COST_OPTIMIZATION_OPPORTUNITY" for f in result.findings),
        "Optimization opportunity is generated",
    )
    recommendation = next(
        f for f in result.findings
        if f.rule_id == "COST_OPTIMIZATION_OPPORTUNITY"
    )
    check(
        "if workload requirements permit" in recommendation.message,
        "Optimization recommendation is appropriately qualified",
    )

    result1 = agent.run(uir=make_uir(), pricing_catalog=CATALOG)
    result2 = agent.run(uir=make_uir(), pricing_catalog=CATALOG)
    check(
        result1.evidence_ids == result2.evidence_ids,
        "Evidence IDs are deterministic",
    )
    check(
        result1.confidence == result2.confidence,
        "Confidence is deterministic",
    )

    check(
        result1.metadata["monthly_hours"] == 730.0,
        "Default monthly utilization is 730 hours",
    )
    check(
        result1.metadata["currency"] == "USD",
        "Default currency is USD",
    )

    invalid = agent.run(uir=None, pricing_catalog=CATALOG)
    check(invalid.status == AgentStatus.FAILED, "Invalid UIR returns FAILED result")

    invalid = agent.run(uir=make_uir(), pricing_catalog={"aws_instance": {"t3.micro": {"hourly": -1}}})
    check(invalid.status == AgentStatus.FAILED, "Negative price is rejected")

    invalid = agent.run(uir=make_uir(), pricing_catalog=CATALOG, monthly_hours=-1)
    check(invalid.status == AgentStatus.FAILED, "Negative monthly hours are rejected")

    invalid = agent.run(uir=make_uir(), pricing_catalog=CATALOG, high_cost_threshold=-1)
    check(invalid.status == AgentStatus.FAILED, "Negative threshold is rejected")

    empty = agent.run(
        uir=make_uir([]),
        pricing_catalog=CATALOG,
    )
    check(empty.status == AgentStatus.COMPLETED, "Empty resource set completes")
    check(empty.metadata["estimated_monthly_cost"] == 0.0, "Empty resource cost is zero")

    print("All Cost Analysis Agent tests PASSED.")


if __name__ == "__main__":
    main()
