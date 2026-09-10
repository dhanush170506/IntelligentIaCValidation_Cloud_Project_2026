from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


class BedrockSchemaError(ValueError):
    """Raised when a Bedrock integration schema object is invalid."""


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BedrockSchemaError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _require_confidence(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BedrockSchemaError(
            f"{field_name} must be a number between 0.0 and 1.0"
        )

    value = float(value)

    if not 0.0 <= value <= 1.0:
        raise BedrockSchemaError(
            f"{field_name} must be between 0.0 and 1.0"
        )

    return value


@dataclass(frozen=True, kw_only=True)
class BedrockRequest:
    """Provider-independent request sent to an LLM backend."""

    model_id: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.0
    max_tokens: int = 2000
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.model_id, "model_id")
        _require_non_empty_string(self.system_prompt, "system_prompt")
        _require_non_empty_string(self.user_prompt, "user_prompt")

        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature, (int, float)
        ):
            raise BedrockSchemaError(
                "temperature must be a number"
            )

        if not 0.0 <= float(self.temperature) <= 1.0:
            raise BedrockSchemaError(
                "temperature must be between 0.0 and 1.0"
            )

        if isinstance(self.max_tokens, bool) or not isinstance(
            self.max_tokens, int
        ):
            raise BedrockSchemaError(
                "max_tokens must be an integer"
            )

        if self.max_tokens <= 0:
            raise BedrockSchemaError(
                "max_tokens must be greater than zero"
            )

        if self.metadata is not None and not isinstance(
            self.metadata, dict
        ):
            raise BedrockSchemaError(
                "metadata must be a dictionary or None"
            )


@dataclass(frozen=True, kw_only=True)
class BedrockResponse:
    """Provider-independent response returned by an LLM backend."""

    model_id: str
    text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    stop_reason: Optional[str] = None
    confidence: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.model_id, "model_id")
        _require_non_empty_string(self.text, "text")
        _require_confidence(self.confidence, "confidence")

        for name, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise BedrockSchemaError(
                        f"{name} must be an integer or None"
                    )
                if value < 0:
                    raise BedrockSchemaError(
                        f"{name} must be non-negative"
                    )

        if self.stop_reason is not None:
            _require_non_empty_string(
                self.stop_reason,
                "stop_reason",
            )

        if self.metadata is not None and not isinstance(
            self.metadata, dict
        ):
            raise BedrockSchemaError(
                "metadata must be a dictionary or None"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "stop_reason": self.stop_reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }