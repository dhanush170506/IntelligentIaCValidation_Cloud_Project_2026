from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project-root import setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Module 1
# ---------------------------------------------------------------------------
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file


# ---------------------------------------------------------------------------
# Module 2
# ---------------------------------------------------------------------------
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module2_uir.uir_validator import validate_uir
from src.ml_model.module2_uir.graph_builder import GraphBuilder


# ---------------------------------------------------------------------------
# Module 3
# ---------------------------------------------------------------------------
from src.ml_model.module3_static_validation.validation_result import build_report
from src.ml_model.module3_static_validation.validation_schema import (
    ValidationSeverity,
    ValidationStatus,
)


# ---------------------------------------------------------------------------
# Module 4
# ---------------------------------------------------------------------------
from src.ml_model.module4_multi_agent.agent_schema import AgentStatus
from src.ml_model.module4_multi_agent.coordinator_agent import CoordinatorAgent
from src.ml_model.module4_multi_agent.syntax_validation_agent import (
    SyntaxValidationAgent,
)
from src.ml_model.module4_multi_agent.security_validation_agent import (
    SecurityValidationAgent,
)
from src.ml_model.module4_multi_agent.deployment_validation_agent import (
    DeploymentValidationAgent,
)
from src.ml_model.module4_multi_agent.drift_detection_agent import (
    DriftDetectionAgent,
)
from src.ml_model.module4_multi_agent.cost_analysis_agent import (
    CostAnalysisAgent,
)
from src.ml_model.module4_multi_agent.evidence_collection_agent import (
    EvidenceCollectionAgent,
)

