"""checkov_adapter.py.

A validation-only adapter around the `checkov -d <dir> -o json` CLI
command.

    Terraform working directory
            -> checkov -d <dir> --framework terraform -o json
            -> native Checkov JSON
            -> CheckovAdapter
            -> ValidationFinding objects
            -> validation_result.build_report()
            -> ValidationReport

This module mirrors `terraform_validate_adapter.py`'s architecture
exactly: it is responsible for running Checkov safely, capturing its
stdout/stderr/return code, parsing its JSON output, translating each
check result into a `ValidationFinding`, and assembling those findings
into a `ValidationReport` via `validation_result.build_report()`. It
performs no field-level validation of its own beyond what is required
to safely extract data from Checkov's JSON — all `ValidationFinding` /
`ValidationReport` validation is owned entirely by `validation_schema.py`
and `validation_result.py`.

Native Checkov JSON shape (single-framework run):
    {
        "check_type": "terraform",
        "results": {
            "passed_checks": [...],
            "failed_checks": [...],
            "skipped_checks": [...],
            "parsing_errors": [...]
        },
        "summary": {"passed": ..., "failed": ..., "skipped": ..., ...}
    }

Checkov may also emit a JSON *array* of such objects (one per detected
framework) when a directory contains more than one IaC type. This
adapter tolerates both shapes — see `_extract_results()`.

Each check entry may contain:
    - check_id (e.g. "CKV_AWS_24")
    - check_name
    - severity (not always present in open-source Checkov runs)
    - resource (a Terraform resource address, e.g.
      "aws_security_group.web_sg")
    - file_path
    - file_line_range (a `[start_line, end_line]` pair; Checkov does
      not report column information)

Unlike `terraform_validate_adapter.py` (which never sets `rule_id`,
since raw `terraform validate` diagnostics carry no native check ID),
Checkov's `check_id` *is* a meaningful native rule identifier, so it is
used directly as `ValidationFinding.rule_id`. Likewise, Checkov's
`resource` field is an explicit, tool-provided resource address, so it
is used directly as `resource_id` — never inferred from source text.

Requirements:
    - Python 3.12
    - The `checkov` CLI, on `PATH` or at an explicitly configured path,
      is required only at call time (not at import time) — this module
      can be imported and unit tested with no Checkov installation
      present.

Typical usage:
    from checkov_adapter import CheckovAdapter

    adapter = CheckovAdapter()
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
# `validation_result.py` and `terraform_validate_adapter.py`.
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
class CheckovAdapterError(Exception):
    """Raised when Checkov cannot be executed, or its output cannot be used.

    This covers adapter-level failures only: the Checkov executable not
    being found, the process timing out, or its output being unusable
    (empty, invalid JSON, malformed top-level structure). An ordinary
    Checkov scan that finds failed checks — a non-zero return code
    accompanied by well-formed JSON results — is not an adapter error;
    it is represented as `ValidationFinding` objects instead.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TOOL_NAME = "checkov"
_PROVIDER_NAME = "Terraform"
_FRAMEWORK = "terraform"

_BUCKET_PASSED = "passed_checks"
_BUCKET_FAILED = "failed_checks"
_BUCKET_SKIPPED = "skipped_checks"
_BUCKET_PARSING_ERRORS = "parsing_errors"

_STATUS_BY_BUCKET = {
    _BUCKET_PASSED: ValidationStatus.PASSED,
    _BUCKET_FAILED: ValidationStatus.FAILED,
    _BUCKET_SKIPPED: ValidationStatus.SKIPPED,
}

_SYNTHETIC_NO_CHECKS_RULE_ID = "CHECKOV_NO_CHECKS"
_SYNTHETIC_NO_CHECKS_MESSAGE = "Checkov found no applicable checks."

