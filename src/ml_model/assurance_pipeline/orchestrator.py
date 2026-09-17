"""Explicit, evidence-preserving composition of the existing Modules 1--8.

This module deliberately contains routing only: validators, agents, drift,
consensus, ranking, and reporting remain owned by their respective modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module2_uir.graph_builder import GraphBuilder
from src.ml_model.module3_static_validation.validation_aggregator import ValidationAggregator
from src.ml_model.module4_multi_agent.syntax_validation_agent import SyntaxValidationAgent
from src.ml_model.module4_multi_agent.security_validation_agent import SecurityValidationAgent
from src.ml_model.module4_multi_agent.deployment_validation_agent import DeploymentValidationAgent
from src.ml_model.module4_multi_agent.drift_detection_agent import DriftDetectionAgent
from src.ml_model.module4_multi_agent.cost_analysis_agent import CostAnalysisAgent
from src.ml_model.module4_multi_agent.evidence_collection_agent import EvidenceCollectionAgent
from src.ml_model.module4_multi_agent.agent_result import AgentResult
from src.ml_model.module4_multi_agent.agent_schema import AgentStatus, AgentType
from src.ml_model.module5_llm_integration.bedrock_adapter import BedrockAdapter
from src.ml_model.module5_llm_integration.bedrock_client import MockBedrockClient
from src.ml_model.module5_llm_integration.recommendation_engine import RecommendationEngine
from src.ml_model.module5_llm_integration.confidence_scoring import ConfidenceScorer
from src.ml_model.module5_llm_integration.evidence_validation import EvidenceConsistencyValidator
from src.ml_model.module5_llm_integration.bedrock_schema import BedrockResponse
from src.ml_model.module6_runtime_telemetry.providers import RuntimeStateCollector, MockConfigProvider, MockCloudWatchProvider
from src.ml_model.module6_runtime_telemetry.analysis import TelemetryIntentDriftAnalyzer
from src.ml_model.module7_research_algorithms.consensus import ConsensusEngine
from src.ml_model.module7_research_algorithms.remediation import BlastRadiusEngine, RemediationGate, RemediationRanker
from src.ml_model.module8_recommendation.engine import AssuranceRecommendationEngine


@dataclass(frozen=True, kw_only=True)
class PipelineResult:
    parsed_iac: Mapping[str, Any]
    uir: Mapping[str, Any]
    graph: Mapping[str, Any]
    validation_reports: tuple[Any, ...]
    agent_results: tuple[Any, ...]
    evidence: tuple[Mapping[str, Any], ...]
    bedrock_response: Any
    recommendation_context: Any
    confidence_assessment: Any
    runtime_state: Any
    drift_assessments: tuple[Any, ...]
    consensus: tuple[Any, ...]
    blast_radius_assessments: tuple[Any, ...]
    remediation_proposals: tuple[Any, ...]
    remediation_rankings: tuple[Mapping[str, Any], ...]
    assurance_report: Any
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AssuranceOrchestrator:
    """Runs Modules 1--8 in dependency order using actual preceding outputs."""
    def __init__(self, *, validators: Iterable[Any] = (), runtime_collector: RuntimeStateCollector | None = None,
                 bedrock_adapter: BedrockAdapter | None = None, pricing_catalog: Mapping[str, Any] | None = None) -> None:
        self.validators = tuple(validators)
        self.runtime_collector = runtime_collector or RuntimeStateCollector(MockConfigProvider(), MockCloudWatchProvider())
        self.bedrock_adapter = bedrock_adapter or BedrockAdapter(MockBedrockClient(), model_id="offline-assurance")
        self.pricing_catalog = dict(pricing_catalog or {})

    def run(self, *, iac_path: str | Path, project: str = "assurance-project") -> PipelineResult:
        stages: list[str] = []
        warnings: list[str] = []
        normalized = process_iac_file(str(iac_path)); stages.append("M1")
        uir = GraphBuilder().attach_graph(build_uir(normalized)); stages.append("M2")
        reports = []
        validator_failures = []
        source = Path(iac_path)
        for validator in self.validators:
            try:
                # Terraform/checkov/tflint accept a directory; CFN-Lint accepts a template.
                reports.append(validator.validate(source if "CfnLint" in type(validator).__name__ else source.parent))
            except Exception as exc:
                warnings.append(f"{type(validator).__name__}: {exc}")
                validator_failures.append(AgentResult(agent_type=AgentType.SYNTAX_VALIDATION, status=AgentStatus.FAILED, message=f"Module 3 validator unavailable or failed: {type(validator).__name__}: {exc}", confidence=0.0))
        if reports:
            ValidationAggregator().aggregate(reports)  # validates the actual standardized set
        stages.append("M3")

        # Collection is performed early because the Module 4 drift agent needs
        # observed state; assessment remains the formal Module 6 stage below.
        runtime = self.runtime_collector.collect(uir)
        observed = {"resources": [{"id": x.resource_id, "properties": x.configuration} for x in runtime.resources]}
        agent_results = (
            SyntaxValidationAgent().run(validation_reports=reports),
            SecurityValidationAgent().run(validation_reports=reports),
            DeploymentValidationAgent().run(uir=uir),
            DriftDetectionAgent().run(uir=uir, observed_state=observed, runtime_state=runtime),
            CostAnalysisAgent().run(uir=uir, pricing_catalog=self.pricing_catalog),
        )
        evidence_result = EvidenceCollectionAgent().run(agent_results=agent_results, evidence_records=runtime.collection_evidence)
        evidence = tuple(evidence_result.metadata["evidence"])
        all_agents = agent_results + tuple(validator_failures) + (evidence_result,); stages.append("M4")

        try:
            bedrock = self.bedrock_adapter.analyze(agent_results=all_agents, uir=uir, evidence=evidence)
        except Exception as exc:
            warnings.append(f"Module 5 Bedrock unavailable: {exc}")
            bedrock = BedrockResponse(model_id="unavailable", text="LLM unavailable; deterministic findings remain authoritative.", stop_reason="unavailable", confidence=0.0, metadata={"backend": "unavailable", "error": str(exc)})
        consistency = EvidenceConsistencyValidator().validate(text=bedrock.text, uir=uir, evidence=evidence, agent_results=all_agents)
        if not consistency.accepted:
            # Preserve the existing response contract while preventing an
            # unsupported generated explanation from entering the pipeline.
            from dataclasses import replace
            bedrock = replace(bedrock, text=consistency.fallback_text, confidence=0.0, metadata={**bedrock.metadata, "evidence_validation": "fallback", "validation_reasons": consistency.reasons})
            warnings.extend(consistency.reasons)
        recommendation_context = RecommendationEngine().generate(response=bedrock, agent_results=all_agents, evidence=evidence)
        confidence = ConfidenceScorer().score(all_agents, evidence_records=evidence, model_confidence=bedrock.confidence); stages.append("M5")

        drift = TelemetryIntentDriftAnalyzer().analyze(uir, runtime); stages.append("M6")
        consensus = ConsensusEngine().analyze(all_agents, evidence)
        blast_engine, gate = BlastRadiusEngine(), RemediationGate()
        blasts, proposals, options = [], [], []
        for item in consensus:
            resource_id = item.claim_key.split("|", 1)[0]
            if resource_id == "global" or not any(x["id"] == resource_id for x in uir["resources"]):
                continue
            blast = blast_engine.assess(uir, resource_id); blasts.append(blast)
            proposal = gate.propose(resource_id=resource_id, proposed_change={"kind": "evidence-backed-remediation"}, blast_radius=blast, consensus=item, confidence=item.score, risk=1.0-item.score, evidence_ids=item.evidence_ids)
            proposals.append(proposal)
            options.append({"option_id": resource_id, "resource_id": resource_id, "security": item.score, "reliability": item.score, "cost": .5, "risk": 1.0-item.score, "blast": blast.blast_radius_score, "confidence": item.score})
        rankings = RemediationRanker().rank(options); stages.append("M7")
        assurance = AssuranceRecommendationEngine().build(project=project, uir=uir, agent_results=all_agents, evidence=evidence, drift_assessments=drift, consensus=consensus, proposals=proposals, rankings=rankings, confidence_assessment=confidence); stages.append("M8")
        return PipelineResult(parsed_iac=normalized, uir=uir, graph=uir["graph"], validation_reports=tuple(reports), agent_results=all_agents, evidence=evidence, bedrock_response=bedrock, recommendation_context=recommendation_context, confidence_assessment=confidence, runtime_state=runtime, drift_assessments=tuple(drift), consensus=tuple(consensus), blast_radius_assessments=tuple(blasts), remediation_proposals=tuple(proposals), remediation_rankings=tuple(rankings), assurance_report=assurance, warnings=tuple(warnings), metadata={"stages": tuple(stages), "iac_path": str(iac_path), "offline": isinstance(self.runtime_collector.config_provider, MockConfigProvider)})