PRICING_CATALOG = {
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
# ---------------------------------------------------------------------------
# Test file
# ---------------------------------------------------------------------------
IAC_FILE = (
    PROJECT_ROOT
    / "src"
    / "ml_model"
    / "module1_iac_parser"
    / "sample_terraform.tf"
)


def main() -> int:
    print("=" * 72)
    print("MODULE 4 REAL PROJECT INTEGRATION TEST")
    print("=" * 72)

    # =======================================================================
    # 1. MODULE 1
    # =======================================================================
    print("\n[1/7] MODULE 1 - IaC parsing")

    normalized = process_iac_file(str(IAC_FILE))

    print("  Provider       :", normalized["provider"])
    print("  Resources      :", len(normalized["resources"]))
    print("  Dependencies   :", len(normalized["dependencies"]))

    assert normalized["provider"] == "Terraform"
    assert len(normalized["resources"]) == 2
    assert len(normalized["dependencies"]) == 1

    print("  [PASS] Module 1")


    # =======================================================================
    # 2. MODULE 2
    # =======================================================================
    print("\n[2/7] MODULE 2 - UIR + resource graph")

    uir = build_uir(normalized)
    validate_uir(uir)

    uir = GraphBuilder().attach_graph(uir)
    validate_uir(uir)

    nodes = uir["graph"]["nodes"]
    edges = uir["graph"]["edges"]

    print("  UIR resources  :", len(uir["resources"]))
    print("  UIR dependencies:", len(uir["dependencies"]))
    print("  Graph nodes    :", len(nodes))
    print("  Graph edges    :", len(edges))

    assert len(uir["resources"]) == 2
    assert len(uir["dependencies"]) == 1
    assert len(nodes) == 2
    assert len(edges) == 1

    print("  [PASS] Module 2")


    # =======================================================================
    # 3. MODULE 3 STANDARDIZED INPUT
    # =======================================================================
    print("\n[3/7] MODULE 3 - standardized ValidationReports")

    syntax_report = build_report(
        provider="Terraform",
        findings=[],
    )

    security_report = build_report(
        provider="Terraform",
        findings=[],
    )

    validation_reports = (
        syntax_report,
        security_report,
    )

    print("  ValidationReports:", len(validation_reports))
    print("  [PASS] Module 3 interface")


    # =======================================================================
    # 4. INDIVIDUAL MODULE 4 AGENTS
    # =======================================================================
    print("\n[4/7] MODULE 4 - individual agents")

    syntax_agent = SyntaxValidationAgent()
    security_agent = SecurityValidationAgent()
    deployment_agent = DeploymentValidationAgent()
    drift_agent = DriftDetectionAgent()
    cost_agent = CostAnalysisAgent()
    evidence_agent = EvidenceCollectionAgent()

    syntax_result = syntax_agent.run(
        validation_reports=validation_reports,
    )

    security_result = security_agent.run(
        validation_reports=validation_reports,
    )

    deployment_result = deployment_agent.run(
        uir=uir,
    )

    # Runtime state intentionally matches the desired state for this first
    # integration smoke test.
    observed_state = {
        "resources": [
            {
                "id": resource["id"],
                "provider": resource["provider"],
                "type": resource["type"],
                "canonical_type": resource["canonical_type"],
                "name": resource["name"],
                "properties": resource["properties"],
            }
            for resource in uir["resources"]
        ]
    }

    drift_result = drift_agent.run(
        uir=uir,
        observed_state=observed_state,
    )

    cost_result = cost_agent.run(
        uir=uir,
        pricing_catalog=PRICING_CATALOG,
    )

    evidence_result = evidence_agent.run(
        agent_results=(
            syntax_result,
            security_result,
            deployment_result,
            drift_result,
            cost_result,
        )
    )

    results = (
        syntax_result,
        security_result,
        deployment_result,
        drift_result,
        cost_result,
        evidence_result,
    )

    expected_types = {
        "SYNTAX_VALIDATION",
        "SECURITY_VALIDATION",
        "DEPLOYMENT_VALIDATION",
        "DRIFT_DETECTION",
        "COST_ANALYSIS",
        "EVIDENCE_COLLECTION",
    }

    actual_types = {result.agent_type.value for result in results}

    assert actual_types == expected_types

    for result in results:
        print(
            f"  {result.agent_type.value:<22}"
            f" status={result.status.value:<10}"
            f" findings={len(result.findings):<3}"
            f" evidence={len(result.evidence_ids):<3}"
            f" confidence={result.confidence:.3f}"
        )

    print("  [PASS] All specialized agents")


    # =======================================================================
    # 5. COORDINATOR
    # =======================================================================
    print("\n[5/7] MODULE 4 - Coordinator")

    # Use agents whose inputs are compatible with the shared integration
    # context. The Coordinator is tested separately from the specialized
    # heterogeneous-input pipeline because each specialized agent naturally
    # consumes a different subset of the project context.
    coordinator = CoordinatorAgent(
        [
            SyntaxValidationAgent(),
            SecurityValidationAgent(),
            DeploymentValidationAgent(),
        ]
    )

    coordinator_result = coordinator.run(
        validation_reports=validation_reports,
        uir=uir,
    )

    print("  Status         :", coordinator_result.status.value)
    print("  Findings       :", len(coordinator_result.findings))
    print("  Evidence       :", len(coordinator_result.evidence_ids))
    print("  Confidence     :", coordinator_result.confidence)

    assert coordinator_result.status in (
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
    )

    if coordinator_result.status is AgentStatus.FAILED:
        print("\n  Coordinator failure:")
        print(" ", coordinator_result.message)

        # Do not fail the entire test silently.
        # This exposes an actual integration contract problem.
        return 1

    print("  [PASS] Coordinator")


    # =======================================================================
    # 6. EVIDENCE CHAIN
    # =======================================================================
    print("\n[6/7] Evidence chain")

    print(
        "  Specialized agent results :",
        len(results),
    )

    print(
        "  Evidence collection count :",
        evidence_result.metadata.get("evidence_count"),
    )

    assert evidence_result.status is AgentStatus.COMPLETED

    print("  [PASS] Evidence chain")


    # =======================================================================
    # 7. FINAL SUMMARY
    # =======================================================================
    print("\n[7/7] FINAL MODULE 4 SUMMARY")

    print(
        json.dumps(
            {
                "input_file": str(IAC_FILE),
                "provider": normalized["provider"],
                "resources": len(uir["resources"]),
                "dependencies": len(uir["dependencies"]),
                "graph_nodes": len(nodes),
                "graph_edges": len(edges),
                "agents": {
                    result.agent_type.value: {
                        "status": result.status.value,
                        "findings": len(result.findings),
                        "evidence_ids": len(result.evidence_ids),
                        "confidence": result.confidence,
                    }
                    for result in results
                },
                "coordinator": {
                    "status": coordinator_result.status.value,
                    "findings": len(coordinator_result.findings),
                    "evidence_ids": len(coordinator_result.evidence_ids),
                    "confidence": coordinator_result.confidence,
                },
            },
            indent=2,
        )
    )

    print("\n" + "=" * 72)
    print("MODULE 4 REAL PROJECT INTEGRATION TEST: PASSED")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())