"""test_agent_foundation.py.

Tests for the Module 4 foundation: `agent_schema.py`, `agent_result.py`,
and `base_agent.py`.

These tests exercise the foundation's own responsibilities only
(enum vocabularies, `AgentFinding`/`AgentResult` construction and
serialization, and `BaseAgent`'s `PENDING -> RUNNING -> COMPLETED`/
`FAILED` lifecycle) using a tiny dummy agent defined in this file. No
real specialized agent (syntax validation, security validation,
deployment validation, drift detection, cost analysis, evidence
collection) or Coordinator Agent is implemented or tested here — that
is a later task.

Run directly:
    python -m src.ml_model.module4_multi_agent.test_agent_foundation
"""

from __future__ import annotations

import sys

# See agent_result.py / base_agent.py for why this try/except import
# pattern is used: it lets this file run correctly both via
# `python -m src.ml_model.module4_multi_agent.test_agent_foundation`
# (package context, relative imports resolve) and via direct/flat
# execution (no package context, falls back to flat imports).
try:
    from .agent_result import AgentResult, AgentResultError
    from .agent_schema import (
        AgentFinding,
        AgentSchemaError,
        AgentSeverity,
        AgentStatus,
        AgentType,
    )
    from .base_agent import BaseAgent
except ImportError:
    from agent_result import AgentResult, AgentResultError  # type: ignore[no-redef]
    from agent_schema import (  # type: ignore[no-redef]
        AgentFinding,
        AgentSchemaError,
        AgentSeverity,
        AgentStatus,
        AgentType,
    )
    from base_agent import BaseAgent  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Tiny dummy agent used only by these tests.
# ---------------------------------------------------------------------------
class DummyAgent(BaseAgent):
    """A minimal `BaseAgent` implementation for exercising the lifecycle.

    Configurable via its constructor so the same class can exercise
    every lifecycle outcome (success, failed validation, failed
    execution) without needing a separate subclass per scenario.
    """

    def __init__(
        self,
        *,
        fail_validation: bool = False,
        fail_execution: bool = False,
    ) -> None:
        self._fail_validation = fail_validation
        self._fail_execution = fail_execution

    @property
    def agent_type(self) -> AgentType:
        return AgentType.SYNTAX_VALIDATION

    def validate_input(self, *, uir: object = None, **kwargs: object) -> None:
        if self._fail_validation:
            raise ValueError("dummy agent was configured to fail validation")
        if uir is None:
            raise ValueError("uir is required")

    def execute(self, *, uir: object = None, **kwargs: object) -> AgentResult:
        if self._fail_execution:
            raise RuntimeError("dummy agent was configured to fail execution")

        finding_one = AgentFinding(
            agent_type=self.agent_type,
            severity=AgentSeverity.LOW,
            message="dummy finding one",
            evidence_ids=("evidence-001",),
            confidence=0.6,
        )
        finding_two = AgentFinding(
            agent_type=self.agent_type,
            severity=AgentSeverity.MEDIUM,
            message="dummy finding two",
            evidence_ids=("evidence-002", "evidence-003"),
            confidence=0.8,
        )

        return AgentResult(
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            findings=(finding_one, finding_two),
            confidence=0.7,
            evidence_ids=("evidence-001", "evidence-002", "evidence-003"),
            message="dummy agent completed successfully",
        )


# ---------------------------------------------------------------------------
# Minimal assertion helper, matching the style of test_validation_result.py.
# ---------------------------------------------------------------------------
_FAILURES: list[str] = []


def _check(condition: bool, description: str) -> None:
    """Record a single check's outcome without stopping the test run."""
    if condition:
        print(f"  [PASS] {description}")
    else:
        print(f"  [FAIL] {description}")
        _FAILURES.append(description)


# ---------------------------------------------------------------------------
# 1. AgentType values
# ---------------------------------------------------------------------------
def test_agent_type_values() -> None:
    print("test_agent_type_values")
    expected = {
        "COORDINATOR",
        "SYNTAX_VALIDATION",
        "SECURITY_VALIDATION",
        "DEPLOYMENT_VALIDATION",
        "DRIFT_DETECTION",
        "COST_ANALYSIS",
        "EVIDENCE_COLLECTION",
    }
    actual = {member.value for member in AgentType}
    _check(actual == expected, f"AgentType members match expected set {expected}")
    _check(AgentType.SECURITY_VALIDATION.value == "SECURITY_VALIDATION", "AgentType is str-valued")


