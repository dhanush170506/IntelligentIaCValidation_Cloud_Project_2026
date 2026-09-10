"""test_cfn_lint_adapter.py.

Comprehensive tests for `cfn_lint_adapter.py`.

No real cfn-lint installation is required: every test mocks
`subprocess.run` at the point `cfn_lint_adapter.py` calls it, so these
tests exercise only the adapter's own logic (command construction,
output parsing, diagnostic translation, and error handling).

Run directly:
    python -m src.ml_model.module3_static_validation.test_cfn_lint_adapter
"""

from __future__ import annotations
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

# See validation_result.py / terraform_validate_adapter.py /
# checkov_adapter.py for why this try/except import pattern is used: it
# lets this file run correctly both via
# `python -m src.ml_model.module3_static_validation....` and via
# direct/flat execution.
try:
    from . import cfn_lint_adapter as cla
    from .cfn_lint_adapter import CfnLintAdapter, CfnLintAdapterError
    from .validation_schema import ValidationReport, ValidationSeverity, ValidationStatus
except ImportError:
    import cfn_lint_adapter as cla  # type: ignore[no-redef]
    from cfn_lint_adapter import CfnLintAdapter, CfnLintAdapterError  # type: ignore[no-redef]
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
        `CfnLintAdapter._run_cfn_lint` expects.
    """
    return subprocess.CompletedProcess(
        args=["cfn-lint", "--format", "json", "template.yaml"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _diagnostics_payload(diagnostics) -> str:
    """Encode a list of diagnostic dicts as cfn-lint's bare top-level JSON array.

    Args:
        diagnostics: The list of diagnostic entries.

    Returns:
        The JSON-encoded array.
    """
    return json.dumps(diagnostics)


class CfnLintAdapterTests(unittest.TestCase):
    """Tests for `CfnLintAdapter`."""

    def setUp(self) -> None:
        self.adapter = CfnLintAdapter()

    # ------------------------------------------------------------------
    # 1. Multiple diagnostics
    # ------------------------------------------------------------------
    def test_multiple_diagnostics(self) -> None:
        payload = _diagnostics_payload(
            [
                {"Rule": {"Id": "E3001"}, "Level": "Error", "Message": "first error"},
                {"Rule": {"Id": "W2001"}, "Level": "Warning", "Message": "first warning"},
                {"Rule": {"Id": "E3002"}, "Level": "Error", "Message": "second error"},
            ]
        )

        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")

        self.assertEqual(len(report.findings), 3)
        self.assertEqual(
            [f.message for f in report.findings], ["first error", "first warning", "second error"]
        )

    # ------------------------------------------------------------------
    # 2. Error diagnostic
    # ------------------------------------------------------------------
    def test_error_diagnostic_maps_to_failed_high(self) -> None:
        payload = _diagnostics_payload([{"Rule": {"Id": "E3001"}, "Level": "Error", "Message": "bad config"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.FAILED)
        self.assertEqual(finding.severity, ValidationSeverity.HIGH)
        self.assertEqual(finding.tool, "cfn-lint")
        self.assertEqual(finding.provider, "AWS CloudFormation")

    # ------------------------------------------------------------------
    # 3. Warning diagnostic
    # ------------------------------------------------------------------
    def test_warning_diagnostic_maps_to_warning_low(self) -> None:
        payload = _diagnostics_payload([{"Rule": {"Id": "W2001"}, "Level": "Warning", "Message": "minor issue"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.WARNING)
        self.assertEqual(finding.severity, ValidationSeverity.LOW)

    def test_informational_diagnostic_maps_to_warning_info(self) -> None:
        payload = _diagnostics_payload([{"Level": "Informational", "Message": "fyi"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("template.yaml")

        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.WARNING)
        self.assertEqual(finding.severity, ValidationSeverity.INFO)

    def test_informational_shorthand_info_is_also_recognized(self) -> None:
        payload = _diagnostics_payload([{"Level": "Info", "Message": "fyi shorthand"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].severity, ValidationSeverity.INFO)

    # ------------------------------------------------------------------
    # 4. Rule ID extraction
    # ------------------------------------------------------------------
    def test_rule_id_extracted_from_nested_rule_object(self) -> None:
        payload = _diagnostics_payload([{"Rule": {"Id": "E3001"}, "Level": "Error", "Message": "x"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].rule_id, "E3001")

    def test_rule_id_falls_back_to_flat_rule_id_key(self) -> None:
        payload = _diagnostics_payload([{"RuleId": "E9999", "Level": "Error", "Message": "x"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].rule_id, "E9999")

    def test_rule_id_missing_entirely_is_none(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "no rule id at all"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertIsNone(report.findings[0].rule_id)

    # ------------------------------------------------------------------
    # 5. Message extraction
    # ------------------------------------------------------------------
    def test_message_extracted_verbatim(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "Additional properties are not allowed"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].message, "Additional properties are not allowed")

    # ------------------------------------------------------------------
    # 6. File path extraction
    # ------------------------------------------------------------------
    def test_file_path_extracted_from_filename_field(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "x", "Filename": "template.yaml"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].file_path, "template.yaml")

    def test_missing_filename_yields_none_file_path(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "x"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertIsNone(report.findings[0].file_path)

    # ------------------------------------------------------------------
    # 7. Line extraction
    # ------------------------------------------------------------------
    def test_line_extracted_from_location_start(self) -> None:
        payload = _diagnostics_payload(
            [{"Level": "Error", "Message": "x", "Location": {"Start": {"LineNumber": 42}}}]
        )
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].line, 42)

    def test_missing_location_yields_none_line_and_column(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "x"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        finding = report.findings[0]
        self.assertIsNone(finding.line)
        self.assertIsNone(finding.column)

    def test_non_positive_line_number_yields_none(self) -> None:
        payload = _diagnostics_payload(
            [{"Level": "Error", "Message": "x", "Location": {"Start": {"LineNumber": 0}}}]
        )
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertIsNone(report.findings[0].line)

    # ------------------------------------------------------------------
    # 8. Column extraction
    # ------------------------------------------------------------------
    def test_column_extracted_from_location_start(self) -> None:
        payload = _diagnostics_payload(
            [{"Level": "Error", "Message": "x", "Location": {"Start": {"LineNumber": 10, "ColumnNumber": 7}}}]
        )
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        self.assertEqual(report.findings[0].column, 7)

    # ------------------------------------------------------------------
    # 9. Severity mapping (unrecognized level)
    # ------------------------------------------------------------------
    def test_unrecognized_level_maps_to_error_medium(self) -> None:
        payload = _diagnostics_payload([{"Level": "Critical", "Message": "unrecognized level"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.ERROR)
        self.assertEqual(finding.severity, ValidationSeverity.MEDIUM)

    def test_missing_level_maps_to_error_medium(self) -> None:
        payload = _diagnostics_payload([{"Message": "no level given"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.ERROR)
        self.assertEqual(finding.severity, ValidationSeverity.MEDIUM)

    # ------------------------------------------------------------------
    # 10. Missing optional fields (all at once) still produces a valid finding
    # ------------------------------------------------------------------
    def test_diagnostic_with_only_message_is_handled_normally(self) -> None:
        payload = _diagnostics_payload([{"Message": "bare minimum diagnostic"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")

        finding = report.findings[0]
        self.assertEqual(finding.message, "bare minimum diagnostic")
        self.assertIsNone(finding.rule_id)
        self.assertIsNone(finding.file_path)
        self.assertIsNone(finding.line)
        self.assertIsNone(finding.column)

    # ------------------------------------------------------------------
    # 11. Non-zero return code with valid JSON: no exception
    # ------------------------------------------------------------------
    def test_nonzero_returncode_with_valid_diagnostics_does_not_raise(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "bad config"}])

        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            try:
                report = self.adapter.validate("template.yaml")
            except CfnLintAdapterError:
                self.fail("validate() raised CfnLintAdapterError for an ordinary cfn-lint failure")

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].status, ValidationStatus.FAILED)

    # ------------------------------------------------------------------
    # 12. Invalid JSON
    # ------------------------------------------------------------------
    def test_invalid_json_raises_adapter_error(self) -> None:
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout="[not valid json")):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    # ------------------------------------------------------------------
    # 13 / 14. Empty stdout, and stderr included in the error
    # ------------------------------------------------------------------
    def test_empty_stdout_raises_adapter_error(self) -> None:
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout="", stderr="", returncode=1)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    def test_empty_stdout_error_message_includes_stderr(self) -> None:
        with patch.object(
            cla.subprocess, "run", return_value=_completed_process(stdout="", stderr="fatal: crashed", returncode=1)
        ):
            with self.assertRaises(CfnLintAdapterError) as ctx:
                self.adapter.validate("template.yaml")
        self.assertIn("fatal: crashed", str(ctx.exception))

    # ------------------------------------------------------------------
    # 15. Executable not found
    # ------------------------------------------------------------------
    def test_executable_not_found_raises_adapter_error(self) -> None:
        with patch.object(cla.subprocess, "run", side_effect=FileNotFoundError("no such file")):
            with self.assertRaises(CfnLintAdapterError) as ctx:
                self.adapter.validate("template.yaml")
        self.assertIn("not found", str(ctx.exception))

    # ------------------------------------------------------------------
    # 16. Timeout
    # ------------------------------------------------------------------
    def test_timeout_raises_adapter_error(self) -> None:
        timeout_error = subprocess.TimeoutExpired(cmd=["cfn-lint"], timeout=60.0)
        with patch.object(cla.subprocess, "run", side_effect=timeout_error):
            with self.assertRaises(CfnLintAdapterError) as ctx:
                self.adapter.validate("template.yaml")
        self.assertIn("timed out", str(ctx.exception))

    # ------------------------------------------------------------------
    # 17. Malformed top-level JSON (not an array)
    # ------------------------------------------------------------------
    def test_malformed_top_level_object_raises_adapter_error(self) -> None:
        payload = json.dumps({"not": "an array"})
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    def test_malformed_top_level_scalar_raises_adapter_error(self) -> None:
        payload = json.dumps("just a string")
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    # ------------------------------------------------------------------
    # 18. Malformed individual diagnostic
    # ------------------------------------------------------------------
    def test_malformed_individual_diagnostic_raises_adapter_error(self) -> None:
        payload = _diagnostics_payload(["not-a-dict", {"Level": "Error", "Message": "real one"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    def test_diagnostic_with_no_message_raises_adapter_error(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error"}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    def test_diagnostic_with_blank_message_raises_adapter_error(self) -> None:
        payload = _diagnostics_payload([{"Level": "Error", "Message": "   "}])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            with self.assertRaises(CfnLintAdapterError):
                self.adapter.validate("template.yaml")

    # ------------------------------------------------------------------
    # 19. Empty diagnostics -> synthetic PASSED finding
    # ------------------------------------------------------------------
    def test_empty_diagnostics_produce_synthetic_passed_finding(self) -> None:
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("template.yaml")

        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, ValidationStatus.PASSED)
        self.assertEqual(finding.severity, ValidationSeverity.NONE)
        self.assertEqual(finding.rule_id, "CFN_LINT_NO_ISSUES")

    # ------------------------------------------------------------------
    # 20. shell=True is never used
    # ------------------------------------------------------------------
    def test_shell_is_never_true(self) -> None:
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("template.yaml")

        _, kwargs = mock_run.call_args
        self.assertIsNot(kwargs.get("shell"), True)

    # ------------------------------------------------------------------
    # 21. timeout is passed to subprocess
    # ------------------------------------------------------------------
    def test_timeout_is_passed_to_subprocess(self) -> None:
        adapter = CfnLintAdapter(timeout_seconds=30.0)
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("template.yaml")

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 30.0)

    # ------------------------------------------------------------------
    # 22. Template path passed correctly
    # ------------------------------------------------------------------
    def test_template_path_is_passed_correctly(self) -> None:
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            self.adapter.validate("path/to/template.yaml")

        args, kwargs = mock_run.call_args
        command = args[0]
        self.assertEqual(command[:3], ["cfn-lint", "--format", "json"])
        self.assertEqual(Path(command[3]), Path("path/to/template.yaml"))
        self.assertNotIn("cwd", kwargs)

    # ------------------------------------------------------------------
    # 23. Custom executable is respected
    # ------------------------------------------------------------------
    def test_custom_executable_is_used(self) -> None:
        adapter = CfnLintAdapter(cfn_lint_executable="/opt/bin/cfn-lint")
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)) as mock_run:
            adapter.validate("template.yaml")

        args, _ = mock_run.call_args
        self.assertEqual(args[0][0], "/opt/bin/cfn-lint")

    # ------------------------------------------------------------------
    # 24. Final result is a ValidationReport
    # ------------------------------------------------------------------
    def test_return_type_is_validation_report(self) -> None:
        payload = _diagnostics_payload([])
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload)):
            report = self.adapter.validate("template.yaml")
        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.provider, "AWS CloudFormation")

    # ------------------------------------------------------------------
    # 25. Summary counts match findings
    # ------------------------------------------------------------------
    def test_report_summary_matches_findings(self) -> None:
        payload = _diagnostics_payload(
            [
                {"Level": "Error", "Message": "e1"},
                {"Level": "Error", "Message": "e2"},
                {"Level": "Warning", "Message": "w1"},
                {"Level": "Informational", "Message": "i1"},
            ]
        )
        with patch.object(cla.subprocess, "run", return_value=_completed_process(stdout=payload, returncode=2)):
            report = self.adapter.validate("template.yaml")

        summary = report.validation_summary
        self.assertEqual(summary.total_checks, len(report.findings))
        self.assertEqual(summary.failed, sum(1 for f in report.findings if f.status == ValidationStatus.FAILED))
        self.assertEqual(summary.warnings, sum(1 for f in report.findings if f.status == ValidationStatus.WARNING))

    # ------------------------------------------------------------------
    # 26. Package-mode execution compatibility is exercised implicitly by
    # every test above via the try/except relative-import pattern; this
    # test additionally confirms the module's own import fallback logic
    # is present and consistent with the other adapters.
    # ------------------------------------------------------------------
    def test_module_exposes_expected_public_api(self) -> None:
        self.assertTrue(hasattr(cla, "CfnLintAdapter"))
        self.assertTrue(hasattr(cla, "CfnLintAdapterError"))
        self.assertEqual(sorted(cla.__all__), ["CfnLintAdapter", "CfnLintAdapterError"])

    # ------------------------------------------------------------------
    # Constructor validation (bonus coverage, not in the numbered list)
    # ------------------------------------------------------------------
    def test_constructor_rejects_empty_executable(self) -> None:
        with self.assertRaises(CfnLintAdapterError):
            CfnLintAdapter(cfn_lint_executable="")

    def test_constructor_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(CfnLintAdapterError):
            CfnLintAdapter(timeout_seconds=0)


def run_all_tests() -> int:
    """Run every test in this module and return a process-suitable exit code.

    Returns:
        `0` if every test passed, `1` otherwise.
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(CfnLintAdapterTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
