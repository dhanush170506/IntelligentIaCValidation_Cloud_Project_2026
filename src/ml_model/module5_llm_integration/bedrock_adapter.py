from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

try:
    from .bedrock_client import BedrockClient
    from .bedrock_schema import BedrockResponse, BedrockRequest
    from .prompt_engineering import AssurancePromptEngineer
except ImportError:
    from bedrock_client import BedrockClient
    from bedrock_schema import BedrockResponse, BedrockRequest
    from prompt_engineering import AssurancePromptEngineer


class BedrockAdapterError(RuntimeError):
    """Raised when Module 4 context cannot be converted safely."""


class BedrockAdapter:
    """
    Converts structured Module 4 assurance context into an LLM request.

    Prompt construction is delegated to AssurancePromptEngineer so that
    prompt policy and Bedrock transport remain separate concerns.
    """

    def __init__(
        self,
        client: BedrockClient,
        *,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        system_prompt: Optional[str] = None,
        prompt_engineer: Optional[AssurancePromptEngineer] = None,
    ) -> None:
        self.client = client
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens

        if prompt_engineer is not None:
            self.prompt_engineer = prompt_engineer
        else:
            self.prompt_engineer = AssurancePromptEngineer(
                system_prompt=system_prompt,
            )

    def analyze(
        self,
        *,
        agent_results: Iterable[Any],
        uir: Optional[Mapping[str, Any]] = None,
        evidence: Iterable[Any] = (),
    ) -> BedrockResponse:
        """
        Build an evidence-grounded prompt and invoke the configured
        Bedrock client.
        """

        try:
            engineered_prompt = self.prompt_engineer.build(
                agent_results=agent_results,
                uir=uir,
                evidence=evidence,
            )

            request = BedrockRequest(
                model_id=self.model_id,
                system_prompt=engineered_prompt.system_prompt,
                user_prompt=engineered_prompt.user_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                metadata={
                    **dict(engineered_prompt.metadata),
                    "prompt_engineering": "AssurancePromptEngineer",
                },
            )

            return self.client.invoke(request)

        except Exception as exc:
            if isinstance(exc, BedrockAdapterError):
                raise

            raise BedrockAdapterError(
                f"Unable to construct or invoke Bedrock request: {exc}"
            ) from exc