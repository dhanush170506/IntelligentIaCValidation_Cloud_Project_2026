import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:9000")
AI_ENGINE_MOCK = os.getenv("AI_ENGINE_MOCK", "true").lower() == "true"
AI_ENGINE_TIMEOUT = int(os.getenv("AI_ENGINE_TIMEOUT", "30"))

MOCK_RESPONSE: Dict[str, Any] = {
    "status": "PASS",
    "security_score": 85,
    "drift_score": 20,
    "confidence": 0.91,
    "findings": [],
    "recommendations": [
        "Use specific AMI IDs instead of 'latest' in production",
        "Enable encryption at rest for EBS volumes",
    ],
    "source": "mock",
}


def _mock_validation(
    upload_id: str, filename: str, file_type: str, content: str
) -> Dict[str, Any]:
    """Return a clearly marked dummy response for mock mode."""
    logger.info(
        "MOCK AI ENGINE: Simulating validation for %s (%s)", filename, upload_id
    )
    result = {**MOCK_RESPONSE, "upload_id": upload_id}
    return result


async def validate_iac(
    upload_id: str, filename: str, file_type: str, content: str
) -> Dict[str, Any]:
    """
    Send IaC content to the AI engine for validation.

    In mock mode, returns a dummy response without calling the real engine.
    In real mode, sends an HTTP POST to AI_ENGINE_URL/validate.

    Expected AI engine request format:
        {
            "upload_id": "...",
            "filename": "...",
            "file_type": "terraform",
            "content": "..."
        }

    Expected AI engine response format:
        {
            "status": "PASS" | "FAIL",
            "security_score": 85,
            "drift_score": 20,
            "confidence": 0.91,
            "findings": [],
            "recommendations": []
        }

    Returns the AI engine response dict, or a structured error dict on failure.
    """
    if AI_ENGINE_MOCK:
        return _mock_validation(upload_id, filename, file_type, content)

    payload = {
        "upload_id": upload_id,
        "filename": filename,
        "file_type": file_type,
        "content": content,
    }

    try:
        async with httpx.AsyncClient(timeout=AI_ENGINE_TIMEOUT) as client:
            response = await client.post(
                f"{AI_ENGINE_URL.rstrip('/')}/validate",
                json=payload,
            )

        if response.status_code != 200:
            logger.warning(
                "AI engine returned HTTP %s: %s",
                response.status_code,
                response.text[:200],
            )
            return {
                "status": "ERROR",
                "error": f"AI engine returned HTTP {response.status_code}",
                "upload_id": upload_id,
            }

        result = response.json()

        required_keys = {"status", "security_score", "drift_score", "confidence"}
        if not required_keys.issubset(result.keys()):
            missing = required_keys - result.keys()
            logger.warning("AI engine response missing keys: %s", missing)
            return {
                "status": "ERROR",
                "error": f"AI engine response missing keys: {missing}",
                "upload_id": upload_id,
            }

        result["upload_id"] = upload_id
        return result

    except httpx.TimeoutException:
        logger.error("AI engine request timed out after %ss", AI_ENGINE_TIMEOUT)
        return {
            "status": "ERROR",
            "error": f"AI engine request timed out after {AI_ENGINE_TIMEOUT}s",
            "upload_id": upload_id,
        }
    except httpx.ConnectError:
        logger.error("AI engine unavailable at %s", AI_ENGINE_URL)
        return {
            "status": "ERROR",
            "error": f"AI engine unavailable at {AI_ENGINE_URL}",
            "upload_id": upload_id,
        }
    except Exception as exc:
        logger.exception("Unexpected error calling AI engine: %s", exc)
        return {
            "status": "ERROR",
            "error": f"Unexpected error: {exc}",
            "upload_id": upload_id,
        }
