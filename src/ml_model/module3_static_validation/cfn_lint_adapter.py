"""cfn_lint_adapter.py.

A validation-only adapter around the `cfn-lint --format json <template>`
CLI command.

    CloudFormation template path
            -> cfn-lint --format json <template>
            -> native cfn-lint JSON
            -> CfnLintAdapter
            -> ValidationFinding objects
            -> validation_result.build_report()
            -> ValidationReport

This module mirrors `terraform_validate_adapter.py`'s and
`checkov_adapter.py`'s architecture exactly: it is responsible for
running cfn-lint safely, capturing its stdout/stderr/return code,
parsing its JSON output, translating each diagnostic into a
`ValidationFinding`, and assembling those findings into a
`ValidationReport` via `validation_result.build_report()`. It performs
no field-level validation of its own beyond what is required to safely
extract data from cfn-lint's JSON — all `ValidationFinding` /
`ValidationReport` validation is owned entirely by `validation_schema.py`
and `validation_result.py`.

Native cfn-lint JSON shape (`cfn-lint --format json <template>`):
    cfn-lint emits a bare top-level JSON *array* of diagnostic objects
    (unlike Terraform's `{"diagnostics": [...]}` wrapper, or Checkov's
    `{"results": {"failed_checks": [...], ...}}` buckets). Each
    diagnostic looks roughly like:
        {
            "Rule": {"Id": "E3001", "Description": "...", ...},
            "Level": "Error",
            "Message": "Additional properties are not allowed",
            "Location": {
                "Start": {"LineNumber": 10, "ColumnNumber": 3},
                "End": {"LineNumber": 10, "ColumnNumber": 20},
                "Path": ["Resources", "MyBucket", "Properties"]
            },
            "Filename": "template.yaml"
        }
    cfn-lint versions have varied this shape slightly over time; every
    field below is extracted defensively and tolerates absence.

Malformed-diagnostic policy (consistent with the corrected
`checkov_adapter.py`): a diagnostic entry that is not a dict, or that
has no usable `Message`, is treated as malformed and raises
`CfnLintAdapterError` — cfn-lint reported *something* here, so silently
discarding it would mean a research-grade assurance system quietly
dropping a result it could not interpret. A diagnostic that is a
well-formed dict with a usable message but is missing other optional
fields (`Rule`, `Level`, `Location`, `Filename`) is handled normally —
those are legitimate optional-field omissions, not malformed data.

Zero-diagnostics policy: an empty cfn-lint output array unambiguously
means "cfn-lint found no issues" — unlike Checkov (which reports
`passed_checks` explicitly) or Terraform (whose JSON carries a separate
`valid` boolean), cfn-lint's array only ever lists problems, so an
empty array has exactly one interpretation. Consistent with both
`TerraformValidateAdapter` and `CheckovAdapter` — which each avoid
returning a zero-check (and therefore misleading-looking) report for a
clean run — this adapter produces one synthetic `PASSED` finding
(`rule_id="CFN_LINT_NO_ISSUES"`) when the diagnostics array is empty.

Requirements:
    - Python 3.12
    - The `cfn-lint` CLI, on `PATH` or at an explicitly configured
      path, is required only at call time (not at import time) — this
      module can be imported and unit tested with no cfn-lint
      installation present.

Typical usage:
    from cfn_lint_adapter import CfnLintAdapter

    adapter = CfnLintAdapter()
    report = adapter.validate("path/to/template.yaml")
    report.to_dict()
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Relative imports are used since this module lives inside the
# `module3_static_validation` package alongside `validation_result.py`
# and `validation_schema.py`. A fallback to absolute (flat) imports is
# provided so this module also runs correctly without package context
# (e.g. direct script execution), matching the pattern already used by
# `validation_result.py`, `terraform_validate_adapter.py`, and
# `checkov_adapter.py`.
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
class CfnLintAdapterError(Exception):
    """Raised when cfn-lint cannot be executed, or its output cannot be used.

    This covers adapter-level failures only: the cfn-lint executable
    not being found, the process timing out, its output being unusable
    (empty, invalid JSON, malformed top-level structure), or an
    individual diagnostic being malformed enough that it cannot be
    safely translated into a `ValidationFinding`. An ordinary cfn-lint
    run that finds errors or warnings — a non-zero return code
    accompanied by well-formed JSON diagnostics — is not an adapter
    error; it is represented as `ValidationFinding` objects instead.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TOOL_NAME = "cfn-lint"
