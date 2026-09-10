from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, kw_only=True)
class AssuranceReport:
    project: str
    provider: str
    deployment_readiness: dict[str, Any]
    security: dict[str, Any]
    runtime: dict[str, Any]
    cost: dict[str, Any]
    recommendations: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    confidence: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "provider": self.provider,
            "deployment_readiness": self.deployment_readiness,
            "security": self.security,
            "runtime": self.runtime,
            "cost": self.cost,
            "recommendations": list(self.recommendations),
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "limitations": list(self.limitations),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, default=str)

    def to_text(self) -> str:
        return (
            f"Assurance report: {self.project}\n"
            f"Readiness: {self.deployment_readiness['score']:.1f}/100\n"
            f"Security: {self.security['score']:.1f}/100\n"
            f"Recommendations: {len(self.recommendations)}"
        )


class AssuranceRecommendationEngine:
    """Consumes M4-M7 outputs; suggestions are deterministic, qualified, and dry-run."""

    SEVERITY = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
        "INFO": 4,
        "NONE": 5,
    }

    ACTIONS = {
        "SECURITY": "Restrict exposure or apply the referenced security control.",
        "SYNTAX": "Correct the reported IaC syntax or rule violation.",
        "DEPLOYMENT": "Correct the deployment dependency or configuration reference.",
        "DRIFT": (
            "Reconcile runtime configuration with IaC intent, or update IaC "
            "if the change is approved."
        ),
        "COST": (
            "Evaluate the evidence-supported lower-cost option if workload "
            "requirements permit."
        ),
        "RELIABILITY": (
            "Investigate the observed runtime reliability signal before "
            "changing production."
        ),
    }

    def build(
        self,
        *,
        project: str,
        uir: Mapping[str, Any],
        agent_results: Iterable[Any],
        evidence: Iterable[Mapping[str, Any]],
        drift_assessments: Iterable[Any] = (),
        consensus: Iterable[Any] = (),
        proposals: Iterable[Any] = (),
        rankings: Iterable[Mapping[str, Any]] = (),
        confidence_assessment: Any = None,
    ) -> AssuranceReport:
        # Materialize all iterables because several are consumed more than once.
        # This makes generator/list inputs semantically identical and deterministic.
        agent_results = tuple(agent_results)
        evidence = tuple(evidence)
        drift_assessments = tuple(drift_assessments)
        consensus = tuple(consensus)
        proposals = tuple(proposals)
        rankings = tuple(rankings)

        evidence_rows = tuple(
            sorted(
                (dict(x) for x in evidence if isinstance(x, Mapping)),
                key=lambda x: str(x.get("evidence_id", "")),
            )
        )
        valid_evidence = {
            str(x.get("evidence_id"))
            for x in evidence_rows
            if x.get("evidence_id") not in (None, "")
        }

        recs: list[dict[str, Any]] = []

        # M4 findings.
        for result in agent_results:
            for finding in getattr(result, "findings", ()):
                f = finding.to_dict()
                ids = self._ground_evidence(f.get("evidence_ids", ()), valid_evidence)
                category = self._category(f)
                recs.append(
                    self._recommend(
                        f,
                        category,
                        ids,
                        float(f.get("confidence", 0.5)),
                        evidence_grounded=bool(ids),
                    )
                )

        # M6 runtime drift.
        for assessment in drift_assessments:
            d = assessment.to_dict() if hasattr(assessment, "to_dict") else dict(assessment)
            category_value = self._enum_value(d.get("category"))

            # Possible drift is an ambiguous signal for investigation, not
            # evidence sufficient to recommend a configuration change.
            if category_value in ("NO_DRIFT", "POSSIBLE_DRIFT"):
                continue

            category = (
                "DRIFT"
                if category_value != "INSUFFICIENT_EVIDENCE"
                else "RELIABILITY"
            )
            ids = self._ground_evidence(
                d.get("telemetry_evidence_ids", ()), valid_evidence
            )
            text = (
                "Collect AWS Config/CloudWatch evidence before proposing a "
                "configuration change."
                if category == "RELIABILITY"
                else self.ACTIONS["DRIFT"]
            )
            recs.append(
                self._recommend(
                    {
                        "resource_id": d.get("resource_id"),
                        "rule_id": "RUNTIME_DRIFT",
                        "severity": d.get("severity", "INFO"),
                        "message": category_value,
                        "evidence_ids": ids,
                    },
                    category,
                    ids,
                    float(d.get("confidence", 0.5)),
                    action=text,
                    evidence_grounded=bool(ids),
                )
            )

        # Module 7 owns consensus, blast-radius gates, and Pareto ranking.
        # M8 only renders those deterministic decisions into traceable
        # recommendations.
        proposal_rows = [
            x.to_dict() if hasattr(x, "to_dict") else dict(x)
            for x in proposals
            if hasattr(x, "to_dict") or isinstance(x, Mapping)
        ]
        ranking_rows = [dict(x) for x in rankings if isinstance(x, Mapping)]
        consensus_rows = [
            x.to_dict() if hasattr(x, "to_dict") else dict(x)
            for x in consensus
            if hasattr(x, "to_dict") or isinstance(x, Mapping)
        ]

        consensus_by_resource: dict[str, dict[str, Any]] = {}
        for row in consensus_rows:
            resource_id = row.get("resource_id")
            if resource_id is None:
                claim_key = str(row.get("claim_key", ""))
                resource_id = claim_key.split("|", 1)[0] if claim_key else ""
            if resource_id:
                consensus_by_resource[str(resource_id)] = row

        # M7 ranking implementations may expose either resource_id or
        # option_id. Prefer resource_id and retain option_id as a compatibility
        # key without changing M7's schema.
        rank_by_resource: dict[str, dict[str, Any]] = {}
        for row in ranking_rows:
            resource_id = row.get("resource_id", row.get("option_id"))
            if resource_id is not None and str(resource_id):
                rank_by_resource[str(resource_id)] = row

        for proposal in proposal_rows:
            resource_id = proposal.get("resource_id")
            decision = self._enum_value(
                proposal.get("decision", "REQUIRES_APPROVAL")
            )
            blast = proposal.get("blast_radius", {})
            if not isinstance(blast, Mapping):
                blast = {}

            related = consensus_by_resource.get(str(resource_id), {})
            ranking = rank_by_resource.get(str(resource_id), {})

            raw_ids = (
                list(proposal.get("evidence_ids", ()))
                + list(related.get("evidence_ids", ()))
                + [proposal.get("evidence_id", "")]
                + [blast.get("evidence_id", "")]
                + [related.get("evidence_id", "")]
                + [ranking.get("evidence_id", "")]
            )
            ids = self._ground_evidence(raw_ids, valid_evidence)

            severity = (
                "HIGH"
                if decision in ("BLOCKED", "REQUIRES_APPROVAL")
                else "MEDIUM"
            )
            action = (
                "Do not apply this change; resolve the recorded contradiction "
                "or risk first."
                if decision == "BLOCKED"
                else (
                    "Submit this dry-run proposal for human approval."
                    if decision == "REQUIRES_APPROVAL"
                    else (
                        "Run the approved dry-run remediation workflow; no "
                        "direct infrastructure action is authorized."
                    )
                )
            )

            rec = self._recommend(
                {
                    "resource_id": resource_id,
                    "rule_id": "MODULE7_REMEDIATION",
                    "severity": severity,
                    "message": f"Module 7 remediation decision: {decision}.",
                    "evidence_ids": ids,
                },
                "RELIABILITY",
                ids,
                float(
                    proposal.get(
                        "confidence", related.get("confidence", 0.5)
                    )
                ),
                action=action,
                evidence_grounded=bool(ids),
            )
            recs.append(
                rec
                | {
                    "source_modules": ["MODULE7", "MODULE8"],
                    "module7_decision": decision,
                    "blast_radius": dict(blast),
                    "consensus": related,
                    "ranking": ranking,
                    "pareto_optimal": ranking.get("pareto_optimal"),
                }
            )

        recs = tuple(
            sorted(
                {r["recommendation_id"]: r for r in recs}.values(),
                key=lambda r: (
                    self.SEVERITY.get(r["severity"], 9),
                    r["recommendation_id"],
                ),
            )
        )

        security = self._security(recs)
        readiness = self._readiness(recs, agent_results)
        runtime = {
            "drift_count": sum(1 for r in recs if r["category"] == "DRIFT"),
            "categories": sorted(
                {
                    self._enum_value(getattr(x, "category", ""))
                    if not isinstance(x, Mapping)
                    else self._enum_value(x.get("category", ""))
                    for x in drift_assessments
                }
                - {""}
            ),
        }
        cost = {
            "optimization_count": sum(
                1 for r in recs if r["category"] == "COST"
            ),
            "pricing_status": (
                "ESTIMATED"
                if any(r["category"] == "COST" for r in recs)
                else "UNKNOWN"
            ),
        }
        conf = (
            confidence_assessment.to_dict()
            if hasattr(confidence_assessment, "to_dict")
            else {"overall": 0.5}
        )

        limitations = [
            "Recommendations are dry-run proposals only; no infrastructure action is executed.",
            "LLM wording is optional and cannot override deterministic evidence.",
        ]
        if any(not r["evidence_grounded"] for r in recs):
            limitations.append(
                "One or more recommendations have no evidence ID present in the "
                "supplied evidence registry and are therefore not evidence-grounded."
            )

        return AssuranceReport(
            project=project,
            provider=str(uir.get("provider", "UNKNOWN")),
            deployment_readiness=readiness,
            security=security,
            runtime=runtime,
            cost=cost,
            recommendations=recs,
            evidence=evidence_rows,
            confidence=conf,
            limitations=tuple(limitations),
        )

    @staticmethod
    def _enum_value(value: Any) -> str:
        raw = getattr(value, "value", value)
        return str(raw)

    @staticmethod
    def _ground_evidence(
        evidence_ids: Iterable[Any],
        valid_evidence: set[str],
    ) -> tuple[str, ...]:
        grounded = {
            str(e)
            for e in evidence_ids
            if e not in (None, "") and str(e) in valid_evidence
        }
        return tuple(sorted(grounded))

    def _recommend(
        self,
        finding: Mapping[str, Any],
        category: str,
        ids: tuple[str, ...],
        confidence: float,
        *,
        action: str | None = None,
        evidence_grounded: bool = False,
    ) -> dict[str, Any]:
        severity = str(finding.get("severity", "INFO")).upper()
        payload = {
            "cat": category,
            "resource": finding.get("resource_id"),
            "rule": finding.get("rule_id"),
            "ids": ids,
            "message": finding.get("message"),
        }
        recommendation_id = (
            "assurance-recommendation:"
            + hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, default=str
                ).encode()
            ).hexdigest()[:16]
        )
        selected_action = action or self.ACTIONS.get(
            category, "Review the evidence and apply an approved corrective action."
        )
        return {
            "recommendation_id": recommendation_id,
            "category": category,
            "priority": severity,
            "severity": severity,
            "title": f"{severity} {category.lower()} recommendation",
            "description": str(
                finding.get("message", "Evidence-supported issue")
            ),
            "action": selected_action,
            "resource_id": finding.get("resource_id"),
            "rule_id": finding.get("rule_id"),
            "evidence_ids": list(ids),
            "evidence_grounded": bool(evidence_grounded),
            "source_modules": [
                "MODULE4",
                "MODULE6" if category in ("DRIFT", "RELIABILITY") else "MODULE4",
            ],
            "confidence": round(max(0, min(1, confidence)), 6),
            "expected_security_impact": 1 if category == "SECURITY" else 0,
            "expected_cost_impact": 1 if category == "COST" else 0,
            "expected_reliability_impact": (
                1 if category in ("DRIFT", "RELIABILITY") else 0
            ),
            "explanation": {
                "problem": str(finding.get("message")),
                "evidence": list(ids),
                "recommended_action": selected_action,
                "limitations": (
                    "Only supplied evidence was used; intent/approval context "
                    "may be unavailable."
                ),
            },
        }

    def _category(self, finding: Mapping[str, Any]) -> str:
        rule = str(finding.get("rule_id", "")).upper()
        message = str(finding.get("message", "")).upper()
        text = f"{rule} {message}"

        if "COST" in rule:
            return "COST"
        if "DRIFT" in rule:
            return "DRIFT"
        if any(x in text for x in ("SECURITY", "CHECKOV", "INGRESS", "IAM")):
            return "SECURITY"
        if "SYNTAX" in rule:
            return "SYNTAX"
        return "DEPLOYMENT"

    def _security(self, recommendations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        recs = tuple(recommendations)
        levels = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        counts = {
            level: sum(
                1
                for r in recs
                if r["category"] == "SECURITY"
                and r["severity"] == level
            )
            for level in levels
        }
        penalty = (
            counts["CRITICAL"] * 45
            + counts["HIGH"] * 25
            + counts["MEDIUM"] * 10
            + counts["LOW"] * 3
        )
        security_recs = [
            r for r in recs if r["category"] == "SECURITY"
        ]
        confidence = sum(
            r["confidence"] for r in security_recs
        ) / max(1, len(security_recs))
        return {
            "score": max(0, 100 - penalty),
            **counts,
            "confidence": round(confidence, 6),
        }

    def _readiness(
        self,
        recommendations: Iterable[Mapping[str, Any]],
        results: Iterable[Any],
    ) -> dict[str, Any]:
        recs = tuple(recommendations)
        results = tuple(results)
        penalty = sum(
            {
                "CRITICAL": 35,
                "HIGH": 20,
                "MEDIUM": 8,
                "LOW": 2,
                "INFO": 0,
                "NONE": 0,
            }.get(r["severity"], 0)
            for r in recs
        )
        failed = sum(
            1
            for x in results
            if self._enum_value(getattr(x, "status", "")) == "FAILED"
        )
        return {
            "score": max(0, round(100 - penalty - failed * 15, 2)),
            "components": {
                "findings_penalty": penalty,
                "agent_failure_penalty": failed * 15,
            },
        }
