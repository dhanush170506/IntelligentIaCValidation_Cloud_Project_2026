"""terraform_validate_adapter.py.

A validation-only adapter around the `terraform validate -json` CLI
command.

    Terraform working directory
            -> terraform validate -json
            -> native Terraform JSON
            -> TerraformValidateAdapter
            -> ValidationFinding objects
            -> validation_result.build_report()
            -> ValidationReport

This module is responsible for exactly five things: running `terraform
validate -json` safely (never `apply`/`plan`/`destroy`), capturing its
stdout/stderr/return code, parsing its JSON output, translating each
diagnostic into a `ValidationFinding`, and assembling those findings
into a `ValidationReport` via `validation_result.build_report()`. It
performs no field-level validation of its own beyond what is required
to safely extract data from Terraform's JSON — all `ValidationFinding`
/ `ValidationReport` validation is owned entirely by
`validation_schema.py` and `validation_result.py`.

Requirements:
    - Python 3.12
    - The `terraform` CLI, on `PATH` or at an explicitly configured
      path, is required only at call time (not at import time) — this
      module can be imported and unit tested with no Terraform
      installation present.

Typical usage:
    from terraform_validate_adapter import TerraformValidateAdapter

    adapter = TerraformValidateAdapter()
    report = adapter.validate("path/to/terraform/project")
    report.to_dict()
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Relative imports are used since this module lives inside the
# `module3_static_validation` package alongside `validation_result.py`
# and `validation_schema.py`. A fallback to absolute (flat) imports is
# provided so this module also runs correctly without package context
# (e.g. direct script execution), matching the pattern already used by
# `validation_result.py`.
try:
    from .validation_result import ValidationResultError, build_report, create_finding
    from .validation_schema import ValidationFinding, ValidationReport, ValidationSeverity, ValidationStatus
except ImportError:
    from validation_result import (  # type: ignore[no-redef]
        ValidationResultError,
        build_report,
        create_finding,
    )
    from validation_schema import (  # type: ignore[no-redef]
        ValidationFinding,
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )

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
# Custom exceptions
# ---------------------------------------------------------------------------
class TerraformValidateAdapterError(Exception):
    """Raised when Terraform cannot be executed, or its output cannot be used.

    This covers adapter-level failures only: the Terraform executable
    not being found, the process timing out, or its output being
    unusable (empty, invalid JSON, malformed top-level structure). An
    ordinary Terraform validation failure — a non-zero return code
    accompanied by well-formed JSON diagnostics — is not an adapter
    error; it is represented as `ValidationFinding` objects instead.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TOOL_NAME = "terraform_validate"
_PROVIDER_NAME = "Terraform"

_TERRAFORM_SEVERITY_ERROR = "error"
_TERRAFORM_SEVERITY_WARNING = "warning"

_SYNTHETIC_PASSED_RULE_ID = "TERRAFORM_VALIDATE"
_SYNTHETIC_PASSED_MESSAGE = "Terraform configuration is valid."

_DEFAULT_TERRAFORM_EXECUTABLE = "terraform"
_DEFAULT_TIMEOUT_SECONDS = 60.0


