from __future__ import annotations
from src.ml_model.module4_multi_agent.agent_result import AgentResult
from src.ml_model.module4_multi_agent.agent_schema import (
    AgentStatus,
    AgentType,
)

from .bedrock_adapter import BedrockAdapter
from .bedrock_client import (
    MockBedrockClient,
    BedrockClientError,
)
from .bedrock_schema import (
    BedrockRequest,
    BedrockResponse,
    BedrockSchemaError,
)


FAILURES = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        FAILURES.append(message)


def test_request_schema() -> None:
    request = BedrockRequest(
        model_id="mock-model",
        system_prompt="System prompt",
        user_prompt="User prompt",
    )

    check(
        request.model_id == "mock-model",
        "BedrockRequest stores model_id",
    )

    check(
        request.temperature == 0.0,
        "Default temperature is deterministic",
    )

    try:
        BedrockRequest(
            model_id="",
            system_prompt="System",
            user_prompt="User",
        )
        check(False, "Empty model_id rejected")
    except BedrockSchemaError:
        check(True, "Empty model_id rejected")


def test_response_schema() -> None:
    response = BedrockResponse(
        model_id="mock-model",
        text="analysis",
        confidence=0.9,
    )

    check(
        response.text == "analysis",
        "BedrockResponse stores text",
    )

    check(
        response.to_dict()["confidence"] == 0.9,
        "BedrockResponse serializes confidence",
    )

    try:
        BedrockResponse(
            model_id="mock-model",
            text="analysis",
            confidence=1.5,
        )
        check(False, "Invalid confidence rejected")
    except BedrockSchemaError:
        check(True, "Invalid confidence rejected")


def test_mock_client() -> None:
    client = MockBedrockClient(
        response_text="Mock assurance analysis",
        confidence=0.95,
    )

    request = BedrockRequest(
        model_id="mock-model",
        system_prompt="System",
        user_prompt="Analyze this.",
    )

    response = client.invoke(request)

    check(
        isinstance(response, BedrockResponse),
        "Mock client returns BedrockResponse",
    )

    check(
        response.text == "Mock assurance analysis",
        "Mock response text preserved",
    )

    check(
        response.confidence == 0.95,
        "Mock confidence preserved",
    )

    check(
        client.last_request == request,
        "Mock client records last request",
    )


def test_adapter() -> None:
    client = MockBedrockClient(
        response_text="Grounded infrastructure analysis",
        confidence=0.92,
    )

    adapter = BedrockAdapter(
        client,
        model_id="mock-model",
    )

    agent_result = AgentResult(
        agent_type=AgentType.SECURITY_VALIDATION,
        status=AgentStatus.COMPLETED,
        message="No security issues detected.",
        confidence=1.0,
    )

    response = adapter.analyze(
        agent_results=(agent_result,),
        uir={
            "provider": "Terraform",
            "resources": [],
            "dependencies": [],
        },
    )

    check(
        response.text == "Grounded infrastructure analysis",
        "Adapter invokes client",
    )

    check(
        client.last_request is not None,
        "Adapter generated BedrockRequest",
    )

    check(
        "SECURITY_VALIDATION"
        in client.last_request.user_prompt,
        "Agent result appears in prompt",
    )

    check(
        "Terraform" in client.last_request.user_prompt,
        "UIR appears in prompt",
    )

def test_empty_agent_results() -> None:
    adapter = BedrockAdapter(
        MockBedrockClient(),
        model_id="mock-model",
    )

    try:
        adapter.analyze(agent_results=())
        check(False, "Empty agent results rejected")
    except Exception:
        check(True, "Empty agent results rejected")


def main() -> int:
    print("=" * 72)
    print("MODULE 5.1 - BEDROCK INTEGRATION UNIT TEST")
    print("=" * 72)

    test_request_schema()
    test_response_schema()
    test_mock_client()
    test_adapter()
    test_empty_agent_results()

    print()

    if FAILURES:
        print("FAILED")
        for failure in FAILURES:
            print(" -", failure)
        return 1

    print("ALL MODULE 5.1 BEDROCK TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())