# ---------------------------------------------------------------------------
# 2. AgentStatus values
# ---------------------------------------------------------------------------
def test_agent_status_values() -> None:
    print("test_agent_status_values")
    expected = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"}
    actual = {member.value for member in AgentStatus}
    _check(actual == expected, f"AgentStatus members match expected set {expected}")


# ---------------------------------------------------------------------------
# 3. AgentSeverity values
# ---------------------------------------------------------------------------
def test_agent_severity_values() -> None:
    print("test_agent_severity_values")
    expected = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "NONE"}
    actual = {member.value for member in AgentSeverity}
    _check(actual == expected, f"AgentSeverity members match expected set {expected}")


# ---------------------------------------------------------------------------
# 4. Valid AgentFinding
# ---------------------------------------------------------------------------
def test_valid_agent_finding() -> AgentFinding:
    print("test_valid_agent_finding")
    finding = AgentFinding(
        agent_type="security_validation",
        severity="high",
        message="Security group allows unrestricted ingress",
        resource_id="aws_security_group.web_sg",
        rule_id="CKV_AWS_24",
        evidence_ids=("evidence-001",),
        confidence=0.92,
    )
    _check(isinstance(finding, AgentFinding), "AgentFinding constructed successfully")
    _check(finding.agent_type is AgentType.SECURITY_VALIDATION, "agent_type coerced from string")
    _check(finding.severity is AgentSeverity.HIGH, "severity coerced from string")
    _check(finding.confidence == 0.92, "confidence stored correctly")
    _check(finding.evidence_ids == ("evidence-001",), "evidence_ids stored as a tuple")
    return finding


# ---------------------------------------------------------------------------
# 5. Invalid confidence
# ---------------------------------------------------------------------------
def test_invalid_confidence() -> None:
    print("test_invalid_confidence")

    for bad_confidence in (-0.01, 1.01, "high", True, None):
        try:
            AgentFinding(
                agent_type=AgentType.COST_ANALYSIS,
                severity=AgentSeverity.INFO,
                message="cost finding",
                confidence=bad_confidence,
            )
            _check(False, f"confidence={bad_confidence!r} is rejected")
        except AgentSchemaError:
            _check(True, f"confidence={bad_confidence!r} is rejected")

    # Boundary values are valid.
    low = AgentFinding(
        agent_type=AgentType.COST_ANALYSIS, severity=AgentSeverity.INFO, message="m", confidence=0.0
    )
    high = AgentFinding(
        agent_type=AgentType.COST_ANALYSIS, severity=AgentSeverity.INFO, message="m", confidence=1.0
    )
    _check(low.confidence == 0.0, "confidence=0.0 is accepted")
    _check(high.confidence == 1.0, "confidence=1.0 is accepted")


# ---------------------------------------------------------------------------
# 6. Invalid required fields
# ---------------------------------------------------------------------------
def test_invalid_required_fields() -> None:
    print("test_invalid_required_fields")

    try:
        AgentFinding(
            agent_type=AgentType.DRIFT_DETECTION,
            severity=AgentSeverity.LOW,
            message="   ",
            confidence=0.5,
        )
        _check(False, "blank message is rejected")
    except AgentSchemaError:
        _check(True, "blank message is rejected")

    try:
        AgentFinding(
            agent_type="not-a-real-agent-type",
            severity=AgentSeverity.LOW,
            message="m",
            confidence=0.5,
        )
        _check(False, "invalid agent_type string is rejected")
    except AgentSchemaError:
        _check(True, "invalid agent_type string is rejected")

    try:
        AgentFinding(
            agent_type=AgentType.DRIFT_DETECTION,
            severity=AgentSeverity.LOW,
            message="m",
            confidence=0.5,
            resource_id="   ",
        )
        _check(False, "blank optional resource_id is rejected")
    except AgentSchemaError:
        _check(True, "blank optional resource_id is rejected")

    try:
        AgentFinding(
            agent_type=AgentType.DRIFT_DETECTION,
            severity=AgentSeverity.LOW,
            message="m",
            confidence=0.5,
            evidence_ids=("ok", ""),
        )
        _check(False, "blank evidence_ids entry is rejected")
    except AgentSchemaError:
        _check(True, "blank evidence_ids entry is rejected")

    try:
        AgentFinding.from_dict({"agent_type": "COST_ANALYSIS", "severity": "LOW"})
        _check(False, "AgentFinding.from_dict rejects missing required fields")
    except AgentSchemaError:
        _check(True, "AgentFinding.from_dict rejects missing required fields")


