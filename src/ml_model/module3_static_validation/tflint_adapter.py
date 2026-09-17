"""
TFLint validation adapter.

This module provides a validation-only adapter around the TFLint CLI.
It executes TFLint, parses its JSON output, and converts diagnostics
into the project's common ValidationReport representation.

No remediation, LLM, graph, or orchestration logic belongs here.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

try:
    from .validation_result import (
        ValidationResultError,
        build_report,
        create_finding,
    )
    from .validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )
except ImportError:
    from validation_result import (
        ValidationResultError,
        build_report,
        create_finding,
    )
    from validation_schema import (
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )


logger = logging.getLogger(__name__)


class TFLintAdapterError(Exception):
    """Raised when TFLint execution or output processing fails."""


class TFLintAdapter:
    """
    Validation-only adapter for TFLint.

    TFLint is executed with JSON output and its diagnostics are converted
    into the project's common ValidationFinding/ValidationReport model.
    """

    TOOL_NAME = "tflint"
    PROVIDER_NAME = "Terraform"

    DEFAULT_EXECUTABLE = "tflint"
    DEFAULT_TIMEOUT_SECONDS = 120.0

    NO_ISSUES_RULE_ID = "TFLINT_NO_ISSUES"
    NO_ISSUES_MESSAGE = "TFLint reported no issues."

    def __init__(
        self,
        tflint_executable: str = DEFAULT_EXECUTABLE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(tflint_executable, str) or not tflint_executable.strip():
            raise ValueError("tflint_executable must be a non-empty string.")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self.tflint_executable = tflint_executable
        self.timeout_seconds = float(timeout_seconds)

    def validate(
        self,
        terraform_path: Union[str, Path],
    ) -> ValidationReport:
        """
        Run TFLint and return a normalized ValidationReport.
        """

        stdout, stderr, return_code = self._run_tflint(terraform_path)

        if not stdout.strip():
            message = "TFLint produced empty stdout."
            if stderr.strip():
                message += f" stderr: {stderr.strip()}"
            raise TFLintAdapterError(message)

        payload = self._parse_output(stdout)

        diagnostics = self._extract_diagnostics(payload)

        findings: List[ValidationFinding] = []

        if not diagnostics:
            findings.append(self._create_no_issues_finding())
        else:
            for diagnostic in diagnostics:
                findings.append(
                    self._diagnostic_to_finding(diagnostic)
                )

        try:
            return build_report(
                provider=self.PROVIDER_NAME,
                findings=findings,
            )
        except ValidationResultError as exc:
            raise TFLintAdapterError(
                f"Failed to build TFLint validation report: {exc}"
            ) from exc

    def _run_tflint(
        self,
        terraform_path: Union[str, Path],
    ) -> tuple[str, str, int]:
        """Execute TFLint safely and return stdout, stderr, and exit code."""

        path = Path(terraform_path)

        command: Sequence[str] = [
            self.tflint_executable,
            "--format",
            "json",
            str(path),
        ]

        logger.debug("Running TFLint command: %s", command)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TFLintAdapterError(
                f"TFLint executable not found: {self.tflint_executable}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TFLintAdapterError(
                f"TFLint execution timed out after "
                f"{self.timeout_seconds} seconds."
            ) from exc
        except OSError as exc:
            raise TFLintAdapterError(
                f"Failed to execute TFLint: {exc}"
            ) from exc

        return (
            completed.stdout or "",
            completed.stderr or "",
            completed.returncode,
        )

    @staticmethod
    def _parse_output(stdout: str) -> Any:
        """Parse TFLint JSON output."""

        try:
            return json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise TFLintAdapterError(
                f"Invalid TFLint JSON output: {exc}"
            ) from exc

    @staticmethod
    def _extract_diagnostics(payload: Any) -> List[Dict[str, Any]]:
        """
        Extract the diagnostic list from TFLint output.

        TFLint JSON output is expected to be a top-level list.
        """

        if not isinstance(payload, list):
            raise TFLintAdapterError(
                "TFLint JSON output must be a top-level list."
            )

        diagnostics: List[Dict[str, Any]] = []

        for index, diagnostic in enumerate(payload):
            if not isinstance(diagnostic, dict):
                raise TFLintAdapterError(
                    f"TFLint diagnostic at index {index} must be an object."
                )

            diagnostics.append(diagnostic)

        return diagnostics

    def _diagnostic_to_finding(
        self,
        diagnostic: Dict[str, Any],
    ) -> ValidationFinding:
        """Convert one TFLint diagnostic into a ValidationFinding."""

        message = diagnostic.get("message")

        if not isinstance(message, str) or not message.strip():
            raise TFLintAdapterError(
                "TFLint diagnostic is missing a usable message."
            )

        rule_name = diagnostic.get("rule_name")
        rule_id = (
            rule_name.strip()
            if isinstance(rule_name, str) and rule_name.strip()
            else None
        )

        severity_value = diagnostic.get("severity")
        status, severity = self._map_severity(severity_value)

        file_path, line, column = self._extract_location(diagnostic)

        try:
            return create_finding(
                tool=self.TOOL_NAME,
                provider=self.PROVIDER_NAME,
                status=status,
                severity=severity,
                rule_id=rule_id,
                message=message.strip(),
                resource_id=None,
                file_path=file_path,
                line=line,
                column=column,
            )
        except ValidationResultError as exc:
            raise TFLintAdapterError(
                f"Failed to create TFLint validation finding: {exc}"
            ) from exc

    @staticmethod
    def _map_severity(
        severity_value: Any,
    ) -> tuple[ValidationStatus, ValidationSeverity]:
        """Map TFLint severity to the common validation model."""

        if not isinstance(severity_value, str):
            return (
                ValidationStatus.ERROR,
                ValidationSeverity.MEDIUM,
            )

        normalized = severity_value.strip().lower()

        if normalized == "error":
            return (
                ValidationStatus.FAILED,
                ValidationSeverity.HIGH,
            )

        if normalized == "warning":
            return (
                ValidationStatus.WARNING,
                ValidationSeverity.LOW,
            )

        if normalized in {"notice", "info", "informational"}:
            return (
                ValidationStatus.WARNING,
                ValidationSeverity.INFO,
            )

        return (
            ValidationStatus.ERROR,
            ValidationSeverity.MEDIUM,
        )

    @staticmethod
    def _extract_location(
        diagnostic: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[int], Optional[int]]:
        """Extract filename, line, and column from a TFLint diagnostic."""

        range_data = diagnostic.get("range")

        if range_data is None:
            return None, None, None

        if not isinstance(range_data, dict):
            raise TFLintAdapterError(
                "TFLint diagnostic 'range' must be an object."
            )

        filename = range_data.get("filename")

        if filename is not None and not isinstance(filename, str):
            raise TFLintAdapterError(
                "TFLint diagnostic 'range.filename' must be a string."
            )

        start = range_data.get("start")

        if start is None:
            return filename, None, None

        if not isinstance(start, dict):
            raise TFLintAdapterError(
                "TFLint diagnostic 'range.start' must be an object."
            )

        line = TFLintAdapter._positive_integer_or_none(
            start.get("line")
        )
        column = TFLintAdapter._positive_integer_or_none(
            start.get("column")
        )

        return filename, line, column

    @staticmethod
    def _positive_integer_or_none(value: Any) -> Optional[int]:
        """Return a positive integer or None."""

        if value is None:
            return None

        if isinstance(value, bool):
            return None

        if isinstance(value, int) and value > 0:
            return value

        return None

    def _create_no_issues_finding(self) -> ValidationFinding:
        """Create the synthetic finding used when TFLint reports no issues."""

        try:
            return create_finding(
                tool=self.TOOL_NAME,
                provider=self.PROVIDER_NAME,
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.NONE,
                rule_id=self.NO_ISSUES_RULE_ID,
                message=self.NO_ISSUES_MESSAGE,
            )
        except ValidationResultError as exc:
            raise TFLintAdapterError(
                f"Failed to create TFLint no-issues finding: {exc}"
            ) from exc


__all__ = [
    "TFLintAdapter",
    "TFLintAdapterError",
]