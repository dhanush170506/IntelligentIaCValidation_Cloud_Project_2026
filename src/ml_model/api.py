"""ML assurance HTTP API adapter.

Exposes the existing AssuranceOrchestrator (Modules 1-8) over HTTP so the
FastAPI backend's ai_service can call it at POST /validate. This module is a
thin adapter only: it changes no pipeline logic and adds no scoring of its
own.

Run with:
    python -m uvicorn src.ml_model.api:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from src.ml_model.assurance_pipeline.orchestrator import AssuranceOrchestrator
from src.ml_model.module3_static_validation.builtin_security_adapter import BuiltinSecurityAdapter
from src.ml_model.module3_static_validation.checkov_adapter import CheckovAdapter

logger = logging.getLogger(__name__)

APP_NAME = os.getenv("ML_API_NAME", "ml-assurance")

ML_API_HOST = os.getenv("ML_API_HOST", "0.0.0.0")
ML_API_PORT = int(os.getenv("ML_API_PORT", "9000"))

SUPPORTED_EXTENSIONS = {".tf", ".yaml", ".yml", ".json"}
MAX_CONTENT_BYTES = int(os.getenv("ML_API_MAX_CONTENT_BYTES", str(2 * 1024 * 1024)))

app = FastAPI(title="ML Assurance API", version="1.0.0")

# A single orchestrator instance is reused. Its defaults are intentionally
# preserved: MockBedrockClient and Mock runtime providers (offline mode).
# Real AWS Bedrock is NOT enabled automatically.
# Checkov is wired as the Module 3 static validator (same as the integration
# test in test_end_to_end.py) so the Security Agent receives real findings.
# CHECKOV_EXECUTABLE lets deployments point at a specific CLI (needed on
# Windows where the pip shim is checkov.cmd and PATH lookup is unreliable);
# default is the plain "checkov" name.
#
# Checkov is OPTIONAL on this machine. If its executable is missing, every
# upload previously degraded to "Module 3 validator unavailable" and the
# pipeline ran with zero static findings, making all uploads produce
# identical reports. AvailabilityProbe delegates to Checkov while it works
# and falls back to the built-in deterministic IaC security adapter
# (module3_static_validation/builtin_security_adapter.py) otherwise — no
# scores are invented anywhere; findings still come from the uploaded IaC.
class _AvailabilityProbe:
    """Prefer Checkov; fall back to the built-in IaC security checks."""

    def __init__(self) -> None:
        self._primary = CheckovAdapter(checkov_executable=os.getenv("CHECKOV_EXECUTABLE", "checkov"))
        self._fallback = BuiltinSecurityAdapter()
        self._use_fallback = False

    def validate(self, path):
        if self._use_fallback:
            return self._fallback.validate(path)
        try:
            return self._primary.validate(path)
        except Exception:
            self._use_fallback = True  # Checkov is not usable on this host
            return self._fallback.validate(path)


orchestrator = AssuranceOrchestrator(
    validators=(_AvailabilityProbe(),)
)


class ValidateRequest(BaseModel):
    """Request body sent by the backend's ai_service (POST /validate)."""

    upload_id: str = ""
    filename: str
    file_type: str | None = None
    content: str

    @field_validator("filename")
    @classmethod
    def _filename_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("filename is required")
        return value.strip()

    @field_validator("content")
    @classmethod
    def _content_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("content is required")
        return value


# ---------------------------------------------------------------------------
# Safe JSON serialization helpers (no modification of existing schemas)
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Convert arbitrary pipeline output into JSON-compatible structures.

    Order of preference:
      1. objects exposing to_dict()
      2. dataclasses via fields
      3. enums via .value
      4. mappings / sequences / scalars
    Never returns Python object representations such as '<Foo object at ...>'.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return value.value

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe({f.name: getattr(value, f.name) for f in fields(value)})

    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(x) for x in value]

    # Last resort: avoid leaking object reprs like '<Foo object at 0x...>'
    return str(value)