_DEFAULT_CHECKOV_EXECUTABLE = "checkov"
_DEFAULT_TIMEOUT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# CheckovAdapter
# ---------------------------------------------------------------------------
class CheckovAdapter:
    """Runs Checkov against a Terraform directory and builds a `ValidationReport`.

    Attributes:
        checkov_executable: The Checkov executable name or path used to
            run the scan.
        timeout_seconds: The maximum time to wait for Checkov to
            complete before treating it as a failure.
    """

    def __init__(
        self,
        checkov_executable: str = _DEFAULT_CHECKOV_EXECUTABLE,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the adapter.

        Args:
            checkov_executable: The Checkov executable name (to be
                resolved via `PATH`) or an explicit path. Defaults to
                `"checkov"`.
            timeout_seconds: The maximum number of seconds to wait for
                Checkov to complete. Defaults to `120.0` (Checkov scans
                are typically slower than `terraform validate`).

        Raises:
            CheckovAdapterError: If `checkov_executable` is empty, or
                `timeout_seconds` is not positive.
        """
        if not isinstance(checkov_executable, str) or not checkov_executable.strip():
            raise CheckovAdapterError(
                f"checkov_executable must be a non-empty string, got {checkov_executable!r}"
            )
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise CheckovAdapterError(f"timeout_seconds must be a positive number, got {timeout_seconds!r}")

        self.checkov_executable = checkov_executable
        self.timeout_seconds = float(timeout_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(self, workdir: Union[str, Path]) -> ValidationReport:
        """Run Checkov against `workdir` and build a `ValidationReport`.

        Uses the same public method name as `TerraformValidateAdapter`
        (`validate(workdir)`) so a future orchestrator can call every
        tool adapter polymorphically without knowing which specific
        tool it is invoking.

        Args:
            workdir: The Terraform directory to scan.

        Returns:
            A `ValidationReport` for provider `"Terraform"`. If Checkov
            reports zero passed, failed, and skipped checks and zero
            parsing errors, the report contains exactly one synthetic
            `PASSED` finding rather than being empty.

        Raises:
            CheckovAdapterError: If the Checkov executable cannot be
                found or fails to launch, if the process times out, or
                if its output cannot be parsed as usable Checkov JSON.
                A non-zero return code accompanied by valid JSON
                results is NOT an error condition and does not raise.
        """
        workdir_path = Path(workdir)
        completed_process = self._run_checkov(workdir_path)

        stdout = completed_process.stdout or ""
        stderr = completed_process.stderr or ""

        if not stdout.strip():
            detail = stderr.strip() or "no output was produced on stdout or stderr"
            logger.error(
                "Checkov produced no usable output for %s (return code %d): %s",
                workdir_path,
                completed_process.returncode,
                detail,
            )
            raise CheckovAdapterError(
                f"Checkov produced no usable JSON output for {workdir_path} "
                f"(return code {completed_process.returncode}): {detail}"
            )

        data = self._parse_output(stdout)
        results = self._extract_results(data)

        findings: List[ValidationFinding] = []
        for bucket_name, status in _STATUS_BY_BUCKET.items():
            for index, check in enumerate(self._extract_bucket(results, bucket_name)):
                findings.append(self._check_to_finding(check, status, index, bucket_name))

        for index, parsing_error in enumerate(self._extract_bucket(results, _BUCKET_PARSING_ERRORS)):
            findings.append(self._parsing_error_to_finding(parsing_error, index))

        if not findings:
            findings.append(self._build_synthetic_no_checks_finding())

        logger.info(
            "Checkov scan of %s produced %d finding(s) (return code=%d).",
            workdir_path,
            len(findings),
            completed_process.returncode,
        )

        try:
            return build_report(provider=_PROVIDER_NAME, findings=findings)
        except ValidationResultError as exc:
            logger.error("Failed to build validation report for %s: %s", workdir_path, exc)
            raise CheckovAdapterError(f"Failed to build validation report for {workdir_path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: process execution
    # ------------------------------------------------------------------
    def _run_checkov(self, workdir: Path) -> "subprocess.CompletedProcess[str]":
        """Execute Checkov against `workdir`.

        Unlike `terraform validate` (which has no directory argument
        and always operates on the process's current working
        directory), Checkov takes an explicit `-d` directory flag. This
        method therefore passes `workdir` via that flag rather than via
        `subprocess.run`'s `cwd` argument, and leaves the subprocess's
        working directory unset.

        Args:
            workdir: The Terraform directory to scan.

        Returns:
            The completed process, with `stdout`, `stderr`, and
            `returncode` captured as text. This method never inspects
            `returncode` itself — a non-zero exit is a normal, expected
            outcome of Checkov reporting failed checks.

        Raises:
            CheckovAdapterError: If the Checkov executable cannot be
                found, the process times out, or launching it otherwise
                fails at the OS level.
        """
        command = [self.checkov_executable, "-d", str(workdir), "-o", "json", "--framework", _FRAMEWORK]
        logger.info("Running '%s' (timeout=%ss)", " ".join(command), self.timeout_seconds)

        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            logger.error("Checkov executable not found: '%s'", self.checkov_executable)
            raise CheckovAdapterError(
                f"Checkov executable not found: '{self.checkov_executable}'. "
                f"Ensure Checkov is installed and on PATH, or configure an explicit path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("Checkov scan timed out after %s second(s) for %s", self.timeout_seconds, workdir)
            raise CheckovAdapterError(
                f"Checkov scan timed out after {self.timeout_seconds} second(s) for {workdir}"
            ) from exc
        except OSError as exc:
            logger.error("Failed to execute Checkov for %s: %s", workdir, exc)
            raise CheckovAdapterError(f"Failed to execute Checkov for {workdir}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: output parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_output(stdout: str) -> Any:
        """Parse Checkov's JSON output.

        Args:
            stdout: The raw stdout text from Checkov.

        Returns:
            The parsed top-level JSON value (a dict for a single-
            framework run, or a list for a multi-framework run — see
            `_extract_results`).

        Raises:
            CheckovAdapterError: If `stdout` is not valid JSON.
        """
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Checkov JSON output: %s", exc)
            raise CheckovAdapterError(f"Failed to parse Checkov JSON output: {exc}") from exc

    @staticmethod
    def _extract_results(data: Any) -> Dict[str, Any]:
        """Normalize Checkov's top-level output down to one `results` block.

        Checkov emits a single report object for a single-framework
        run, or a JSON array of report objects (one per detected
        framework) otherwise. This adapter always runs with
        `--framework terraform`, so when given an array it selects only
        the entry whose `check_type` is `"terraform"` — it never falls
        back to an arbitrary other entry, since silently substituting a
        different framework's findings would be unsafe for a validation
        report claiming to represent Terraform. An empty array (nothing
        scanned/reported at all) is treated as a usable, empty result;
        a non-empty array containing no Terraform-tagged entry is not.

        A selected report object that lacks a `results` key entirely is
        treated as malformed and raises, rather than silently becoming
        an empty (and therefore synthetically `PASSED`) result — e.g.
        `{"check_type": "terraform"}` with no `results` key at all is a
        malformed report, not a clean scan. An explicitly empty
        `results: {}` is accepted and represents a legitimate
        zero-check scan.

        Args:
            data: The parsed top-level Checkov JSON value.

        Returns:
            The `results` dict from the selected report, or an empty
            dict if Checkov's top-level output was an empty array.

        Raises:
            CheckovAdapterError: If `data` is neither a dict nor a
                list; if `data` is a non-empty list containing no
                report whose `check_type` is `"terraform"`; if the
                selected report does not contain a `results` key; or if
                `results` is present but not a dict.
        """
        if isinstance(data, dict):
            report: Dict[str, Any] = data
        elif isinstance(data, list):
            if not data:
                return {}

            terraform_reports = [
                item for item in data if isinstance(item, dict) and item.get("check_type") == _FRAMEWORK
            ]
            if not terraform_reports:
                logger.error(
                    "Checkov output array contained no report with check_type == '%s': %r", _FRAMEWORK, data
                )
                raise CheckovAdapterError(
                    f"Checkov output array contained no report with check_type == '{_FRAMEWORK}'"
                )
            report = terraform_reports[0]
        else:
            logger.error("Expected Checkov JSON to be an object or a list, got %s", type(data).__name__)
            raise CheckovAdapterError(f"Expected Checkov JSON to be an object or a list, got {type(data).__name__}")

        if "results" not in report:
            logger.error("Selected Checkov report is missing required key 'results': %r", report)
            raise CheckovAdapterError(f"Selected Checkov report is missing required key 'results': {report!r}")

        results = report["results"]
        if not isinstance(results, dict):
            logger.error("Expected 'results' to be an object, got %s", type(results).__name__)
            raise CheckovAdapterError(f"Expected 'results' to be an object, got {type(results).__name__}")

        return results

    @staticmethod
    def _extract_bucket(results: Dict[str, Any], key: str) -> List[Any]:
        """Extract one named list (e.g. `"failed_checks"`) from `results`.

        Args:
            results: The parsed `results` dict.
            key: One of `"passed_checks"`, `"failed_checks"`,
                `"skipped_checks"`, or `"parsing_errors"`.

        Returns:
            The value of `results[key]`, or an empty list if the key is
            absent or `None`.

        Raises:
            CheckovAdapterError: If `results[key]` is present and
                neither `None` nor a list.
        """
        bucket = results.get(key)
        if bucket is None:
            return []

        if not isinstance(bucket, list):
            logger.error("Expected '%s' to be a list, got %s", key, type(bucket).__name__)
            raise CheckovAdapterError(f"Expected '{key}' to be a list, got {type(bucket).__name__}")

        return bucket

    # ------------------------------------------------------------------
    # Internal: check entry -> ValidationFinding translation
    # ------------------------------------------------------------------
    def _check_to_finding(
        self, check: Any, status: ValidationStatus, index: int, bucket_name: str
    ) -> ValidationFinding:
        """Translate one Checkov check entry into a `ValidationFinding`.

        A check entry that is not a dict, or that has neither a usable
        `check_name` nor `check_id`, is treated as malformed and raises
        — Checkov reported a result here, so silently discarding it
        would mean a research-grade assurance system quietly dropping a
        security-relevant result rather than surfacing that it could
        not be interpreted. This is distinct from a structurally valid
        entry that simply omits optional fields (`severity`,
        `file_path`, `file_line_range`, etc.), which is still handled
        normally.

        Args:
            check: One entry from a Checkov results bucket, in whatever
                shape it happens to be.
            status: The `ValidationStatus` implied by the bucket this
                entry came from.
            index: The entry's position within its bucket, used only
                for logging.
            bucket_name: The name of the bucket this entry came from,
                used only for logging.

        Returns:
            A new `ValidationFinding`.

        Raises:
            CheckovAdapterError: If `check` is not a dict, if it lacks
                both a usable `check_name` and `check_id`, or if the
                entry's data is otherwise well-formed enough to build a
                finding from but `validation_result.create_finding()`
                itself rejects it.
        """
        if not isinstance(check, dict):
            logger.error("Malformed %s entry at index %d: expected a dict, got %r", bucket_name, index, check)
            raise CheckovAdapterError(
                f"Malformed {bucket_name} entry at index {index}: expected a dict, got "
                f"{type(check).__name__}"
            )

        check_id = self._clean_optional_string(check.get("check_id"))
        check_name = self._clean_optional_string(check.get("check_name"))

        message = self._build_check_message(check, check_name, check_id, status, index, bucket_name)

        severity = self._map_check_severity(check.get("severity"), status)
        resource_id = self._clean_optional_string(check.get("resource"))
        file_path = self._clean_optional_string(check.get("file_path"))
        line = self._extract_start_line(check.get("file_line_range"))

        try:
            return create_finding(
                tool=_TOOL_NAME,
                provider=_PROVIDER_NAME,
                status=status,
                severity=severity,
                message=message,
                rule_id=check_id,
                resource_id=resource_id,
                file_path=file_path,
                line=line,
                column=None,
            )
        except ValidationResultError as exc:
            logger.error("Failed to build finding for %s entry at index %d: %s", bucket_name, index, exc)
            raise CheckovAdapterError(
                f"Failed to build finding for {bucket_name} entry at index {index}: {exc}"
            ) from exc

    @staticmethod
    def _build_check_message(
        check: Dict[str, Any],
        check_name: Optional[str],
        check_id: Optional[str],
        status: ValidationStatus,
        index: int,
        bucket_name: str,
    ) -> str:
        """Build a finding message from a check entry's name/id (and skip reason).

        Prefers `check_name`; falls back to `f"Check {check_id}"` if
        only the ID is available. For a skipped check, a skip reason
        (if present) is appended as `"{base}: {reason}"`, mirroring
        `terraform_validate_adapter.py`'s `"{summary}: {detail}"`
        pattern.

        Args:
            check: The full check entry, used to look up a skip reason.
            check_name: The entry's cleaned `check_name`, if any.
            check_id: The entry's cleaned `check_id`, if any.
            status: The status implied by this entry's bucket.
            index: The entry's position within its bucket, used only
                for logging.
            bucket_name: The name of the bucket this entry came from,
                used only for logging.

        Returns:
            The built message.

        Raises:
            CheckovAdapterError: If neither `check_name` nor `check_id`
                is usable — there is no basis on which to build any
                message for this entry.
        """
        base = check_name or (f"Check {check_id}" if check_id else None)
        if base is None:
            logger.error(
                "Malformed %s entry at index %d: no usable check_name or check_id", bucket_name, index
            )
            raise CheckovAdapterError(
                f"Malformed {bucket_name} entry at index {index}: no usable check_name or check_id"
            )

        if status is ValidationStatus.SKIPPED:
            skip_reason = CheckovAdapter._extract_skip_reason(check)
            if skip_reason:
                return f"{base}: {skip_reason}"

        return base

    @staticmethod
    def _extract_skip_reason(check: Dict[str, Any]) -> Optional[str]:
        """Extract a human-readable skip reason from a skipped check entry.

        Different Checkov versions have placed this under different
        keys; both are checked defensively.

        Args:
            check: The check entry.

        Returns:
            The skip reason/comment, or `None` if none is present.
        """
        check_result = check.get("check_result")
        if isinstance(check_result, dict):
            suppress_comment = CheckovAdapter._clean_optional_string(check_result.get("suppress_comment"))
            if suppress_comment:
                return suppress_comment

        return CheckovAdapter._clean_optional_string(check.get("skip_comment"))

    @staticmethod
    def _map_check_severity(severity_raw: Any, status: ValidationStatus) -> ValidationSeverity:
        """Map a Checkov check's `severity` value to a `ValidationSeverity`.

        Checkov's own severity vocabulary (`CRITICAL`/`HIGH`/`MEDIUM`/
        `LOW`/`INFO`) matches `ValidationSeverity`'s almost exactly, so
        a valid value is used directly (case-insensitive). Open-source
        Checkov runs frequently omit severity entirely; a missing or
        unrecognized value falls back to `NONE` for a passed or skipped
        check (nothing to warn about), or `MEDIUM` for a failed or
        errored check (a real issue whose severity is simply unknown).

        Args:
            severity_raw: The check entry's `severity` value, in
                whatever shape it happens to be.
            status: The status this check was translated to, used only
                to pick a sensible fallback.

        Returns:
            The corresponding `ValidationSeverity`.
        """
        if isinstance(severity_raw, str) and severity_raw.strip():
            try:
                return ValidationSeverity(severity_raw.strip().upper())
            except ValueError:
                logger.warning("Unrecognized Checkov severity %r for status %s", severity_raw, status)

        if status in (ValidationStatus.PASSED, ValidationStatus.SKIPPED):
            return ValidationSeverity.NONE
        return ValidationSeverity.MEDIUM

    @staticmethod
    def _extract_start_line(file_line_range: Any) -> Optional[int]:
        """Extract a positive integer start line from a check's `file_line_range`.

        Checkov reports `file_line_range` as a `[start_line, end_line]`
        pair and does not report column information at all, so this
        adapter never populates `ValidationFinding.column`.
        `ValidationFinding` uses 1-based source positions, so any value
        that is not a positive integer is treated as absent.

        Args:
            file_line_range: The check entry's `file_line_range` value,
                in whatever shape it happens to be.

        Returns:
            The start line, or `None` if `file_line_range` is not a
            non-empty list or its first element is not a positive
            integer.
        """
        if not isinstance(file_line_range, list) or not file_line_range:
            return None

        value = file_line_range[0]
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
    # Internal: parsing error -> ValidationFinding translation
    # ------------------------------------------------------------------
    def _parsing_error_to_finding(self, parsing_error: Any, index: int) -> ValidationFinding:
        """Translate one Checkov parsing error into a `ValidationFinding`.

        A file Checkov could not parse is represented as
        `status=ERROR` (a check that could not be completed), not
        `FAILED` (a check that ran and found a problem) — matching
        `ValidationStatus.ERROR`'s own definition.

        Checkov has reported parsing errors both as plain file-path
        strings and as dictionaries (e.g. `{"file": ..., "error":
        ...}`) across versions; both shapes are handled. An entry that
        matches neither shape closely enough to yield any usable
        message is treated as malformed and raises, rather than being
        silently discarded.

        Args:
            parsing_error: One entry from Checkov's `parsing_errors`
                list, in whatever shape it happens to be.
            index: The entry's position in the list, used only for
                logging.

        Returns:
            A new `ValidationFinding`.

        Raises:
            CheckovAdapterError: If `parsing_error` yields no usable
                message, or if its data is otherwise well-formed enough
                to build a finding from but
                `validation_result.create_finding()` itself rejects it.
        """
        file_path: Optional[str] = None
        message: Optional[str] = None

        if isinstance(parsing_error, str):
            file_path = self._clean_optional_string(parsing_error)
            if file_path:
                message = f"Checkov failed to parse {file_path}"
        elif isinstance(parsing_error, dict):
            file_path = self._clean_optional_string(parsing_error.get("file") or parsing_error.get("file_path"))
            reason = self._clean_optional_string(parsing_error.get("error") or parsing_error.get("message"))
            if file_path and reason:
                message = f"Checkov failed to parse {file_path}: {reason}"
            elif file_path:
                message = f"Checkov failed to parse {file_path}"
            elif reason:
                message = f"Checkov encountered a parsing error: {reason}"

        if message is None:
            logger.error("Malformed parsing_errors entry at index %d: %r", index, parsing_error)
            raise CheckovAdapterError(f"Malformed parsing_errors entry at index {index}: {parsing_error!r}")

        try:
            return create_finding(
                tool=_TOOL_NAME,
                provider=_PROVIDER_NAME,
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.MEDIUM,
                message=message,
                rule_id=None,
                resource_id=None,
                file_path=file_path,
            )
        except ValidationResultError as exc:
            logger.error("Failed to build finding for parsing error at index %d: %s", index, exc)
            raise CheckovAdapterError(f"Failed to build finding for parsing error at index {index}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal: synthetic finding
    # ------------------------------------------------------------------
    @staticmethod
    def _build_synthetic_no_checks_finding() -> ValidationFinding:
        """Build the synthetic `PASSED` finding used when Checkov finds nothing to check.

        Used when a scan produces zero passed, failed, and skipped
        checks and zero parsing errors, so a clean/empty scan never
        produces an empty (zero-check) report — mirroring
        `TerraformValidateAdapter`'s synthetic finding for the same
        reason.

        Returns:
            A `ValidationFinding` with `status=PASSED`,
            `severity=NONE`, and `rule_id="CHECKOV_NO_CHECKS"`.
        """
        return create_finding(
            tool=_TOOL_NAME,
            provider=_PROVIDER_NAME,
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.NONE,
            message=_SYNTHETIC_NO_CHECKS_MESSAGE,
            rule_id=_SYNTHETIC_NO_CHECKS_RULE_ID,
        )


__all__ = [
    "CheckovAdapter",
    "CheckovAdapterError",
]
