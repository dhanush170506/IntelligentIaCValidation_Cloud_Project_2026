"""test_checkov_adapter.py.

Comprehensive tests for `checkov_adapter.py`.

No real Checkov installation is required: every test mocks
`subprocess.run` at the point `checkov_adapter.py` calls it, so these
tests exercise only the adapter's own logic (command construction,
output parsing, check-entry translation, and error handling).

Run directly:
    python -m src.ml_model.module3_static_validation.test_checkov_adapter
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

# See validation_result.py / terraform_validate_adapter.py for why this
# try/except import pattern is used: it lets this file run correctly
# both via `python -m src.ml_model.module3_static_validation....` and
# via direct/flat execution.
try:
    from . import checkov_adapter as ca
    from .checkov_adapter import CheckovAdapter, CheckovAdapterError
    from .validation_schema import ValidationReport, ValidationSeverity, ValidationStatus
except ImportError:
    import checkov_adapter as ca  # type: ignore[no-redef]
    from checkov_adapter import CheckovAdapter, CheckovAdapterError  # type: ignore[no-redef]
    from validation_schema import (  # type: ignore[no-redef]
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )


def _completed_process(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    """Build a `subprocess.CompletedProcess` as `subprocess.run` would return it.

    Args:
        stdout: The process's captured stdout text.
        stderr: The process's captured stderr text.
        returncode: The process's exit code.

    Returns:
        A `subprocess.CompletedProcess` matching what
        `CheckovAdapter._run_checkov` expects.
    """
    return subprocess.CompletedProcess(
        args=["checkov", "-d", ".", "-o", "json", "--framework", "terraform"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _report_payload(
    passed=None, failed=None, skipped=None, parsing_errors=None, check_type: str = "terraform"
) -> str:
    """Build a single-framework Checkov JSON report as a string.

    Args:
        passed: Entries for `results.passed_checks`.
        failed: Entries for `results.failed_checks`.
        skipped: Entries for `results.skipped_checks`.
        parsing_errors: Entries for `results.parsing_errors`.
        check_type: The report's `check_type` value.

    Returns:
        The JSON-encoded report.
    """
    return json.dumps(
        {
            "check_type": check_type,
            "results": {
                "passed_checks": passed or [],
                "failed_checks": failed or [],
                "skipped_checks": skipped or [],
                "parsing_errors": parsing_errors or [],
            },
        }
    )


class CheckovAdapterTests(unittest.TestCase):
    """Tests for `CheckovAdapter`."""

    def setUp(self) -> None:
        self.adapter = CheckovAdapter()

    # ------------------------------------------------------------------
    # 1. Multiple passed checks
    # ------------------------------------------------------------------
    def test_multiple_passed_checks(self) -> None:
        payload = _report_payload(
            passed=[
                {"check_id": "CKV_AWS_1", "check_name": "Ensure A", "resource": "aws_s3_bucket.a"},
                {"check_id": "CKV_AWS_2", "check_name": "Ensure B", "resource": "aws_s3_bucket.b"},
            ]
        )

        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 2)
        for finding in report.findings:
            self.assertEqual(finding.status, ValidationStatus.PASSED)
            self.assertEqual(finding.severity, ValidationSeverity.NONE)
            self.assertEqual(finding.tool, "checkov")
            self.assertEqual(finding.provider, "Terraform")

    # ------------------------------------------------------------------
    # 2. Single failed check: status, severity, rule_id, resource_id, file/line
    # ------------------------------------------------------------------
    def test_single_failed_check(self) -> None:
        payload = _report_payload(
            failed=[
                {
                    "check_id": "CKV_AWS_24",
                    "check_name": "Ensure security group does not allow unrestricted ingress",
                    "severity": "HIGH",
                    "resource": "aws_security_group.web_sg",
                    "file_path": "/main.tf",
                    "file_line_range": [10, 25],
                }
            ]
        )

        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.FAILED)
        self.assertEqual(finding.severity, ValidationSeverity.HIGH)
        self.assertEqual(finding.rule_id, "CKV_AWS_24")
        self.assertEqual(finding.resource_id, "aws_security_group.web_sg")
        self.assertEqual(finding.file_path, "/main.tf")
        self.assertEqual(finding.line, 10)
        self.assertIsNone(finding.column)
        self.assertEqual(finding.message, "Ensure security group does not allow unrestricted ingress")

    # ------------------------------------------------------------------
    # 3. Single skipped check, with and without a skip reason
    # ------------------------------------------------------------------
    def test_single_skipped_check_with_reason(self) -> None:
        payload = _report_payload(
            skipped=[
                {
                    "check_id": "CKV_AWS_3",
                    "check_name": "Some check",
                    "check_result": {"suppress_comment": "not applicable in this environment"},
                }
            ]
        )
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.SKIPPED)
        self.assertEqual(finding.severity, ValidationSeverity.NONE)
        self.assertEqual(finding.message, "Some check: not applicable in this environment")

    def test_single_skipped_check_without_reason(self) -> None:
        payload = _report_payload(skipped=[{"check_id": "CKV_AWS_3", "check_name": "Some check"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(report.findings[0].message, "Some check")

    # ------------------------------------------------------------------
    # 4. Missing severity on a failed check -> defaults to MEDIUM
    # ------------------------------------------------------------------
    def test_missing_severity_on_failed_check_defaults_to_medium(self) -> None:
        payload = _report_payload(failed=[{"check_id": "CKV_AWS_9", "check_name": "no severity given"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(report.findings[0].severity, ValidationSeverity.MEDIUM)

    def test_unrecognized_severity_falls_back_correctly(self) -> None:
        payload = _report_payload(
            failed=[{"check_id": "CKV_AWS_9", "check_name": "weird severity", "severity": "not-a-real-severity"}]
        )
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(report.findings[0].severity, ValidationSeverity.MEDIUM)

    # ------------------------------------------------------------------
    # 5. Multiple checks across all buckets: count, order, summary counts
    # ------------------------------------------------------------------
    def test_multiple_checks_across_buckets_order_and_summary(self) -> None:
        payload = _report_payload(
            passed=[{"check_id": "P1", "check_name": "passed one"}],
            failed=[
                {"check_id": "F1", "check_name": "failed one", "severity": "CRITICAL"},
                {"check_id": "F2", "check_name": "failed two", "severity": "LOW"},
            ],
            skipped=[{"check_id": "S1", "check_name": "skipped one"}],
            parsing_errors=["/broken.tf"],
        )

        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 5)
        # Deterministic order: passed, failed, skipped, parsing_errors.
        self.assertEqual(
            [f.message for f in report.findings],
            ["passed one", "failed one", "failed two", "skipped one", "Checkov failed to parse /broken.tf"],
        )
        summary = report.validation_summary
        self.assertEqual(summary.total_checks, 5)
        self.assertEqual(summary.passed, 1)
        self.assertEqual(summary.failed, 2)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.errors, 1)

    # ------------------------------------------------------------------
    # 6. Missing/malformed file_line_range -> line=None
    # ------------------------------------------------------------------
    def test_missing_file_line_range_yields_none_line(self) -> None:
        payload = _report_payload(failed=[{"check_id": "F1", "check_name": "no range"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertIsNone(report.findings[0].line)
        self.assertIsNone(report.findings[0].file_path)

    def test_malformed_file_line_range_yields_none_line(self) -> None:
        payload = _report_payload(failed=[{"check_id": "F1", "check_name": "bad range", "file_line_range": "nope"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertIsNone(report.findings[0].line)

    def test_empty_file_line_range_yields_none_line(self) -> None:
        payload = _report_payload(failed=[{"check_id": "F1", "check_name": "empty range", "file_line_range": []}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertIsNone(report.findings[0].line)

    # ------------------------------------------------------------------
    # 7. Missing check_name but check_id present -> message falls back
    # ------------------------------------------------------------------
    def test_missing_check_name_falls_back_to_check_id(self) -> None:
        payload = _report_payload(failed=[{"check_id": "CKV_AWS_99"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(report.findings[0].message, "Check CKV_AWS_99")
        self.assertEqual(report.findings[0].rule_id, "CKV_AWS_99")

    # ------------------------------------------------------------------
    # 8. Missing both check_name and check_id -> malformed, must raise
    # ------------------------------------------------------------------
    def test_missing_check_name_and_id_raises_adapter_error(self) -> None:
        payload = _report_payload(failed=[{"severity": "HIGH"}], passed=[{"check_id": "P1", "check_name": "kept"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 9 / 10. Parsing errors: string entries and dict entries
    # ------------------------------------------------------------------
    def test_string_parsing_error(self) -> None:
        payload = _report_payload(parsing_errors=["/broken.tf"])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.ERROR)
        self.assertEqual(finding.severity, ValidationSeverity.MEDIUM)
        self.assertEqual(finding.file_path, "/broken.tf")
        self.assertEqual(finding.message, "Checkov failed to parse /broken.tf")

    def test_dict_parsing_error_with_file_and_reason(self) -> None:
        payload = _report_payload(parsing_errors=[{"file": "/broken.tf", "error": "unexpected token"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertEqual(finding.file_path, "/broken.tf")
        self.assertEqual(finding.message, "Checkov failed to parse /broken.tf: unexpected token")

    def test_dict_parsing_error_with_reason_only(self) -> None:
        payload = _report_payload(parsing_errors=[{"error": "unexpected token"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertIsNone(finding.file_path)
        self.assertEqual(finding.message, "Checkov encountered a parsing error: unexpected token")

    def test_malformed_parsing_error_entry_raises_adapter_error(self) -> None:
        payload = _report_payload(parsing_errors=[123, {}], passed=[{"check_id": "P1", "check_name": "kept"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 11. Non-zero return code with valid JSON: no exception
    # ------------------------------------------------------------------
    def test_nonzero_returncode_with_valid_results_does_not_raise(self) -> None:
        payload = _report_payload(failed=[{"check_id": "F1", "check_name": "bad config", "severity": "HIGH"}])

        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            try:
                report = self.adapter.validate("/fake/workdir")
            except CheckovAdapterError:
                self.fail("validate() raised CheckovAdapterError for an ordinary Checkov failure")

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].status, ValidationStatus.FAILED)

    # ------------------------------------------------------------------
    # 12. Invalid JSON
    # ------------------------------------------------------------------
    def test_invalid_json_raises_adapter_error(self) -> None:
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout="{not valid json")):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 13. Empty stdout
    # ------------------------------------------------------------------
    def test_empty_stdout_raises_adapter_error(self) -> None:
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout="", stderr="", returncode=1)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    def test_empty_stdout_error_message_includes_stderr(self) -> None:
        with patch.object(
            ca.subprocess, "run", return_value=_completed_process(stdout="", stderr="fatal: crashed", returncode=1)
        ):
            with self.assertRaises(CheckovAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("fatal: crashed", str(ctx.exception))

    # ------------------------------------------------------------------
    # 14. Checkov executable not found
    # ------------------------------------------------------------------
    def test_executable_not_found_raises_adapter_error(self) -> None:
        with patch.object(ca.subprocess, "run", side_effect=FileNotFoundError("no such file")):
            with self.assertRaises(CheckovAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("not found", str(ctx.exception))

    # ------------------------------------------------------------------
    # 15. Timeout
    # ------------------------------------------------------------------
    def test_timeout_raises_adapter_error(self) -> None:
        timeout_error = subprocess.TimeoutExpired(cmd=["checkov"], timeout=120.0)
        with patch.object(ca.subprocess, "run", side_effect=timeout_error):
            with self.assertRaises(CheckovAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("timed out", str(ctx.exception))

    # ------------------------------------------------------------------
    # 16. 'results' not a dict
    # ------------------------------------------------------------------
    def test_results_not_a_dict_raises_adapter_error(self) -> None:
        payload = json.dumps({"check_type": "terraform", "results": "not-a-dict"})
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    def test_missing_results_key_raises_adapter_error(self) -> None:
        """A report object with no 'results' key at all must not become a synthetic PASSED report."""
        payload = json.dumps({"check_type": "terraform"})
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CheckovAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("results", str(ctx.exception))

    def test_explicit_empty_results_dict_is_accepted(self) -> None:
        """An explicit 'results': {} is a legitimate zero-check scan, unlike a missing key entirely."""
        payload = json.dumps({"check_type": "terraform", "results": {}})
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].rule_id, "CHECKOV_NO_CHECKS")

    # ------------------------------------------------------------------
    # 17. A bucket present but not a list
    # ------------------------------------------------------------------
    def test_bucket_not_a_list_raises_adapter_error(self) -> None:
        payload = json.dumps({"check_type": "terraform", "results": {"failed_checks": "not-a-list"}})
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 18. Malformed individual check entry must raise, not be silently skipped
    # ------------------------------------------------------------------
    def test_malformed_individual_check_entry_raises_adapter_error(self) -> None:
        payload = _report_payload(failed=["not-a-dict", {"check_id": "F1", "check_name": "real one"}])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 19. Zero checks across all buckets -> synthetic PASSED finding
    # ------------------------------------------------------------------
    def test_all_empty_buckets_produce_synthetic_passed_finding(self) -> None:
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.PASSED)
        self.assertEqual(finding.severity, ValidationSeverity.NONE)
        self.assertEqual(finding.rule_id, "CHECKOV_NO_CHECKS")

    # ------------------------------------------------------------------
    # 20. Multi-framework (list) top-level shape
    # ------------------------------------------------------------------
    def test_list_of_reports_filters_to_terraform(self) -> None:
        payload = json.dumps(
            [
                {"check_type": "secrets", "results": {"failed_checks": [{"check_id": "SECRET1", "check_name": "leak"}]}},
                {
                    "check_type": "terraform",
                    "results": {"passed_checks": [{"check_id": "P1", "check_name": "terraform check"}]},
                },
            ]
        )
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].message, "terraform check")

    def test_list_of_reports_with_no_terraform_entry_raises_adapter_error(self) -> None:
        """A non-empty array containing no Terraform report must raise, never silently fall back to another framework."""
        payload = json.dumps(
            [{"check_type": "secrets", "results": {"failed_checks": [{"check_id": "SECRET1", "check_name": "leak"}]}}]
        )
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CheckovAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("terraform", str(ctx.exception))

    def test_empty_list_produces_synthetic_passed_finding(self) -> None:
        payload = json.dumps([])
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].rule_id, "CHECKOV_NO_CHECKS")

    def test_malformed_top_level_type_raises_adapter_error(self) -> None:
        payload = json.dumps("just a string")
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CheckovAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 21. shell=True is never used
    # ------------------------------------------------------------------
    def test_shell_is_never_true(self) -> None:
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        _, kwargs = mock_run.call_args
        self.assertIsNot(kwargs.get("shell"), True)

    # ------------------------------------------------------------------
    # 22. timeout is passed to subprocess
    # ------------------------------------------------------------------
    def test_timeout_is_passed_to_subprocess(self) -> None:
        adapter = CheckovAdapter(timeout_seconds=99.0)
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("/fake/workdir")

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 99.0)

    # ------------------------------------------------------------------
    # 23. Working directory passed via -d, not via cwd=
    # ------------------------------------------------------------------
    def test_workdir_is_passed_via_directory_flag(self) -> None:
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        args, kwargs = mock_run.call_args
        command = args[0]
        self.assertIn("-d", command)
        self.assertEqual(
            Path(command[command.index("-d") + 1]),
            Path("/fake/workdir")
        )
        self.assertNotIn("cwd", kwargs)

    # ------------------------------------------------------------------
    # 24. --framework terraform is present
    # ------------------------------------------------------------------
    def test_command_restricts_to_terraform_framework(self) -> None:
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        args, _ = mock_run.call_args
        command = args[0]
        self.assertIn("--framework", command)
        self.assertEqual(command[command.index("--framework") + 1], "terraform")
        self.assertIn("-o", command)
        self.assertEqual(command[command.index("-o") + 1], "json")

    # ------------------------------------------------------------------
    # 25. Custom Checkov executable is used
    # ------------------------------------------------------------------
    def test_custom_checkov_executable_is_used(self) -> None:
        adapter = CheckovAdapter(checkov_executable="/opt/bin/checkov")
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("/fake/workdir")

        args, _ = mock_run.call_args
        self.assertEqual(args[0][0], "/opt/bin/checkov")

    # ------------------------------------------------------------------
    # 26. Final object is a ValidationReport
    # ------------------------------------------------------------------
    def test_return_type_is_validation_report(self) -> None:
        payload = _report_payload()
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.provider, "Terraform")

    # ------------------------------------------------------------------
    # 27. Report summary matches findings
    # ------------------------------------------------------------------
    def test_report_summary_matches_findings(self) -> None:
        payload = _report_payload(
            failed=[
                {"check_id": "F1", "check_name": "e1", "severity": "HIGH"},
                {"check_id": "F2", "check_name": "e2", "severity": "LOW"},
            ],
            skipped=[{"check_id": "S1", "check_name": "s1"}],
        )
        with patch.object(ca.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        summary = report.validation_summary
        self.assertEqual(summary.total_checks, len(report.findings))
        self.assertEqual(summary.failed, sum(1 for f in report.findings if f.status == ValidationStatus.FAILED))
        self.assertEqual(summary.skipped, sum(1 for f in report.findings if f.status == ValidationStatus.SKIPPED))

    # ------------------------------------------------------------------
    # Constructor validation (bonus coverage, not in the numbered list)
    # ------------------------------------------------------------------
    def test_constructor_rejects_empty_executable(self) -> None:
        with self.assertRaises(CheckovAdapterError):
            CheckovAdapter(checkov_executable="")

    def test_constructor_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(CheckovAdapterError):
            CheckovAdapter(timeout_seconds=0)


def run_all_tests() -> int:
    """Run every test in this module and return a process-suitable exit code.

    Returns:
        `0` if every test passed, `1` otherwise.
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(CheckovAdapterTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
