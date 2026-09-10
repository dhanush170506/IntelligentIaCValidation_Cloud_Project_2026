"""coordinator_agent.py.

Coordinator Agent for Module 4 — Intelligent Multi-Agent Framework.

The Coordinator orchestrates already-implemented Module 4 agents. It does
not contain domain-specific validation logic and does not call external
tools, AWS services, Bedrock, or LLMs.

Lifecycle:
    BaseAgent.run()
        -> CoordinatorAgent.validate_input()
        -> CoordinatorAgent.execute()
            -> child_agent.run(...)
            -> collect AgentResults
            -> aggregate findings/evidence
            -> return coordinator AgentResult
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

try:
    from .agent_result import AgentResult
    from .agent_schema import AgentFinding, AgentStatus, AgentType
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentFinding, AgentStatus, AgentType  # type: ignore[no-redef]
    from base_agent import BaseAgent  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


class CoordinatorAgentError(Exception):
    """Raised when Coordinator Agent configuration or execution is invalid."""


class CoordinatorAgent(BaseAgent):
    """Orchestrates a collection of Module 4 agents.

    Every child agent receives the same ``*args``/``**kwargs`` supplied to
    ``run()``. This keeps the coordinator generic: concrete agents can
    inspect only the inputs they require.

    Child failures are isolated. A failed child produces its normal FAILED
    ``AgentResult`` and does not prevent the remaining agents from running.
    The coordinator reports FAILED if at least one child failed; otherwise
    it reports COMPLETED.
    """

    def __init__(self, agents: Iterable[BaseAgent]) -> None:
        try:
            self._agents = tuple(agents)
        except TypeError as exc:
            raise CoordinatorAgentError(
                "agents must be an iterable of BaseAgent instances"
            ) from exc

        if not self._agents:
            raise CoordinatorAgentError(
                "CoordinatorAgent requires at least one child agent"
            )

        for index, agent in enumerate(self._agents):
            if not isinstance(agent, BaseAgent):
                raise CoordinatorAgentError(
                    f"agents[{index}] must be a BaseAgent, got "
                    f"{type(agent).__name__}"
                )
            if agent.agent_type is AgentType.COORDINATOR:
                raise CoordinatorAgentError(
                    "CoordinatorAgent cannot contain another COORDINATOR agent"
                )

    @property
    def agent_type(self) -> AgentType:
        """Identify this agent as the Module 4 coordinator."""
        return AgentType.COORDINATOR

    @property
    def agents(self) -> tuple[BaseAgent, ...]:
        """Return the configured child agents in execution order."""
        return self._agents

    def validate_input(self, *args: Any, **kwargs: Any) -> None:
        """Validate coordinator inputs.

        The coordinator itself has no mandatory UIR/runtime input because
        different child agents may require different context. The only
        required configuration is that at least one child agent exists.
        """
        if not self._agents:
            raise CoordinatorAgentError(
                "CoordinatorAgent requires at least one child agent"
            )

    def execute(self, *args: Any, **kwargs: Any) -> AgentResult:
        """Run all child agents and aggregate their results."""
        results: list[AgentResult] = []

        for index, agent in enumerate(self._agents):
            logger.info(
                "Coordinator: executing child agent %d/%d: %s",
                index + 1,
                len(self._agents),
                agent.agent_type.value,
            )
            result = agent.run(*args, **kwargs)
            results.append(result)

        findings: list[AgentFinding] = []
        evidence_ids: list[str] = []

        for result in results:
            findings.extend(result.findings)
            for evidence_id in result.evidence_ids:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)

        failed_count = sum(
            result.status is AgentStatus.FAILED for result in results
        )
        completed_count = sum(
            result.status is AgentStatus.COMPLETED for result in results
        )
        skipped_count = sum(
            result.status is AgentStatus.SKIPPED for result in results
        )

        status = (
            AgentStatus.FAILED
            if failed_count
            else AgentStatus.COMPLETED
        )

        confidence = (
            sum(result.confidence for result in results) / len(results)
        )

        if failed_count:
            message = (
                f"Coordinator completed with partial failure: "
                f"{completed_count} completed, {skipped_count} skipped, "
                f"{failed_count} failed."
            )
        else:
            message = (
                f"Coordinator completed successfully: "
                f"{completed_count} completed, {skipped_count} skipped."
            )

        return AgentResult(
            agent_type=self.agent_type,
            status=status,
            findings=tuple(findings),
            evidence_ids=tuple(evidence_ids),
            confidence=confidence,
            message=message,
            metadata={
                "child_agent_count": len(results),
                "completed_count": completed_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "child_results": [result.to_dict() for result in results],
            },
        )


__all__ = ["CoordinatorAgent", "CoordinatorAgentError"]