# ---------------------------------------------------------------------------
# 7. AgentFinding serialization
# ---------------------------------------------------------------------------
def test_agent_finding_serialization(finding: AgentFinding) -> None:
    print("test_agent_finding_serialization")

    as_dict = finding.to_dict()
    _check(as_dict["agent_type"] == "SECURITY_VALIDATION", "to_dict serializes agent_type as a string")
    _check(as_dict["severity"] == "HIGH", "to_dict serializes severity as a string")
    _check(as_dict["evidence_ids"] == ["evidence-001"], "to_dict serializes evidence_ids as a list")

    round_tripped = AgentFinding.from_dict(as_dict)
    _check(round_tripped == finding, "from_dict(to_dict(finding)) round-trips to an equal AgentFinding")


# ---------------------------------------------------------------------------
# 8. AgentResult creation
# ---------------------------------------------------------------------------
def test_agent_result_creation() -> AgentResult:
    print("test_agent_result_creation")

    finding = AgentFinding(
        agent_type=AgentType.SYNTAX_VALIDATION,
        severity=AgentSeverity.MEDIUM,
        message="minor syntax issue",
        confidence=0.5,
    )

    result = AgentResult(
        agent_type=AgentType.SYNTAX_VALIDATION,
        status="completed",
        findings=(finding,),
        confidence=0.5,
        evidence_ids=("evidence-100",),
        message="syntax validation completed",
        metadata={"duration_ms": 12},
    )

    _check(isinstance(result, AgentResult), "AgentResult constructed successfully")
    _check(result.status is AgentStatus.COMPLETED, "status coerced from string")
    _check(len(result.findings) == 1, "findings preserved")
    _check(result.metadata == {"duration_ms": 12}, "metadata preserved")

    # findings must contain only AgentFinding instances.
    try:
        AgentResult(
            agent_type=AgentType.SYNTAX_VALIDATION,
            status=AgentStatus.COMPLETED,
            findings=("not-a-finding",),
            confidence=0.5,
            message="m",
        )
        _check(False, "AgentResult rejects a findings element that is not an AgentFinding")
    except AgentResultError:
        _check(True, "AgentResult rejects a findings element that is not an AgentFinding")

    # confidence/evidence_ids validation is reused, not duplicated.
    try:
        AgentResult(
            agent_type=AgentType.SYNTAX_VALIDATION,
            status=AgentStatus.COMPLETED,
            confidence=2.0,
            message="m",
        )
        _check(False, "AgentResult rejects out-of-range confidence")
    except AgentResultError:
        _check(True, "AgentResult rejects out-of-range confidence")

    return result


# ---------------------------------------------------------------------------
# 9. AgentResult serialization
# ---------------------------------------------------------------------------
def test_agent_result_serialization(result: AgentResult) -> None:
    print("test_agent_result_serialization")

    as_dict = result.to_dict()
    _check(as_dict["status"] == "COMPLETED", "to_dict serializes status as a string")
    _check(len(as_dict["findings"]) == 1, "to_dict serializes findings as a list")
    _check(as_dict["evidence_ids"] == ["evidence-100"], "to_dict serializes evidence_ids as a list")

    round_tripped = AgentResult.from_dict(as_dict)
    _check(round_tripped == result, "from_dict(to_dict(result)) round-trips to an equal AgentResult")

    try:
        AgentResult.from_dict({"status": "COMPLETED"})
        _check(False, "AgentResult.from_dict rejects missing required fields")
    except AgentResultError:
        _check(True, "AgentResult.from_dict rejects missing required fields")


