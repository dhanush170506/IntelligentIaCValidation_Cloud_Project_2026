"""Thin façade formally exposing Module 2 UIR and Module 6 drift in Module 7."""
from __future__ import annotations
from typing import Any, Mapping
from src.ml_model.module2_uir.graph_builder import GraphBuilder
from src.ml_model.module6_runtime_telemetry.analysis import TelemetryIntentDriftAnalyzer
from .consensus import ConsensusEngine
from .remediation import BlastRadiusEngine, RemediationGate, RemediationRanker

class ResearchArchitecture:
    """Composes existing UIR/drift mechanisms with the new independent engines."""
    def __init__(self) -> None:
        self.consensus=ConsensusEngine(); self.blast_radius=BlastRadiusEngine(); self.gate=RemediationGate(); self.ranker=RemediationRanker()
    def attach_graph(self, uir: Mapping[str,Any])->dict[str,Any]: return GraphBuilder().attach_graph(dict(uir))
    def analyze_drift(self, uir: Mapping[str,Any], runtime: Any): return TelemetryIntentDriftAnalyzer().analyze(uir,runtime)
