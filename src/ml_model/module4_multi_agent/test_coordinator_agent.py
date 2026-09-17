"""Tests for coordinator_agent.py."""

from __future__ import annotations

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from .base_agent import BaseAgent
    from .coordinator_agent import CoordinatorAgent, CoordinatorAgentError
except ImportError:
    from agent_result import AgentResult
    from agent_schema import AgentFinding, AgentSeverity, AgentStatus, AgentType
    from base_agent import BaseAgent
    from coordinator_agent import CoordinatorAgent, CoordinatorAgentError


class DummyAgent(BaseAgent):
    def __init__(
        self,
        agent_type: AgentType,
        *,
        status: AgentStatus = AgentStatus.COMPLETED,
        fail: bool = False,
        confidence: float = 0.8,
    ) -> None:
        self._agent_type = agent_type
        self._status = status
        self._fail = fail
        self._confidence = confidence

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    def validate_input(self, *args, **kwargs) -> None:
        pass

    def execute(self, *args, **kwargs) -> AgentResult:
        if self._fail:
            raise RuntimeError("dummy failure")

        finding = AgentFinding(
            agent_type=self.agent_type,
            severity=AgentSeverity.MEDIUM,
            message=f"{self.agent_type.value} finding",
            confidence=self._confidence,
            evidence_ids=(f"evidence-{self.agent_type.value}",),
        )
        return AgentResult(
            agent_type=self.agent_type,
            status=self._status,
            message=f"{self.agent_type.value} finished",
            confidence=self._confidence,
            findings=(finding,),
            evidence_ids=(f"evidence-{self.agent_type.value}",),
        )


def test_successful_coordination() -> None:
    agents = (
        DummyAgent(AgentType.SYNTAX_VALIDATION, confidence=0.8),
        DummyAgent(AgentType.SECURITY_VALIDATION, confidence=0.6),
    )
    result = CoordinatorAgent(agents).run(context="demo")

    assert result.agent_type is AgentType.COORDINATOR
    assert result.status is AgentStatus.COMPLETED
    assert len(result.findings) == 2
    assert result.confidence == 0.7
    assert result.evidence_ids == (
        "evidence-SYNTAX_VALIDATION",
        "evidence-SECURITY_VALIDATION",
    )
    assert result.metadata["child_agent_count"] == 2
    assert len(result.metadata["child_results"]) == 2


def test_child_failure_is_isolated() -> None:
    agents = (
        DummyAgent(AgentType.SYNTAX_VALIDATION, confidence=0.8),
        DummyAgent(AgentType.SECURITY_VALIDATION, fail=True),
        DummyAgent(AgentType.DEPLOYMENT_VALIDATION, confidence=0.9),
    )
    result = CoordinatorAgent(agents).run(context="demo")

    assert result.status is AgentStatus.FAILED
    assert len(result.metadata["child_results"]) == 3
    assert result.metadata["completed_count"] == 2
    assert result.metadata["failed_count"] == 1
    assert len(result.findings) == 2


def test_skipped_child() -> None:
    agent = DummyAgent(
        AgentType.DRIFT_DETECTION,
        status=AgentStatus.SKIPPED,
        confidence=0.0,
    )
    result = CoordinatorAgent((agent,)).run()

    assert result.status is AgentStatus.COMPLETED
    assert result.metadata["skipped_count"] == 1


def test_empty_agents_rejected() -> None:
    try:
        CoordinatorAgent(())
        raise AssertionError("empty agent collection should be rejected")
    except CoordinatorAgentError:
        pass


def test_nested_coordinator_rejected() -> None:
    child = DummyAgent(AgentType.SYNTAX_VALIDATION)
    coordinator = CoordinatorAgent((child,))
    try:
        CoordinatorAgent((coordinator,))
        raise AssertionError("nested coordinator should be rejected")
    except CoordinatorAgentError:
        pass


def test_invalid_agent_rejected() -> None:
    try:
        CoordinatorAgent((object(),))
        raise AssertionError("non-agent should be rejected")
    except CoordinatorAgentError:
        pass


if __name__ == "__main__":
    tests = [
        test_successful_coordination,
        test_child_failure_is_isolated,
        test_skipped_child,
        test_empty_agents_rejected,
        test_nested_coordinator_rejected,
        test_invalid_agent_rejected,
    ]
    for test_fn in tests:
        test_fn()
        print(f"[PASS] {test_fn.__name__}")
    print("All Coordinator Agent tests PASSED.")