_PROVIDER_NAME = "AWS CloudFormation"

_LEVEL_ERROR = "ERROR"
_LEVEL_WARNING = "WARNING"
_LEVEL_INFORMATIONAL = "INFORMATIONAL"
_LEVEL_INFO_ALIAS = "INFO"

_SYNTHETIC_NO_ISSUES_RULE_ID = "CFN_LINT_NO_ISSUES"
_SYNTHETIC_NO_ISSUES_MESSAGE = "cfn-lint reported no issues."

_DEFAULT_CFN_LINT_EXECUTABLE = "cfn-lint"
_DEFAULT_TIMEOUT_SECONDS = 60.0


# ---------------------------------------------------------------------------
# CfnLintAdapter
# ---------------------------------------------------------------------------
class CfnLintAdapter:
    """Runs cfn-lint against a CloudFormation template and builds a `ValidationReport`.

    Attributes:
        cfn_lint_executable: The cfn-lint executable name or path used
            to run the lint.
        timeout_seconds: The maximum time to wait for cfn-lint to
            complete before treating it as a failure.
    """

    def __init__(
        self,
        cfn_lint_executable: str = _DEFAULT_CFN_LINT_EXECUTABLE,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the adapter.

        Args:
            cfn_lint_executable: The cfn-lint executable name (to be
                resolved via `PATH`) or an explicit path. Defaults to
                `"cfn-lint"`.
            timeout_seconds: The maximum number of seconds to wait for
                cfn-lint to complete. Defaults to `60.0`.

        Raises:
            CfnLintAdapterError: If `cfn_lint_executable` is empty, or
                `timeout_seconds` is not positive.
        """
        if not isinstance(cfn_lint_executable, str) or not cfn_lint_executable.strip():
            raise CfnLintAdapterError(
                f"cfn_lint_executable must be a non-empty string, got {cfn_lint_executable!r}"
            )
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise CfnLintAdapterError(f"timeout_seconds must be a positive number, got {timeout_seconds!r}")

        self.cfn_lint_executable = cfn_lint_executable
        self.timeout_seconds = float(timeout_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(self, template_path: Union[str, Path]) -> ValidationReport:
        """Run cfn-lint against `template_path` and build a `ValidationReport`.

        Uses the same public method name as `TerraformValidateAdapter`
        and `CheckovAdapter` (`validate(...)`) so a future orchestrator
        can call every tool adapter polymorphically without knowing
        which specific tool it is invoking.

        Args:
            template_path: Path to the CloudFormation template file to
                lint.

        Returns:
            A `ValidationReport` for provider `"AWS CloudFormation"`.
            If cfn-lint reports zero diagnostics, the report contains
            exactly one synthetic `PASSED` finding rather than being
            empty (see the module docstring's "Zero-diagnostics
            policy").

        Raises:
            CfnLintAdapterError: If the cfn-lint executable cannot be
                found or fails to launch, if the process times out, if
                its output cannot be parsed as usable cfn-lint JSON, or
                if any individual diagnostic cannot be safely
                translated into a finding. A non-zero return code
                accompanied by valid JSON diagnostics is NOT an error
                condition and does not raise.
        """
        template_path_obj = Path(template_path)
        completed_process = self._run_cfn_lint(template_path_obj)

        stdout = completed_process.stdout or ""
        stderr = completed_process.stderr or ""

        if not stdout.strip():
            detail = stderr.strip() or "no output was produced on stdout or stderr"
            logger.error(
                "cfn-lint produced no usable output for %s (return code %d): %s",
                template_path_obj,
                completed_process.returncode,
                detail,
            )
            raise CfnLintAdapterError(
                f"cfn-lint produced no usable JSON output for {template_path_obj} "
                f"(return code {completed_process.returncode}): {detail}"
            )

        data = self._parse_output(stdout)
        diagnostics = self._extract_diagnostics(data)

        findings: List[ValidationFinding] = [
            self._diagnostic_to_finding(diagnostic, index) for index, diagnostic in enumerate(diagnostics)
        ]

        if not findings:
            findings.append(self._build_synthetic_passed_finding())

        logger.info(
            "cfn-lint run against %s produced %d finding(s) (return code=%d).",
            template_path_obj,
            len(findings),
            completed_process.returncode,
        )

        try:
            return build_report(provider=_PROVIDER_NAME, findings=findings)
        except ValidationResultError as exc:
            logger.error("Failed to build validation report for %s: %s", template_path_obj, exc)
            raise CfnLintAdapterError(f"Failed to build validation report for {template_path_obj}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: process execution
    # ------------------------------------------------------------------
    def _run_cfn_lint(self, template_path: Path) -> "subprocess.CompletedProcess[str]":
        """Execute `cfn-lint --format json <template_path>`.

        Args:
            template_path: The CloudFormation template file to lint,
                passed to cfn-lint as a positional argument (cfn-lint,
                like Checkov, takes its target as an explicit CLI
                argument rather than operating on the process's current
                working directory, so `subprocess.run`'s `cwd` argument
                is not used here).

        Returns:
            The completed process, with `stdout`, `stderr`, and
            `returncode` captured as text. This method never inspects
            `returncode` itself — a non-zero exit is a normal, expected
            outcome of cfn-lint reporting errors or warnings.

        Raises:
            CfnLintAdapterError: If the cfn-lint executable cannot be
                found, the process times out, or launching it otherwise
                fails at the OS level.
        """
        command = [self.cfn_lint_executable, "--format", "json", str(template_path)]
        logger.info("Running '%s' (timeout=%ss)", " ".join(command), self.timeout_seconds)

        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            logger.error("cfn-lint executable not found: '%s'", self.cfn_lint_executable)
            raise CfnLintAdapterError(
                f"cfn-lint executable not found: '{self.cfn_lint_executable}'. "
                f"Ensure cfn-lint is installed and on PATH, or configure an explicit path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error(
                "cfn-lint timed out after %s second(s) for %s", self.timeout_seconds, template_path
            )
            raise CfnLintAdapterError(
                f"cfn-lint timed out after {self.timeout_seconds} second(s) for {template_path}"
            ) from exc
        except OSError as exc:
            logger.error("Failed to execute cfn-lint for %s: %s", template_path, exc)
            raise CfnLintAdapterError(f"Failed to execute cfn-lint for {template_path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: output parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_output(stdout: str) -> Any:
        """Parse cfn-lint's JSON output.

        Args:
            stdout: The raw stdout text from cfn-lint.

        Returns:
            The parsed top-level JSON value.

        Raises:
            CfnLintAdapterError: If `stdout` is not valid JSON.
        """
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse cfn-lint JSON output: %s", exc)
            raise CfnLintAdapterError(f"Failed to parse cfn-lint JSON output: {exc}") from exc

    @staticmethod
    def _extract_diagnostics(data: Any) -> List[Any]:
        """Extract the diagnostics list from parsed cfn-lint JSON.

        `cfn-lint --format json` emits a bare top-level array directly
        — there is no wrapper object to unwrap (unlike Terraform's
        `{"diagnostics": [...]}` or Checkov's `{"results": {...}}`).

        Args:
            data: The parsed top-level cfn-lint JSON value.

        Returns:
            `data` itself, unchanged.

        Raises:
            CfnLintAdapterError: If `data` is not a list.
        """
        if not isinstance(data, list):
            logger.error("Expected cfn-lint JSON to be an array, got %s", type(data).__name__)
            raise CfnLintAdapterError(f"Expected cfn-lint JSON to be an array, got {type(data).__name__}")

        return data

    # ------------------------------------------------------------------
    # Internal: diagnostic -> ValidationFinding translation
    # ------------------------------------------------------------------
    def _diagnostic_to_finding(self, diagnostic: Any, index: int) -> ValidationFinding:
        """Translate one cfn-lint diagnostic into a `ValidationFinding`.

        A diagnostic that is not a dict, or that has no usable
        `Message`, is treated as malformed and raises — cfn-lint
        reported something here, so silently discarding it would mean
        quietly dropping a result this adapter could not interpret.
        Missing `Rule`, `Level`, `Location`, or `Filename` are legitimate
        optional-field omissions and are handled normally.

        Args:
            diagnostic: One entry from cfn-lint's top-level JSON array,
                in whatever shape it happens to be.
            index: The diagnostic's position in the array, used only
                for logging.

        Returns:
            A new `ValidationFinding`.

        Raises:
            CfnLintAdapterError: If `diagnostic` is not a dict, has no
                usable `Message`, or is otherwise well-formed enough to
                build a finding from but
                `validation_result.create_finding()` itself rejects it.
        """
        if not isinstance(diagnostic, dict):
            logger.error("Malformed diagnostic at index %d: expected a dict, got %r", index, diagnostic)
            raise CfnLintAdapterError(
                f"Malformed diagnostic at index {index}: expected a dict, got {type(diagnostic).__name__}"
            )

        message = self._clean_optional_string(diagnostic.get("Message"))
        if message is None:
            logger.error("Malformed diagnostic at index %d: no usable 'Message'", index)
            raise CfnLintAdapterError(f"Malformed diagnostic at index {index}: no usable 'Message'")

        rule_id = self._extract_rule_id(diagnostic)
        status, severity = self._map_level(diagnostic.get("Level"), index)
        file_path = self._clean_optional_string(diagnostic.get("Filename"))
        line, column = self._extract_position(diagnostic.get("Location"))

        try:
            return create_finding(
                tool=_TOOL_NAME,
                provider=_PROVIDER_NAME,
                status=status,
                severity=severity,
                message=message,
                rule_id=rule_id,
                resource_id=None,
                file_path=file_path,
                line=line,
                column=column,
            )
        except ValidationResultError as exc:
            logger.error("Failed to build finding for diagnostic at index %d: %s", index, exc)
            raise CfnLintAdapterError(f"Failed to build finding for diagnostic at index {index}: {exc}") from exc

    @staticmethod
    def _extract_rule_id(diagnostic: Dict[str, Any]) -> Optional[str]:
        """Extract the native cfn-lint rule identifier from a diagnostic.

        The standard shape nests it as `diagnostic["Rule"]["Id"]`; a
        couple of flatter shapes are checked defensively in case of
        cfn-lint version differences, but nothing is fabricated if none
        are present.

        Args:
            diagnostic: The diagnostic dictionary.

        Returns:
            The rule identifier, or `None` if none could be found.
        """
        rule = diagnostic.get("Rule")
        if isinstance(rule, dict):
            rule_id = CfnLintAdapter._clean_optional_string(rule.get("Id"))
            if rule_id:
                return rule_id

        return CfnLintAdapter._clean_optional_string(
            diagnostic.get("RuleId")
        ) or CfnLintAdapter._clean_optional_string(diagnostic.get("Id"))

    @staticmethod
    def _map_level(level_raw: Any, index: int) -> Tuple[ValidationStatus, ValidationSeverity]:
        """Map a cfn-lint diagnostic's `Level` to a status/severity pair.

        cfn-lint's three native levels map onto the existing enums
        without inventing new values:
            - `"Error"` -> `(FAILED, HIGH)`
            - `"Warning"` -> `(WARNING, LOW)`
            - `"Informational"` (or the shorthand `"Info"`) ->
              `(WARNING, INFO)` — `ValidationSeverity.INFO` is a direct,
              deliberate name match for cfn-lint's informational level;
              `WARNING` is the closest existing status for "worth
              noting, not a failure," since the schema has no distinct
              "informational" status.

        An unrecognized or missing level falls back to `(ERROR, MEDIUM)`
        — `ERROR` because whether the diagnostic represents a real
        failure could not be determined, not because it necessarily is
        one — mirroring `CheckovAdapter`'s fallback for an unrecognized
        severity.

        Args:
            level_raw: The diagnostic's `Level` value, in whatever
                shape it happens to be.
            index: The diagnostic's position in the array, used only
                for logging.

        Returns:
            A `(ValidationStatus, ValidationSeverity)` tuple.
        """
        if isinstance(level_raw, str):
            normalized = level_raw.strip().upper()
            if normalized == _LEVEL_ERROR:
                return ValidationStatus.FAILED, ValidationSeverity.HIGH
            if normalized == _LEVEL_WARNING:
                return ValidationStatus.WARNING, ValidationSeverity.LOW
            if normalized in (_LEVEL_INFORMATIONAL, _LEVEL_INFO_ALIAS):
                return ValidationStatus.WARNING, ValidationSeverity.INFO

        logger.warning(
            "Diagnostic at index %d has unrecognized Level %r; treating as ERROR/MEDIUM", index, level_raw
        )
        return ValidationStatus.ERROR, ValidationSeverity.MEDIUM

    @staticmethod
    def _extract_position(location: Any) -> Tuple[Optional[int], Optional[int]]:
        """Extract a `(line, column)` pair from a diagnostic's `Location.Start`.

        `ValidationFinding` uses 1-based source positions, so any value
        that is not a positive integer is treated as absent.

        Args:
            location: The diagnostic's `Location` value, in whatever
                shape it happens to be.

        Returns:
            A `(line, column)` tuple, either element of which may be
            `None` if `location` is not a dict, has no usable `Start`
            object, or the corresponding value is not a positive
            integer.
        """
        if not isinstance(location, dict):
            return None, None

        start = location.get("Start")
        if not isinstance(start, dict):
            return None, None

        return (
            CfnLintAdapter._extract_positive_int(start.get("LineNumber")),
            CfnLintAdapter._extract_positive_int(start.get("ColumnNumber")),
        )

    @staticmethod
    def _extract_positive_int(value: Any) -> Optional[int]:
        """Normalize a value into a positive integer, or `None`.

        Args:
            value: The raw value, in whatever shape it happens to be.

        Returns:
            `value` itself if it is a positive `int`, otherwise `None`.
            `bool` is explicitly rejected even though it is technically
            an `int` subclass in Python, since a boolean is not a
            meaningful line/column number.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None
        return value

    @staticmethod
    def _clean_optional_string(value: Any) -> Optional[str]:
        """Normalize an optional string field: strip it, or treat it as absent.

        Args:
            value: The raw field value, in whatever shape it happens to
                be.

        Returns:
            The stripped string, or `None` if `value` is not a string
            or is empty/whitespace-only.
        """
        return value.strip() if isinstance(value, str) and value.strip() else None

    # ------------------------------------------------------------------
    # Internal: synthetic finding
    # ------------------------------------------------------------------
    @staticmethod
    def _build_synthetic_passed_finding() -> ValidationFinding:
        """Build the synthetic `PASSED` finding used when cfn-lint finds no issues.

        Used when cfn-lint's diagnostics array is empty, so a clean
        lint run never produces an empty (zero-check) report —
        mirroring `TerraformValidateAdapter` and `CheckovAdapter`'s
        synthetic findings for the same reason. See the module
        docstring's "Zero-diagnostics policy" for why an empty array is
        an unambiguous "no issues" signal for cfn-lint specifically.

        Returns:
            A `ValidationFinding` with `status=PASSED`,
            `severity=NONE`, and `rule_id="CFN_LINT_NO_ISSUES"`.
        """
        return create_finding(
            tool=_TOOL_NAME,
            provider=_PROVIDER_NAME,
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.NONE,
            message=_SYNTHETIC_NO_ISSUES_MESSAGE,
            rule_id=_SYNTHETIC_NO_ISSUES_RULE_ID,
        )


__all__ = [
    "CfnLintAdapter",
    "CfnLintAdapterError",
]
