"""test_terraform_validate_adapter.py.

Comprehensive tests for `terraform_validate_adapter.py`.

No real Terraform installation is required: every test mocks
`subprocess.run` at the point `terraform_validate_adapter.py` calls it,
so these tests exercise only the adapter's own logic (command
construction, output parsing, diagnostic translation, and error
handling).

Run directly:
    python -m src.ml_model.module3_static_validation.test_terraform_validate_adapter
"""

from __future__ import annotations

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
    from . import terraform_validate_adapter as tva
    from .terraform_validate_adapter import TerraformValidateAdapter, TerraformValidateAdapterError
    from .validation_schema import ValidationReport, ValidationSeverity, ValidationStatus
except ImportError:
    import terraform_validate_adapter as tva  # type: ignore[no-redef]
    from terraform_validate_adapter import (  # type: ignore[no-redef]
        TerraformValidateAdapter,
        TerraformValidateAdapterError,
    )
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
        `TerraformValidateAdapter._run_terraform_validate` expects.
    """
    return subprocess.CompletedProcess(
        args=["terraform", "validate", "-json"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TerraformValidateAdapterTests(unittest.TestCase):
    """Tests for `TerraformValidateAdapter`."""

    def setUp(self) -> None:
        self.adapter = TerraformValidateAdapter()

    # ------------------------------------------------------------------
    # 1. Valid Terraform output -> exactly one PASSED finding
    # ------------------------------------------------------------------
    def test_valid_output_with_no_diagnostics_produces_synthetic_passed_finding(self) -> None:
        payload = json.dumps({"valid": True, "error_count": 0, "warning_count": 0, "diagnostics": []})

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.PASSED)
        self.assertEqual(finding.severity, ValidationSeverity.NONE)
        self.assertEqual(finding.rule_id, "TERRAFORM_VALIDATE")
        self.assertEqual(finding.tool, "terraform_validate")
        self.assertEqual(finding.provider, "Terraform")

    # ------------------------------------------------------------------
    # 2. Single error diagnostic
    # ------------------------------------------------------------------
    def test_single_error_diagnostic(self) -> None:
        payload = json.dumps(
            {
                "valid": False,
                "diagnostics": [
                    {
                        "severity": "error",
                        "summary": "Unsupported argument",
                        "detail": "An argument named \"foo\" is not expected here.",
                        "range": {"filename": "main.tf", "start": {"line": 10, "column": 5}},
                    }
                ],
            }
        )

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.FAILED)
        self.assertEqual(finding.severity, ValidationSeverity.HIGH)
        self.assertEqual(finding.message, 'Unsupported argument: An argument named "foo" is not expected here.')
        self.assertEqual(finding.file_path, "main.tf")
        self.assertEqual(finding.line, 10)
        self.assertEqual(finding.column, 5)

    # ------------------------------------------------------------------
    # 3. Single warning diagnostic
    # ------------------------------------------------------------------
    def test_single_warning_diagnostic(self) -> None:
        payload = json.dumps(
            {
                "valid": True,
                "diagnostics": [
                    {"severity": "warning", "summary": "Deprecated attribute", "detail": "Use 'new_attr' instead."}
                ],
            }
        )

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.WARNING)
        self.assertEqual(finding.severity, ValidationSeverity.LOW)

    # ------------------------------------------------------------------
    # 4. Multiple diagnostics: count, order, summary counts
    # ------------------------------------------------------------------
    def test_multiple_diagnostics_order_and_summary_counts(self) -> None:
        payload = json.dumps(
            {
                "valid": False,
                "diagnostics": [
                    {"severity": "error", "summary": "first error"},
                    {"severity": "warning", "summary": "first warning"},
                    {"severity": "error", "summary": "second error"},
                ],
            }
        )

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 3)
        self.assertEqual([f.message for f in report.findings], ["first error", "first warning", "second error"])
        self.assertEqual(report.validation_summary.failed, 2)
        self.assertEqual(report.validation_summary.warnings, 1)
        self.assertEqual(report.validation_summary.total_checks, 3)

    # ------------------------------------------------------------------
    # 5. Missing optional range
    # ------------------------------------------------------------------
    def test_missing_range_yields_none_position_fields(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "error", "summary": "no range here"}]})

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertIsNone(finding.file_path)
        self.assertIsNone(finding.line)
        self.assertIsNone(finding.column)

    # ------------------------------------------------------------------
    # 6 / 7 / 8. summary/detail combination cases
    # ------------------------------------------------------------------
    def test_missing_summary_uses_detail_only(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "error", "detail": "detail only"}]})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(report.findings[0].message, "detail only")

    def test_missing_detail_uses_summary_only(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "error", "summary": "summary only"}]})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(report.findings[0].message, "summary only")

    def test_both_summary_and_detail_are_combined(self) -> None:
        payload = json.dumps(
            {"valid": False, "diagnostics": [{"severity": "error", "summary": "sum", "detail": "det"}]}
        )
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        self.assertEqual(report.findings[0].message, "sum: det")

    # ------------------------------------------------------------------
    # 9. Non-zero return code with valid JSON diagnostics: no exception
    # ------------------------------------------------------------------
    def test_nonzero_returncode_with_valid_diagnostics_does_not_raise(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "error", "summary": "bad config"}]})

        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            try:
                report = self.adapter.validate("/fake/workdir")
            except TerraformValidateAdapterError:
                self.fail("validate() raised TerraformValidateAdapterError for an ordinary validation failure")

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].status, ValidationStatus.FAILED)

    # ------------------------------------------------------------------
    # 10. Invalid JSON
    # ------------------------------------------------------------------
    def test_invalid_json_raises_adapter_error(self) -> None:
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout="{not valid json")):
            with self.assertRaises(TerraformValidateAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 11. Empty stdout
    # ------------------------------------------------------------------
    def test_empty_stdout_raises_adapter_error(self) -> None:
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout="", stderr="", returncode=1)):
            with self.assertRaises(TerraformValidateAdapterError):
                self.adapter.validate("/fake/workdir")

    def test_empty_stdout_error_message_includes_stderr(self) -> None:
        with patch.object(
            tva.subprocess, "run", return_value=_completed_process(stdout="", stderr="fatal: no config", returncode=1)
        ):
            with self.assertRaises(TerraformValidateAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("fatal: no config", str(ctx.exception))

    # ------------------------------------------------------------------
    # 12. Terraform executable not found
    # ------------------------------------------------------------------
    def test_executable_not_found_raises_adapter_error(self) -> None:
        with patch.object(tva.subprocess, "run", side_effect=FileNotFoundError("no such file")):
            with self.assertRaises(TerraformValidateAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("not found", str(ctx.exception))

    # ------------------------------------------------------------------
    # 13. Timeout
    # ------------------------------------------------------------------
    def test_timeout_raises_adapter_error(self) -> None:
        timeout_error = subprocess.TimeoutExpired(cmd=["terraform", "validate", "-json"], timeout=60.0)
        with patch.object(tva.subprocess, "run", side_effect=timeout_error):
            with self.assertRaises(TerraformValidateAdapterError) as ctx:
                self.adapter.validate("/fake/workdir")
        self.assertIn("timed out", str(ctx.exception))

    # ------------------------------------------------------------------
    # 14. Malformed diagnostics collection (not a list)
    # ------------------------------------------------------------------
    def test_diagnostics_not_a_list_raises_adapter_error(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": "not-a-list"})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            with self.assertRaises(TerraformValidateAdapterError):
                self.adapter.validate("/fake/workdir")

    # ------------------------------------------------------------------
    # 15. Malformed individual diagnostic (skipped, not fatal)
    # ------------------------------------------------------------------
    def test_malformed_individual_diagnostic_is_skipped(self) -> None:
        payload = json.dumps(
            {
                "valid": False,
                "diagnostics": [
                    "not-a-dict",
                    {"severity": "error", "summary": "a real diagnostic"},
                ],
            }
        )
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].message, "a real diagnostic")

    def test_diagnostic_with_no_summary_or_detail_is_skipped(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "error"}]})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")
        # No usable diagnostic and valid=False -> no synthetic finding either.
        self.assertEqual(len(report.findings), 0)

    # ------------------------------------------------------------------
    # 16. Unknown severity
    # ------------------------------------------------------------------
    def test_unknown_severity_maps_to_error_and_medium(self) -> None:
        payload = json.dumps({"valid": False, "diagnostics": [{"severity": "note", "summary": "informational"}]})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.ERROR)
        self.assertEqual(finding.severity, ValidationSeverity.MEDIUM)

    # ------------------------------------------------------------------
    # 17. shell=True is never used
    # ------------------------------------------------------------------
    def test_shell_is_never_true(self) -> None:
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        _, kwargs = mock_run.call_args
        self.assertIsNot(kwargs.get("shell"), True)

    # ------------------------------------------------------------------
    # 18. timeout is passed to subprocess
    # ------------------------------------------------------------------
    def test_timeout_is_passed_to_subprocess(self) -> None:
        adapter = TerraformValidateAdapter(timeout_seconds=42.0)
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("/fake/workdir")

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 42.0)

    # ------------------------------------------------------------------
    # 19. working directory is passed correctly
    # ------------------------------------------------------------------
    def test_workdir_is_passed_correctly(self) -> None:
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("cwd"), "/fake/workdir")

    def test_command_invokes_validate_json_only(self) -> None:
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("/fake/workdir")

        args, _ = mock_run.call_args
        command = args[0]
        self.assertEqual(command, ["terraform", "validate", "-json"])

    def test_custom_terraform_executable_is_used(self) -> None:
        adapter = TerraformValidateAdapter(terraform_executable="/opt/bin/terraform")
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("/fake/workdir")

        args, _ = mock_run.call_args
        self.assertEqual(args[0][0], "/opt/bin/terraform")

    # ------------------------------------------------------------------
    # 20. Final object is a ValidationReport
    # ------------------------------------------------------------------
    def test_return_type_is_validation_report(self) -> None:
        payload = json.dumps({"valid": True, "diagnostics": []})
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("/fake/workdir")
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.provider, "Terraform")

    # ------------------------------------------------------------------
    # 21. Report summary matches findings
    # ------------------------------------------------------------------
    def test_report_summary_matches_findings(self) -> None:
        payload = json.dumps(
            {
                "valid": False,
                "diagnostics": [
                    {"severity": "error", "summary": "e1"},
                    {"severity": "error", "summary": "e2"},
                    {"severity": "warning", "summary": "w1"},
                ],
            }
        )
        with patch.object(tva.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=1)):
            report = self.adapter.validate("/fake/workdir")

        summary = report.validation_summary
        self.assertEqual(summary.total_checks, len(report.findings))
        self.assertEqual(summary.failed, sum(1 for f in report.findings if f.status == ValidationStatus.FAILED))
        self.assertEqual(summary.warnings, sum(1 for f in report.findings if f.status == ValidationStatus.WARNING))

    # ------------------------------------------------------------------
    # Constructor validation (bonus coverage, not in the numbered list)
    # ------------------------------------------------------------------
    def test_constructor_rejects_empty_executable(self) -> None:
        with self.assertRaises(TerraformValidateAdapterError):
            TerraformValidateAdapter(terraform_executable="")

    def test_constructor_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(TerraformValidateAdapterError):
            TerraformValidateAdapter(timeout_seconds=0)


def run_all_tests() -> int:
    """Run every test in this module and return a process-suitable exit code.

    Returns:
        `0` if every test passed, `1` otherwise.
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TerraformValidateAdapterTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