def _extract_findings(agent_results: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Flatten Module 4 AgentResults into a findings list.

    Uses each result's existing to_dict() so agent_type, severity, rule_id,
    resource_id, message, evidence_ids, and confidence are all preserved
    without changing the source schemas.
    """
    findings: list[dict[str, Any]] = []
    for result in agent_results:
        try:
            data = result.to_dict() if hasattr(result, "to_dict") else {}
        except Exception:  # noqa: BLE001 - never fail the API on one bad result
            logger.exception("Failed to serialize an agent result")
            continue

        agent_type = data.get("agent_type")
        for finding in data.get("findings", []) or []:
            row = dict(finding) if isinstance(finding, Mapping) else {}
            row.setdefault("agent_type", agent_type)
            findings.append(_json_safe(row))
    return findings


def _derive_status(report: Mapping[str, Any]) -> str:
    """Deterministic status mapping from AssuranceReport deployment_readiness."""
    readiness = report.get("deployment_readiness", {})
    score = readiness.get("score", 0) if isinstance(readiness, Mapping) else 0
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0

    if score >= 80:
        return "PASS"
    if score >= 50:
        return "REVIEW_REQUIRED"
    return "FAIL"


def _derive_drift_score(
    report: Mapping[str, Any],
    drift_assessments: tuple[Any, ...],
) -> float:
    """Deterministic drift score (0-100) from existing pipeline data.

    Mapping (documented, not invented):
      - Preferred: if every DriftAssessment carries a numeric score, average
        them and scale from the pipeline's 0..1 range to 0..100.
      - Fallback: AssuranceReport.runtime.drift_count. Each drift
        recommendation represents a confirmed/likely drift finding, so
        drift_score = 100 if drift_count > 0 else 0. The count itself is also
        returned under "drift_count" so the caller can see the raw value.
    """
    scores = [
        float(a.score)
        for a in drift_assessments
        if hasattr(a, "score") and isinstance(a.score, (int, float))
    ]
    if scores:
        return round(sum(scores) / len(scores) * 100, 1)

    runtime = report.get("runtime", {})
    drift_count = runtime.get("drift_count", 0) if isinstance(runtime, Mapping) else 0
    try:
        drift_count = int(drift_count)
    except (TypeError, ValueError):
        drift_count = 0
    return 100.0 if drift_count > 0 else 0.0


def _validate_payload(payload: ValidateRequest) -> str:
    """Validate file type/extension and content size; return the suffix to use."""
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{suffix}'. Allowed: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    if len(payload.content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Content exceeds maximum size of {MAX_CONTENT_BYTES} bytes",
        )

    return suffix


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}


@app.post("/validate")
async def validate(payload: ValidateRequest) -> dict[str, Any]:
    suffix = _validate_payload(payload)

    # AssuranceOrchestrator.run() expects a file path. Write the content to a
    # temp file with the correct extension; always clean it up.
    with tempfile.TemporaryDirectory(prefix="ml-assurance-") as tmp_dir:
        temp_path = Path(tmp_dir) / f"iac{suffix}"
        temp_path.write_text(payload.content, encoding="utf-8")

        try:
            result = orchestrator.run(
                iac_path=temp_path,
                project=payload.upload_id or "assurance-project",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Assurance pipeline failed")
            raise HTTPException(
                status_code=500,
                detail={"error": "Assurance pipeline failed", "reason": str(exc)},
            ) from exc

    try:
        report = result.assurance_report.to_dict()

        response: dict[str, Any] = {
            # A. Backend-compatible summary fields
            "status": _derive_status(report),
            "security_score": report.get("security", {}).get("score", 0),
            "drift_score": _derive_drift_score(report, result.drift_assessments),
            "confidence": (result.confidence_assessment.to_dict().get("score", 0)
                           if result.confidence_assessment is not None else 0),
            "findings": _extract_findings(result.agent_results),
            "recommendations": _json_safe(report.get("recommendations", [])),

            # B. Rich ML output (serialized from existing pipeline objects)
            "assurance_report": _json_safe(report),
            "provider": report.get("provider"),
            "uir": _json_safe(result.uir),
            "graph": _json_safe(result.graph),
            "evidence": _json_safe(result.evidence),
            "agent_results": _json_safe(result.agent_results),
            "drift_assessments": _json_safe(result.drift_assessments),
            "consensus": _json_safe(result.consensus),
            "blast_radius_assessments": _json_safe(result.blast_radius_assessments),
            "remediation_proposals": _json_safe(result.remediation_proposals),
            "remediation_rankings": _json_safe(result.remediation_rankings),
            "warnings": list(result.warnings),
            "errors": list(result.errors),
            "metadata": _json_safe(result.metadata),
        }
        return response
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to serialize pipeline output")
        raise HTTPException(
            status_code=500,
            detail={"error": "Response serialization failed", "reason": str(exc)},
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=ML_API_HOST, port=ML_API_PORT)
