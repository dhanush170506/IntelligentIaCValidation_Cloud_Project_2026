"""Deterministic post-generation checks for evidence-grounded LLM text."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

@dataclass(frozen=True, kw_only=True)
class EvidenceConsistencyResult:
    accepted: bool; reasons: tuple[str, ...]; fallback_text: str

class EvidenceConsistencyValidator:
    """Conservative lexical guard; it never uses an LLM to validate an LLM."""
    RESOURCE = re.compile(r"\b(?:aws_[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|[A-Za-z][A-Za-z0-9_-]*Resource)\b")
    EVIDENCE = re.compile(r"\b(?:evidence|telemetry|config|cost|runtime-drift|consensus|remediation)[A-Za-z0-9:_.-]*:[A-Za-z0-9_.:-]+\b", re.I)
    MONEY = re.compile(r"\$\s*\d+(?:\.\d+)?")
    UNSAFE_ACTION = re.compile(r"\b(?:apply|destroy|delete|terminate)\b", re.I)
    def validate(self, *, text: Any, uir: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]], agent_results: Iterable[Any]) -> EvidenceConsistencyResult:
        fallback = "Deterministic assurance summary: use only the attached findings and evidence; submit remediation for approval before any infrastructure change."
        if not isinstance(text, str) or not text.strip(): return EvidenceConsistencyResult(accepted=False, reasons=("Generated explanation is missing or malformed.",), fallback_text=fallback)
        resources = {str(x.get("id")) for x in uir.get("resources", ()) if isinstance(x, Mapping)}
        ids = {str(x.get("evidence_id")) for x in evidence if isinstance(x, Mapping) and x.get("evidence_id")}
        reasons = []
        for value in self.RESOURCE.findall(text):
            if value not in resources: reasons.append(f"Unknown resource reference: {value}")
        for value in self.EVIDENCE.findall(text):
            if value not in ids: reasons.append(f"Unknown evidence reference: {value}")
        # Dollar amounts are only accepted when the supplied evidence contains
        # the same literal amount; this prevents invented cost claims.
        evidence_text = " ".join(str(x) for x in evidence)
        for amount in self.MONEY.findall(text):
            if amount.replace(" ", "") not in evidence_text.replace(" ", ""): reasons.append(f"Unsupported cost value: {amount}")
        if self.UNSAFE_ACTION.search(text): reasons.append("Generated text proposes an unsupported direct infrastructure action.")
        return EvidenceConsistencyResult(accepted=not reasons, reasons=tuple(reasons), fallback_text=fallback)
