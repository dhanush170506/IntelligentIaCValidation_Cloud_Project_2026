from __future__ import annotations

from pathlib import Path

from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module2_uir.uir_validator import validate_uir
from src.ml_model.module2_uir.graph_builder import GraphBuilder

from src.ml_model.module3_static_validation.validation_result import build_report

from src.ml_model.module4_multi_agent.agent_schema import AgentStatus
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

from .bedrock_adapter import BedrockAdapter
from .bedrock_schema import BedrockResponse
from .recommendation_engine import RecommendationEngine


ROOT = Path(__file__).resolve().parents[3]

IAC_FILE = (
    ROOT
    / "src"
    / "ml_model"
    / "module1_iac_parser"
    / "sample_terraform.tf"
)


# A deterministic local pricing catalog.
# This keeps the integration test independent of AWS/network access.
PRICING_CATALOG = {
    "compute_instance": {
        "t3.micro": {
            "hourly": 0.0104,
        },
        "t3.small": {
            "hourly": 0.0208,
        },
    },
    "security_group": {
        "default": {
            "monthly": 0.0,
        },
    },
}


class IntegrationBedrockClient:
    """
    Deterministic local Bedrock substitute.

    It implements the same invoke(request) contract used by
    BedrockAdapter, while avoiding AWS credentials/network access.
    """

    def __init__(self) -> None:
        self.last_request = None

    def invoke(self, request):
        self.last_request = request

        return BedrockResponse(
            model_id=request.model_id,
            text=(
                "The infrastructure assurance analysis identified "
                "evidence-supported findings that should be reviewed."
            ),
            confidence=0.90,
        )


