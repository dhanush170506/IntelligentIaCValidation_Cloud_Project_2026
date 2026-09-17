from __future__ import annotations

import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Project root
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
from src.ml_model.module3_static_validation.validation_result import (
    build_report,
)


# ---------------------------------------------------------------------------
# Module 4
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Module 5.1
# ---------------------------------------------------------------------------
from src.ml_model.module5_llm_integration.bedrock_adapter import (
    BedrockAdapter,
)
from src.ml_model.module5_llm_integration.bedrock_client import (
    MockBedrockClient,
)


IAC_FILE = (
    PROJECT_ROOT
    / "src"
    / "ml_model"
    / "module1_iac_parser"
    / "sample_terraform.tf"
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


def main() -> int:
    print("=" * 72)
    print("MODULE 5.1 - REAL PROJECT INTEGRATION TEST")
    print("=" * 72)

    # =======================================================================
    # MODULE 1
    # =======================================================================
    print("\n[1/5] Module 1 - IaC parsing")

    normalized = process_iac_file(str(IAC_FILE))

    print("  Provider      :", normalized["provider"])
    print("  Resources     :", len(normalized["resources"]))
    print("  Dependencies  :", len(normalized["dependencies"]))

    assert normalized["provider"] == "Terraform"
    assert len(normalized["resources"]) == 2
    assert len(normalized["dependencies"]) == 1

    print("  [PASS] Module 1")


    # =======================================================================
    # MODULE 2
    # =======================================================================
    print("\n[2/5] Module 2 - UIR + graph")

    uir = build_uir(normalized)
    validate_uir(uir)

    uir = GraphBuilder().attach_graph(uir)
    validate_uir(uir)

    print("  UIR resources :", len(uir["resources"]))
    print("  UIR deps      :", len(uir["dependencies"]))
    print("  Graph nodes   :", len(uir["graph"]["nodes"]))
    print("  Graph edges   :", len(uir["graph"]["edges"]))

    assert len(uir["resources"]) == 2
    assert len(uir["dependencies"]) == 1
    assert len(uir["graph"]["nodes"]) == 2
    assert len(uir["graph"]["edges"]) == 1

    print("  [PASS] Module 2")


    # =======================================================================
    # MODULE 3
    # =======================================================================
    print("\n[3/5] Module 3 - standardized validation reports")

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

    print("  Validation reports:", len(validation_reports))
    print("  [PASS] Module 3 interface")


    # =======================================================================
    # MODULE 4
    # =======================================================================
    print("\n[4/5] Module 4 - agent execution")

    syntax_result = SyntaxValidationAgent().run(
        validation_reports=validation_reports,
    )

    security_result = SecurityValidationAgent().run(
        validation_reports=validation_reports,
    )

    deployment_result = DeploymentValidationAgent().run(
        uir=uir,
    )

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

    drift_result = DriftDetectionAgent().run(
        uir=uir,
        observed_state=observed_state,
    )

    cost_result = CostAnalysisAgent().run(
        uir=uir,
        pricing_catalog=PRICING_CATALOG,
    )

    agent_results = (
        syntax_result,
        security_result,
        deployment_result,
        drift_result,
        cost_result,
    )

    for result in agent_results:
        print(
            f"  {result.agent_type.value:<22}"
            f" status={result.status.value:<10}"
            f" findings={len(result.findings):<3}"
            f" confidence={result.confidence:.3f}"
        )

    for result in agent_results:
        assert result.status.value == "COMPLETED"

    print("  [PASS] Module 4")


    # =======================================================================
    # MODULE 5.1
    # =======================================================================
    print("\n[5/5] Module 5.1 - Bedrock integration")

    mock_client = MockBedrockClient(
        response_text=(
            "Infrastructure assurance analysis completed "
            "using the supplied evidence."
        ),
        confidence=0.92,
    )

    adapter = BedrockAdapter(
        mock_client,
        model_id="mock-model",
    )

    response = adapter.analyze(
        agent_results=agent_results,
        uir=uir,
    )

    assert response.model_id == "mock-model"
    assert response.text
    assert response.confidence == 0.92

    assert mock_client.last_request is not None

    prompt = mock_client.last_request.user_prompt

    assert "agent_results" in prompt
    assert "uir" in prompt
    assert "SYNTAX_VALIDATION" in prompt
    assert "SECURITY_VALIDATION" in prompt
    assert "DEPLOYMENT_VALIDATION" in prompt
    assert "DRIFT_DETECTION" in prompt
    assert "COST_ANALYSIS" in prompt
    assert "Terraform" in prompt

    print("  Model ID       :", response.model_id)
    print("  Response       :", response.text)
    print("  Confidence     :", response.confidence)
    print("  Prompt length  :", len(prompt))
    print("  [PASS] Module 5.1")


    # =======================================================================
    # FINAL
    # =======================================================================
    print("\n" + "=" * 72)
    print("MODULE 5.1 REAL PROJECT INTEGRATION TEST: PASSED")
    print("=" * 72)

    print("\nFinal response:")
    print(
        json.dumps(
            response.to_dict(),
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())