# ---------------------------------------------------------------------------
# 10. BaseAgent lifecycle
# ---------------------------------------------------------------------------
def test_base_agent_lifecycle() -> None:
    print("test_base_agent_lifecycle")

    try:
        BaseAgent()  # type: ignore[abstract]
        _check(False, "BaseAgent cannot be instantiated directly (it is abstract)")
    except TypeError:
        _check(True, "BaseAgent cannot be instantiated directly (it is abstract)")

    agent = DummyAgent()
    _check(agent.agent_type is AgentType.SYNTAX_VALIDATION, "concrete agent_type property works")

    result = agent.run(uir=object())
    _check(isinstance(result, AgentResult), "run() returns an AgentResult")
    _check(result.status in (AgentStatus.COMPLETED, AgentStatus.FAILED), "run() reaches a terminal status")


# ---------------------------------------------------------------------------
# 11. Successful agent execution
# ---------------------------------------------------------------------------
def test_successful_agent_execution() -> None:
    print("test_successful_agent_execution")

    result = DummyAgent().run(uir=object())

    _check(result.status is AgentStatus.COMPLETED, "successful run reaches COMPLETED status")
    _check(result.agent_type is AgentType.SYNTAX_VALIDATION, "result.agent_type matches the agent")
    _check(len(result.findings) == 2, "successful run's findings are preserved")
    _check(result.message == "dummy agent completed successfully", "successful run's message is preserved")


# ---------------------------------------------------------------------------
# 12. Failed agent execution
# ---------------------------------------------------------------------------
def test_failed_agent_execution() -> None:
    print("test_failed_agent_execution")

    result = DummyAgent(fail_execution=True).run(uir=object())

    _check(result.status is AgentStatus.FAILED, "execution failure reaches FAILED status")
    _check(result.confidence == 0.0, "FAILED result from run() has confidence 0.0")
    _check(result.findings == (), "FAILED result from run() has no findings")
    _check(
        "Agent execution failed" in result.message
        and "dummy agent was configured to fail execution" in result.message,
        "FAILED result's message describes the underlying execution failure",
    )


# ---------------------------------------------------------------------------
# 13. Invalid agent input
# ---------------------------------------------------------------------------
def test_invalid_agent_input() -> None:
    print("test_invalid_agent_input")

    # No `uir` supplied at all: DummyAgent.validate_input() raises.
    result_missing_input = DummyAgent().run()
    _check(result_missing_input.status is AgentStatus.FAILED, "missing required input reaches FAILED status")
    _check(
        "Input validation failed" in result_missing_input.message,
        "FAILED result's message describes the input validation failure",
    )

    # Agent explicitly configured to fail its own input validation.
    result_bad_validation = DummyAgent(fail_validation=True).run(uir=object())
    _check(
        result_bad_validation.status is AgentStatus.FAILED,
        "configured validation failure reaches FAILED status",
    )
    _check(
        "dummy agent was configured to fail validation" in result_bad_validation.message,
        "FAILED result's message includes the original validation error",
    )


# ---------------------------------------------------------------------------
# 14. Evidence preservation
# ---------------------------------------------------------------------------
def test_evidence_preservation() -> None:
    print("test_evidence_preservation")

    result = DummyAgent().run(uir=object())

    _check(
        result.evidence_ids == ("evidence-001", "evidence-002", "evidence-003"),
        "result-level evidence_ids are preserved in order",
    )
    _check(
        result.findings[0].evidence_ids == ("evidence-001",),
        "first finding's evidence_ids are preserved",
    )
    _check(
        result.findings[1].evidence_ids == ("evidence-002", "evidence-003"),
        "second finding's evidence_ids are preserved, including order",
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
def run_all_tests() -> int:
    """Run every test function in this module and print a final summary.

    Returns:
        `0` if every check passed, `1` otherwise (suitable as a process
        exit code).
    """
    test_agent_type_values()
    test_agent_status_values()
    test_agent_severity_values()
    finding = test_valid_agent_finding()
    test_invalid_confidence()
    test_invalid_required_fields()
    test_agent_finding_serialization(finding)
    result = test_agent_result_creation()
    test_agent_result_serialization(result)
    test_base_agent_lifecycle()
    test_successful_agent_execution()
    test_failed_agent_execution()
    test_invalid_agent_input()
    test_evidence_preservation()

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED:")
        for description in _FAILURES:
            print(f"  - {description}")
        return 1

    print("All checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