def main() -> int:
    print("=" * 72)
    print("MODULE 5.3 REAL PROJECT INTEGRATION TEST")
    print("=" * 72)

    # ------------------------------------------------------------------
    # 1. MODULE 1
    # ------------------------------------------------------------------
    print("\n[1/7] MODULE 1 - IaC parsing")

    normalized = process_iac_file(str(IAC_FILE))

    assert normalized["provider"] == "Terraform"
    assert len(normalized["resources"]) == 2
    assert len(normalized["dependencies"]) == 1

    print(
        "  Provider     :", normalized["provider"]
    )
    print(
        "  Resources    :", len(normalized["resources"])
    )
    print(
        "  Dependencies :", len(normalized["dependencies"])
    )
    print("  [PASS] Module 1")

    # ------------------------------------------------------------------
    # 2. MODULE 2
    # ------------------------------------------------------------------
    print("\n[2/7] MODULE 2 - UIR + resource graph")

    uir = build_uir(normalized)
    validate_uir(uir)

    uir = GraphBuilder().attach_graph(uir)
    validate_uir(uir)

    assert len(uir["resources"]) == 2
    assert len(uir["dependencies"]) == 1
    assert len(uir["graph"]["nodes"]) == 2
    assert len(uir["graph"]["edges"]) == 1

    print("  UIR resources :", len(uir["resources"]))
    print("  Graph nodes   :", len(uir["graph"]["nodes"]))
    print("  Graph edges   :", len(uir["graph"]["edges"]))
    print("  [PASS] Module 2")

    # ------------------------------------------------------------------
    # 3. MODULE 3
    # ------------------------------------------------------------------
    print("\n[3/7] MODULE 3 - standardized validation input")

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

    assert len(validation_reports) == 2

    print(
        "  ValidationReports :",
        len(validation_reports),
    )
    print("  [PASS] Module 3 interface")

    # ------------------------------------------------------------------
    # 4. MODULE 4
    # ------------------------------------------------------------------
    print("\n[4/7] MODULE 4 - multi-agent execution")

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

    evidence_result = EvidenceCollectionAgent().run(
        agent_results=(
            syntax_result,
            security_result,
            deployment_result,
            drift_result,
            cost_result,
        )
    )

    agent_results = (
        syntax_result,
        security_result,
        deployment_result,
        drift_result,
        cost_result,
    )

    print("  Syntax       :", syntax_result.status.value)
    print("  Security     :", security_result.status.value)
    print("  Deployment   :", deployment_result.status.value)
    print("  Drift        :", drift_result.status.value)
    print("  Cost         :", cost_result.status.value)
    print("  Evidence     :", evidence_result.status.value)

    assert all(
        result.status is AgentStatus.COMPLETED
        for result in agent_results
    )

    assert evidence_result.status is AgentStatus.COMPLETED

    print("  Evidence IDs :", len(evidence_result.evidence_ids))
    print("  [PASS] Module 4")

    # ------------------------------------------------------------------
    # 5. MODULE 5.2 - PROMPT ENGINEERING + BEDROCK
    # ------------------------------------------------------------------
    print("\n[5/7] MODULE 5.2 - prompt engineering + Bedrock")

    client = IntegrationBedrockClient()

    adapter = BedrockAdapter(
        client,
        model_id="mock-assurance-model",
        temperature=0.0,
        max_tokens=1000,
    )

    evidence_records = ()

    if evidence_result.metadata:
        evidence_records = tuple(
            evidence_result.metadata.get(
                "evidence",
                (),
            )
        )

    bedrock_response = adapter.analyze(
        agent_results=agent_results,
        uir=uir,
        evidence=evidence_records,
    )

    assert isinstance(
        bedrock_response,
        BedrockResponse,
    )

    assert client.last_request is not None

    assert (
        client.last_request.metadata.get(
            "prompt_engineering"
        )
        == "AssurancePromptEngineer"
    )

    assert "Terraform" in client.last_request.user_prompt

    print(
        "  Model         :",
        bedrock_response.model_id,
    )
    print(
        "  Prompt chars  :",
        len(client.last_request.user_prompt),
    )
    print(
        "  Evidence used :",
        len(evidence_records),
    )
    print("  [PASS] Module 5.2")

    # ------------------------------------------------------------------
    # 6. MODULE 5.3 - RECOMMENDATION ENGINE
    # ------------------------------------------------------------------
    print("\n[6/7] MODULE 5.3 - recommendation generation")

    recommendation_engine = RecommendationEngine()

    recommendation_report = recommendation_engine.generate(
        response=bedrock_response,
        agent_results=agent_results,
        evidence=evidence_records,
    )

    print(
        "  Recommendations :",
        len(recommendation_report.recommendations),
    )

    print(
        "  Overall confidence :",
        recommendation_report.overall_confidence,
    )

    print(
        "  Evidence grounded :",
        recommendation_report.metadata.get(
            "evidence_grounded"
        )
        if recommendation_report.metadata
        else None,
    )

    assert recommendation_report.source_model_id == (
        "mock-assurance-model"
    )

    assert recommendation_report.metadata is not None

    assert (
        recommendation_report.metadata.get(
            "evidence_grounded"
        )
        is True
    )

    # The current sample project has cost findings in the real Module 4
    # integration path, so at least one recommendation should normally
    # be produced.
    assert len(
        recommendation_report.recommendations
    ) >= 1

    for recommendation in recommendation_report.recommendations:
        print(
            "  -",
            recommendation.priority.value,
            "|",
            recommendation.action.value,
            "|",
            recommendation.title,
        )

    print("  [PASS] Module 5.3")

    # ------------------------------------------------------------------
    # 7. FINAL
    # ------------------------------------------------------------------
    print("\n[7/7] END-TO-END RESULT")

    print(
        "  Module 1  -> PASS"
    )
    print(
        "  Module 2  -> PASS"
    )
    print(
        "  Module 3  -> PASS"
    )
    print(
        "  Module 4  -> PASS"
    )
    print(
        "  Module 5.2 -> PASS"
    )
    print(
        "  Module 5.3 -> PASS"
    )

    print()
    print("=" * 72)
    print("MODULE 5.3 REAL PROJECT INTEGRATION TEST: PASSED")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())