# ---------------------------------------------------------------------------
# TerraformValidateAdapter
# ---------------------------------------------------------------------------
class TerraformValidateAdapter:
    """Runs `terraform validate -json` and translates its output into a `ValidationReport`.

    Attributes:
        terraform_executable: The Terraform executable name or path
            used to run validation.
        timeout_seconds: The maximum time to wait for `terraform
            validate` to complete before treating it as a failure.
    """

    def __init__(
        self,
        terraform_executable: str = _DEFAULT_TERRAFORM_EXECUTABLE,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the adapter.

        Args:
            terraform_executable: The Terraform executable name (to be
                resolved via `PATH`) or an explicit path. Defaults to
                `"terraform"`.
            timeout_seconds: The maximum number of seconds to wait for
                `terraform validate` to complete. Defaults to `60.0`.

        Raises:
            TerraformValidateAdapterError: If `terraform_executable` is
                empty, or `timeout_seconds` is not positive.
        """
        if not isinstance(terraform_executable, str) or not terraform_executable.strip():
            raise TerraformValidateAdapterError(
                f"terraform_executable must be a non-empty string, got {terraform_executable!r}"
            )
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise TerraformValidateAdapterError(
                f"timeout_seconds must be a positive number, got {timeout_seconds!r}"
            )

        self.terraform_executable = terraform_executable
        self.timeout_seconds = float(timeout_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(self, workdir: Union[str, Path]) -> ValidationReport:
        """Run `terraform validate -json` in `workdir` and build a `ValidationReport`.

        Args:
            workdir: The Terraform working directory to validate. Must
                already contain initialized/parseable Terraform
                configuration; this method does not run `terraform
                init`.

        Returns:
            A `ValidationReport` for provider `"Terraform"`. If
            Terraform reports the configuration as valid and produced
            no usable diagnostics, the report contains exactly one
            synthetic `PASSED` finding rather than being empty.

        Raises:
            TerraformValidateAdapterError: If the Terraform executable
                cannot be found or fails to launch, if the process
                times out, or if its output cannot be parsed as usable
                Terraform validate JSON. A non-zero return code
                accompanied by valid JSON diagnostics is NOT an error
                condition and does not raise.
        """
        workdir_path = Path(workdir)
        # Preserve the caller's path spelling for subprocess `cwd`.  This is
        # relevant to injected runners and avoids platform-specific rewriting
        # of an otherwise valid caller-provided path representation.
        completed_process = self._run_terraform_validate(workdir)

        stdout = completed_process.stdout or ""
        stderr = completed_process.stderr or ""

        if not stdout.strip():
            detail = stderr.strip() or "no output was produced on stdout or stderr"
            logger.error(
                "Terraform validate produced no usable output in %s (return code %d): %s",
                workdir_path,
                completed_process.returncode,
                detail,
            )
            raise TerraformValidateAdapterError(
                f"Terraform validate produced no usable JSON output in {workdir_path} "
                f"(return code {completed_process.returncode}): {detail}"
            )

        data = self._parse_output(stdout)
        diagnostics = self._extract_diagnostics(data)

        findings: List[ValidationFinding] = []
        for index, diagnostic in enumerate(diagnostics):
            finding = self._diagnostic_to_finding(diagnostic, index)
            if finding is not None:
                findings.append(finding)

        is_valid = bool(data.get("valid", False))
        if is_valid and not findings:
            findings.append(self._build_synthetic_passed_finding())

        logger.info(
            "Terraform validate in %s produced %d finding(s) (valid=%s, return code=%d).",
            workdir_path,
            len(findings),
            is_valid,
            completed_process.returncode,
        )

        try:
            return build_report(provider=_PROVIDER_NAME, findings=findings)
        except ValidationResultError as exc:
            logger.error("Failed to build validation report for %s: %s", workdir_path, exc)
            raise TerraformValidateAdapterError(
                f"Failed to build validation report for {workdir_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal: process execution
    # ------------------------------------------------------------------
    def _run_terraform_validate(self, workdir: Union[str, Path]) -> "subprocess.CompletedProcess[str]":
        """Execute `terraform validate -json` in `workdir`.

        Args:
            workdir: The directory to run the command in.

        Returns:
            The completed process, with `stdout`, `stderr`, and
            `returncode` captured as text. This method never inspects
            `returncode` itself — a non-zero exit is a normal, expected
            outcome of Terraform reporting validation failures.

        Raises:
            TerraformValidateAdapterError: If the Terraform executable
                cannot be found, the process times out, or launching it
                otherwise fails at the OS level.
        """
        command = [self.terraform_executable, "validate", "-json"]
        logger.info("Running '%s' in %s (timeout=%ss)", " ".join(command), workdir, self.timeout_seconds)

        try:
            return subprocess.run(
                command,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            logger.error("Terraform executable not found: '%s'", self.terraform_executable)
            raise TerraformValidateAdapterError(
                f"Terraform executable not found: '{self.terraform_executable}'. "
                f"Ensure Terraform is installed and on PATH, or configure an explicit path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("Terraform validate timed out after %s second(s) in %s", self.timeout_seconds, workdir)
            raise TerraformValidateAdapterError(
                f"Terraform validate timed out after {self.timeout_seconds} second(s) in {workdir}"
            ) from exc
        except OSError as exc:
            logger.error("Failed to execute Terraform in %s: %s", workdir, exc)
            raise TerraformValidateAdapterError(f"Failed to execute Terraform in {workdir}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: output parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_output(stdout: str) -> Dict[str, Any]:
        """Parse Terraform's JSON output into a dictionary.

        Args:
            stdout: The raw stdout text from `terraform validate -json`.

        Returns:
            The parsed top-level JSON object.

        Raises:
            TerraformValidateAdapterError: If `stdout` is not valid
                JSON, or its top-level value is not a JSON object.
        """
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Terraform validate JSON output: %s", exc)
            raise TerraformValidateAdapterError(f"Failed to parse Terraform validate JSON output: {exc}") from exc

        if not isinstance(data, dict):
            logger.error("Expected Terraform validate JSON to be an object, got %s", type(data).__name__)
            raise TerraformValidateAdapterError(
                f"Expected Terraform validate JSON to be an object, got {type(data).__name__}"
            )

        return data

    @staticmethod
    def _extract_diagnostics(data: Dict[str, Any]) -> List[Any]:
        """Extract the `diagnostics` list from parsed Terraform validate JSON.

        Args:
            data: The parsed top-level Terraform validate JSON object.

        Returns:
            The value of `data["diagnostics"]`, or an empty list if the
            key is absent or `None`.

        Raises:
            TerraformValidateAdapterError: If `diagnostics` is present
                and neither `None` nor a list.
        """
        diagnostics = data.get("diagnostics")
        if diagnostics is None:
            return []

        if not isinstance(diagnostics, list):
            logger.error("Expected 'diagnostics' to be a list, got %s", type(diagnostics).__name__)
            raise TerraformValidateAdapterError(
                f"Expected 'diagnostics' to be a list, got {type(diagnostics).__name__}"
            )

        return diagnostics

    # ------------------------------------------------------------------
    # Internal: diagnostic -> ValidationFinding translation
    # ------------------------------------------------------------------
    def _diagnostic_to_finding(self, diagnostic: Any, index: int) -> Optional[ValidationFinding]:
        """Translate one Terraform diagnostic into a `ValidationFinding`.

        A diagnostic that is not a dict, or that has neither a usable
        `summary` nor `detail`, is skipped (logged as a warning) rather
        than raising — one malformed diagnostic should not discard an
        otherwise usable validation run.

        Args:
            diagnostic: One entry from Terraform's `diagnostics` list,
                in whatever shape it happens to be.
            index: The diagnostic's position in the list, used only for
                logging.

        Returns:
            A new `ValidationFinding`, or `None` if this diagnostic
            could not be meaningfully translated.

        Raises:
            TerraformValidateAdapterError: If the diagnostic's data is
                well-formed enough to build a finding from, but
                `validation_result.create_finding()` itself rejects it
                (e.g. an internal inconsistency this adapter did not
                anticipate).
        """
        if not isinstance(diagnostic, dict):
            logger.warning("Skipping malformed diagnostic at index %d: %r", index, diagnostic)
            return None

        message = self._build_message(diagnostic, index)
        if message is None:
            return None

        status, severity = self._map_severity(diagnostic.get("severity"), index)

        range_data = diagnostic.get("range")
        file_path = self._extract_file_path(range_data)
        line = self._extract_position(range_data, "line")
        column = self._extract_position(range_data, "column")

        try:
            return create_finding(
                tool=_TOOL_NAME,
                provider=_PROVIDER_NAME,
                status=status,
                severity=severity,
                message=message,
                rule_id=None,
                resource_id=None,
                file_path=file_path,
                line=line,
                column=column,
            )
        except ValidationResultError as exc:
            logger.error("Failed to build finding for diagnostic at index %d: %s", index, exc)
            raise TerraformValidateAdapterError(
                f"Failed to build finding for diagnostic at index {index}: {exc}"
            ) from exc

    @staticmethod
    def _build_message(diagnostic: Dict[str, Any], index: int) -> Optional[str]:
        """Build a finding message from a diagnostic's `summary`/`detail`.

        Combines both when present as `"{summary}: {detail}"`, falls
        back to whichever one is present, and never produces an empty
        message.

        Args:
            diagnostic: The diagnostic dictionary.
            index: The diagnostic's position in the list, used only for
                logging.

        Returns:
            The combined message, or `None` if neither `summary` nor
            `detail` is a usable non-empty string.
        """
        summary_raw = diagnostic.get("summary")
        detail_raw = diagnostic.get("detail")

        summary = summary_raw.strip() if isinstance(summary_raw, str) and summary_raw.strip() else None
        detail = detail_raw.strip() if isinstance(detail_raw, str) and detail_raw.strip() else None

        if summary and detail:
            return f"{summary}: {detail}"
        if summary:
            return summary
        if detail:
            return detail

        logger.warning("Skipping diagnostic at index %d with no usable summary or detail", index)
        return None

    @staticmethod
    def _map_severity(severity_raw: Any, index: int) -> tuple[ValidationStatus, ValidationSeverity]:
        """Map a Terraform diagnostic severity string to a status/severity pair.

        Args:
            severity_raw: The diagnostic's `severity` value, in
                whatever shape it happens to be.
            index: The diagnostic's position in the list, used only for
                logging.

        Returns:
            A `(ValidationStatus, ValidationSeverity)` tuple. Unknown or
            missing severities map to `(ERROR, MEDIUM)` — `ERROR`
            because whether the check truly passed or failed could not
            be determined, not because the check itself failed.
        """
        if severity_raw == _TERRAFORM_SEVERITY_ERROR:
            return ValidationStatus.FAILED, ValidationSeverity.HIGH
        if severity_raw == _TERRAFORM_SEVERITY_WARNING:
            return ValidationStatus.WARNING, ValidationSeverity.LOW

        logger.warning(
            "Diagnostic at index %d has unrecognized severity %r; treating as ERROR/MEDIUM",
            index,
            severity_raw,
        )
        return ValidationStatus.ERROR, ValidationSeverity.MEDIUM

    @staticmethod
    def _extract_file_path(range_data: Any) -> Optional[str]:
        """Extract a usable file path from a diagnostic's `range`, if present.

        Args:
            range_data: The diagnostic's `range` value, in whatever
                shape it happens to be.

        Returns:
            The range's `filename`, or `None` if `range_data` is not a
            dict or `filename` is not a non-empty string.
        """
        if not isinstance(range_data, dict):
            return None

        filename = range_data.get("filename")
        return filename if isinstance(filename, str) and filename.strip() else None

    @staticmethod
    def _extract_position(range_data: Any, key: str) -> Optional[int]:
        """Extract a positive integer position from a diagnostic's `range.start`.

        `ValidationFinding` uses 1-based source positions, so any value
        that is not a positive integer is treated as absent rather than
        passed through.

        Args:
            range_data: The diagnostic's `range` value, in whatever
                shape it happens to be.
            key: Either `"line"` or `"column"`.

        Returns:
            The corresponding positive integer, or `None` if
            `range_data` is not a dict, has no usable `start` object, or
            the value at `key` is not a positive integer.
        """
        if not isinstance(range_data, dict):
            return None

        start = range_data.get("start")
        if not isinstance(start, dict):
            return None

        value = start.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None

        return value

    @staticmethod
    def _build_synthetic_passed_finding() -> ValidationFinding:
        """Build the synthetic `PASSED` finding used for a clean validation run.

        Used when Terraform reports `valid: true` with no usable
        diagnostics, so a successful validation run never produces an
        empty (zero-check) report.

        Returns:
            A `ValidationFinding` with `status=PASSED`,
            `severity=NONE`, and `rule_id="TERRAFORM_VALIDATE"`.
        """
        return create_finding(
            tool=_TOOL_NAME,
            provider=_PROVIDER_NAME,
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.NONE,
            message=_SYNTHETIC_PASSED_MESSAGE,
            rule_id=_SYNTHETIC_PASSED_RULE_ID,
        )


__all__ = [
    "TerraformValidateAdapter",
    "TerraformValidateAdapterError",
]
