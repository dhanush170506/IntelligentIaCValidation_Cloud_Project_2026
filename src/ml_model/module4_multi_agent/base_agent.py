"""base_agent.py.

Defines the abstract base class every Module 4 agent — the future
Coordinator Agent as well as each specialized agent (syntax
validation, security validation, deployment validation, drift
detection, cost analysis, evidence collection) — is built on.

`BaseAgent` provides only the common execution lifecycle:

    PENDING -> RUNNING -> COMPLETED / FAILED

and the two extension points every concrete agent must implement
(`validate_input()` and `execute()`). It defines no agent-specific
analysis logic of its own, and calls none of Terraform, Checkov,
TFLint, CFN-Lint, any AWS API (including CloudWatch, AWS Config, or
Bedrock), or any LLM — those integrations belong to the concrete
agents that will be built on top of this foundation in a later task.

`run()` is deliberately generic over its input (`*args, **kwargs`)
rather than accepting fixed parameters for the Unified Intermediate
Representation, resource/dependency graphs, `ValidationReport`s,
runtime telemetry, or configuration state: different concrete agents
will need different subsets of those inputs, and hard-coding all of
them into this base class now would force every future agent to
depend on inputs it doesn't use. Each concrete agent's
`validate_input()`/`execute()` overrides are free to declare whatever
specific keyword arguments that agent actually needs.

Requirements:
    - Python 3.12

Typical usage (see `test_agent_foundation.py` for a complete example):
    class MyAgent(BaseAgent):
        @property
        def agent_type(self) -> AgentType:
            return AgentType.SYNTAX_VALIDATION

        def validate_input(self, *, uir=None, **kwargs) -> None:
            if uir is None:
                raise ValueError("uir is required")

        def execute(self, *, uir=None, **kwargs) -> AgentResult:
            ...
            return AgentResult(...)

    result = MyAgent().run(uir=my_uir)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

# Relative imports are used since this module lives inside the
# `module4_multi_agent` package alongside `agent_result.py` and
# `agent_schema.py`. A fallback to absolute (flat) imports is provided
# so this module also runs correctly when executed or imported
# directly without package context, matching the same pattern used
# throughout Module 3 (e.g. `validation_result.py`).
try:
    from .agent_result import AgentResult
    from .agent_schema import AgentStatus, AgentType
except ImportError:
    from agent_result import AgentResult  # type: ignore[no-redef]
    from agent_schema import AgentStatus, AgentType  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

if not logger.handlers:
    # Configure a default handler only if the module is used standalone
    # (i.e. the host application hasn't already configured logging).
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------
class BaseAgent(ABC):
    """Abstract base class providing the common Module 4 agent lifecycle.

    Concrete subclasses implement `agent_type`, `validate_input()`, and
    `execute()`. `run()` is the one lifecycle every agent shares and is
    not meant to be overridden:

        PENDING -> RUNNING -> COMPLETED / FAILED

    `run()` calls `validate_input()` first (the "PENDING" input check),
    then `execute()` (the "RUNNING" analysis step), and converts any
    exception raised by either step into a `FAILED` `AgentResult`
    rather than letting it propagate — so one agent's failure never
    crashes whatever orchestrates multiple agents (the future
    Coordinator Agent).

    This conversion is deliberately narrow, so it does not hide
    programming errors it shouldn't:
        - Only `Exception` subclasses raised by `validate_input()` or
          `execute()` are converted. `BaseException` subclasses used
          for control flow (`KeyboardInterrupt`, `SystemExit`,
          `GeneratorExit`) are never caught here and propagate
          normally.
        - Every caught exception is logged with its full traceback via
          `logger.exception()` *before* being converted, so the
          original failure remains fully visible in logs rather than
          being silently swallowed.
        - If `execute()` does not raise but returns a value that is
          not an `AgentResult`, that is treated as a genuine
          programming error in the concrete agent's implementation (a
          broken contract, not a runtime failure to recover from) and
          is allowed to raise directly rather than being converted.
    """

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """The `AgentType` this agent identifies its results as."""
        raise NotImplementedError

    @abstractmethod
    def validate_input(self, *args: Any, **kwargs: Any) -> None:
        """Validate that this agent's execution inputs are usable.

        Concrete agents implement this to check whatever inputs they
        actually need (UIR, resource/dependency graphs,
        `ValidationReport`s, runtime telemetry, configuration state,
        etc. — see this module's docstring for why the signature is
        left generic here). Implementations should simply return on
        success; they signal invalid input by raising.

        Raises:
            Exception: Any exception indicating the input is not
                usable. `run()` catches this itself and converts it
                into a `FAILED` `AgentResult`; subclasses do not need
                to catch it themselves.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> AgentResult:
        """Run this agent's own analysis and return its result.

        Called only after `validate_input()` has succeeded. Concrete
        agents implement this to perform their own analysis and return
        a fully-formed `AgentResult`. An implementation should set its
        own result's `status` to whichever outcome it reached itself
        (typically `AgentStatus.COMPLETED` or `AgentStatus.SKIPPED`);
        `run()` sets `AgentStatus.FAILED` on its returned `AgentResult`
        only when `execute()` raises instead of returning one.

        Returns:
            The `AgentResult` produced by this agent's analysis.

        Raises:
            Exception: Any exception indicating execution could not
                complete. `run()` catches this itself and converts it
                into a `FAILED` `AgentResult`; subclasses do not need
                to catch it themselves.
        """
        raise NotImplementedError

    def run(self, *args: Any, **kwargs: Any) -> AgentResult:
        """Run this agent's full lifecycle: validate, execute, and report.

        Args:
            *args: Positional arguments forwarded to both
                `validate_input()` and `execute()`.
            **kwargs: Keyword arguments forwarded to both
                `validate_input()` and `execute()`.

        Returns:
            The `AgentResult` returned by `execute()` on success, or a
            `FAILED` `AgentResult` describing the failure if either
            `validate_input()` or `execute()` raises an `Exception`.

        Raises:
            TypeError: If `execute()` returns a value that is not an
                `AgentResult` (a programming error in the concrete
                agent, not a runtime failure — see this class's
                docstring).
        """
        logger.info("%s: PENDING -> validating input.", self.agent_type.value)

        try:
            self.validate_input(*args, **kwargs)
        except Exception as exc:
            logger.exception("%s: input validation failed.", self.agent_type.value)
            return self._failed_result(f"Input validation failed: {exc}")

        logger.info("%s: RUNNING.", self.agent_type.value)

        try:
            result = self.execute(*args, **kwargs)
        except Exception as exc:
            logger.exception("%s: execution failed.", self.agent_type.value)
            return self._failed_result(f"Agent execution failed: {exc}")

        if not isinstance(result, AgentResult):
            raise TypeError(
                f"{type(self).__name__}.execute() must return an AgentResult, got "
                f"{type(result).__name__}"
            )

        logger.info("%s: %s.", self.agent_type.value, result.status.value)
        return result

    def _failed_result(self, message: str) -> AgentResult:
        """Build the `FAILED` `AgentResult` `run()` returns on exception.

        Args:
            message: A human-readable description of what failed.

        Returns:
            An `AgentResult` with `status=AgentStatus.FAILED`,
            `confidence=0.0`, and no findings/evidence.
        """
        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.FAILED,
            message=message,
            confidence=0.0,
        )


__all__ = ["BaseAgent"]
