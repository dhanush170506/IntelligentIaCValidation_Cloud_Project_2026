from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

try:
    from .bedrock_schema import BedrockRequest, BedrockResponse
except ImportError:
    from bedrock_schema import BedrockRequest, BedrockResponse


class BedrockClientError(RuntimeError):
    """Raised when an LLM backend request cannot be completed."""


class BedrockClient(ABC):
    """Provider-independent interface for an LLM backend."""

    @abstractmethod
    def invoke(self, request: BedrockRequest) -> BedrockResponse:
        """Execute one LLM request."""
        raise NotImplementedError


class MockBedrockClient(BedrockClient):
    """
    Deterministic local Bedrock substitute.

    Used for unit tests and development when AWS credentials/network
    access are unavailable.
    """

    def __init__(
        self,
        response_text: str = (
            "The infrastructure analysis completed successfully."
        ),
        confidence: float = 0.90,
    ) -> None:
        self.response_text = response_text
        self.confidence = confidence
        self.last_request: Optional[BedrockRequest] = None

    def invoke(self, request: BedrockRequest) -> BedrockResponse:
        if not isinstance(request, BedrockRequest):
            raise BedrockClientError(
                "request must be a BedrockRequest"
            )

        self.last_request = request

        return BedrockResponse(
            model_id=request.model_id,
            text=self.response_text,
            input_tokens=None,
            output_tokens=None,
            stop_reason="mock",
            confidence=self.confidence,
            metadata={
                "backend": "mock",
            },
        )


class AwsBedrockClient(BedrockClient):
    """
    Amazon Bedrock Runtime client.

    boto3 is imported lazily so the rest of the project can still be
    imported and unit-tested when boto3/AWS credentials are unavailable.
    """

    def __init__(
        self,
        *,
        region_name: str = "us-east-1",
        boto3_client: Any = None,
    ) -> None:
        self.region_name = region_name

        if boto3_client is not None:
            self._client = boto3_client
            return

        try:
            import boto3
        except ImportError as exc:
            raise BedrockClientError(
                "boto3 is required for AwsBedrockClient. "
                "Install it with: pip install boto3"
            ) from exc

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region_name,
        )

    def invoke(self, request: BedrockRequest) -> BedrockResponse:
        if not isinstance(request, BedrockRequest):
            raise BedrockClientError(
                "request must be a BedrockRequest"
            )

        payload = {
            "inputText": request.user_prompt,
            "textGenerationConfig": {
                "temperature": request.temperature,
                "maxTokenCount": request.max_tokens,
            },
        }

        try:
            response = self._client.invoke_model(
                modelId=request.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
        except Exception as exc:
            raise BedrockClientError(
                f"Bedrock invocation failed: {exc}"
            ) from exc

        try:
            raw_body = response["body"]

            if hasattr(raw_body, "read"):
                raw_body = raw_body.read()

            if isinstance(raw_body, bytes):
                raw_body = raw_body.decode("utf-8")

            data = json.loads(raw_body)

            results = data.get("results", [])

            if not results:
                raise BedrockClientError(
                    "Bedrock response contains no results"
                )

            first_result = results[0]

            text = first_result.get("outputText")

            if not isinstance(text, str) or not text.strip():
                raise BedrockClientError(
                    "Bedrock response contains no usable outputText"
                )

            return BedrockResponse(
                model_id=request.model_id,
                text=text,
                input_tokens=data.get("inputTextTokenCount"),
                output_tokens=data.get("resultsTokenCount"),
                stop_reason=first_result.get("completionReason"),
                confidence=0.0,
                metadata={
                    "backend": "aws_bedrock",
                    "raw_response_keys": tuple(data.keys()),
                },
            )

        except BedrockClientError:
            raise
        except Exception as exc:
            raise BedrockClientError(
                f"Unable to parse Bedrock response: {exc}"
            ) from exc