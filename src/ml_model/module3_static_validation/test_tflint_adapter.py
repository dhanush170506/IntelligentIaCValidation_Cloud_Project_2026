"""
Tests for the TFLint validation adapter.
"""

from pathlib import Path
from unittest.mock import Mock, patch

try:
    from .tflint_adapter import TFLintAdapter, TFLintAdapterError
    from .validation_schema import (
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )
except ImportError:
    from tflint_adapter import TFLintAdapter, TFLintAdapterError
    from validation_schema import (
        ValidationReport,
        ValidationSeverity,
        ValidationStatus,
    )


def completed_process(stdout="", stderr="", returncode=0):
    """Create a mock CompletedProcess-like object."""
    return Mock(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def diagnostic_payload(
    rule_name="terraform_required_providers",
    severity="error",
    message="Missing required provider configuration.",
    filename="main.tf",
    line=10,
    column=5,
):
    """Create a representative TFLint diagnostic."""
    return [
        {
            "rule_name": rule_name,
            "severity": severity,
            "message": message,
            "range": {
                "filename": filename,
                "start": {
                    "line": line,
                    "column": column,
                },
                "end": {
                    "line": line,
                    "column": column + 5,
                },
            },
        }
    ]


class TestTFLintAdapter:
    """Unit tests for TFLintAdapter."""

    def test_error_diagnostic(self):
        import json

        output = json.dumps(
            diagnostic_payload(
                severity="error",
                message="Provider configuration is invalid.",
            )
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(
                stdout=output,
                returncode=2,
            ),
        ):
            report = TFLintAdapter().validate("main.tf")

        self.assert_report(report)

        finding = report.findings[0]

        assert finding.tool == "tflint"
        assert finding.provider == "Terraform"
        assert finding.status == ValidationStatus.FAILED
        assert finding.severity == ValidationSeverity.HIGH
        assert finding.rule_id == "terraform_required_providers"
        assert finding.message == "Provider configuration is invalid."
        assert finding.file_path == "main.tf"
        assert finding.line == 10
        assert finding.column == 5

    def test_warning_diagnostic(self):
        import json

        output = json.dumps(
            diagnostic_payload(
                severity="warning",
                message="Variable could be simplified.",
            )
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        finding = report.findings[0]

        assert finding.status == ValidationStatus.WARNING
        assert finding.severity == ValidationSeverity.LOW

    def test_notice_diagnostic(self):
        import json

        output = json.dumps(
            diagnostic_payload(severity="notice")
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        finding = report.findings[0]

        assert finding.status == ValidationStatus.WARNING
        assert finding.severity == ValidationSeverity.INFO

    def test_info_diagnostic(self):
        import json

        output = json.dumps(
            diagnostic_payload(severity="info")
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        finding = report.findings[0]

        assert finding.status == ValidationStatus.WARNING
        assert finding.severity == ValidationSeverity.INFO

    def test_unknown_severity(self):
        import json

        output = json.dumps(
            diagnostic_payload(severity="something-unknown")
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        finding = report.findings[0]

        assert finding.status == ValidationStatus.ERROR
        assert finding.severity == ValidationSeverity.MEDIUM

    def test_empty_diagnostics_creates_synthetic_finding(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        assert len(report.findings) == 1

        finding = report.findings[0]

        assert finding.tool == "tflint"
        assert finding.provider == "Terraform"
        assert finding.status == ValidationStatus.PASSED
        assert finding.severity == ValidationSeverity.NONE
        assert finding.rule_id == "TFLINT_NO_ISSUES"
        assert finding.message == "TFLint reported no issues."

    def test_multiple_diagnostics(self):
        import json

        diagnostics = [
            diagnostic_payload(
                rule_name="rule_one",
                severity="error",
            )[0],
            diagnostic_payload(
                rule_name="rule_two",
                severity="warning",
            )[0],
        ]

        with patch(
            "subprocess.run",
            return_value=completed_process(
                stdout=json.dumps(diagnostics)
            ),
        ):
            report = TFLintAdapter().validate("main.tf")

        assert len(report.findings) == 2
        assert report.findings[0].rule_id == "rule_one"
        assert report.findings[1].rule_id == "rule_two"

    def test_missing_optional_fields(self):
        import json

        output = json.dumps(
            [
                {
                    "message": "Something is wrong."
                }
            ]
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        finding = report.findings[0]

        assert finding.message == "Something is wrong."
        assert finding.rule_id is None
        assert finding.file_path is None
        assert finding.line is None
        assert finding.column is None

    def test_missing_message_raises(self):
        import json

        output = json.dumps(
            [
                {
                    "rule_name": "some_rule",
                    "severity": "error",
                }
            ]
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_blank_message_raises(self):
        import json

        output = json.dumps(
            [
                {
                    "message": "   ",
                }
            ]
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_malformed_diagnostic_raises(self):
        import json

        output = json.dumps(
            [
                "not-an-object"
            ]
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_top_level_object_raises(self):
        import json

        output = json.dumps({"diagnostics": []})

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_invalid_json_raises(self):
        with patch(
            "subprocess.run",
            return_value=completed_process(
                stdout="{invalid json"
            ),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_empty_stdout_raises(self):
        with patch(
            "subprocess.run",
            return_value=completed_process(
                stdout="",
                stderr="TFLint failed.",
                returncode=1,
            ),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_executable_not_found(self):
        with patch(
            "subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_timeout(self):
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["tflint"],
                timeout=120,
            ),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_os_error(self):
        with patch(
            "subprocess.run",
            side_effect=OSError("execution failed"),
        ):
            try:
                TFLintAdapter().validate("main.tf")
                assert False, "Expected TFLintAdapterError"
            except TFLintAdapterError:
                pass

    def test_nonzero_exit_with_valid_json_is_accepted(self):
        import json

        output = json.dumps(
            diagnostic_payload(severity="error")
        )

        with patch(
            "subprocess.run",
            return_value=completed_process(
                stdout=output,
                stderr="TFLint found problems.",
                returncode=2,
            ),
        ):
            report = TFLintAdapter().validate("main.tf")

        assert len(report.findings) == 1
        assert report.findings[0].status == ValidationStatus.FAILED

    def test_command_construction(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ) as mock_run:
            TFLintAdapter().validate(
                Path("path/to/main.tf")
            )

        command = mock_run.call_args.args[0]

        assert command[:3] == [
            "tflint",
            "--format",
            "json",
        ]
        assert Path(command[3]) == Path(
            "path/to/main.tf"
        )

    def test_no_shell_true(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ) as mock_run:
            TFLintAdapter().validate("main.tf")

        kwargs = mock_run.call_args.kwargs

        assert kwargs.get("shell") is not True

    def test_timeout_is_passed(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ) as mock_run:
            TFLintAdapter(timeout_seconds=45).validate(
                "main.tf"
            )

        assert mock_run.call_args.kwargs["timeout"] == 45

    def test_custom_executable(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ) as mock_run:
            TFLintAdapter(
                tflint_executable="C:\\tools\\tflint.exe"
            ).validate("main.tf")

        command = mock_run.call_args.args[0]

        assert command[0] == "C:\\tools\\tflint.exe"

    def test_constructor_rejects_empty_executable(self):
        try:
            TFLintAdapter(tflint_executable="")
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_constructor_rejects_nonpositive_timeout(self):
        try:
            TFLintAdapter(timeout_seconds=0)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_report_type_and_provider(self):
        import json

        output = json.dumps([])

        with patch(
            "subprocess.run",
            return_value=completed_process(stdout=output),
        ):
            report = TFLintAdapter().validate("main.tf")

        self.assert_report(report)
        assert report.provider == "Terraform"

    @staticmethod
    def assert_report(report):
        assert isinstance(report, ValidationReport)


def run_tests():
    """Simple test runner compatible with the existing project style."""

    test_class = TestTFLintAdapter()
    tests = [
        name
        for name in dir(test_class)
        if name.startswith("test_")
    ]

    passed = 0

    for name in tests:
        getattr(test_class, name)()
        passed += 1

    print(f"All {passed} TFLint adapter tests PASSED.")


if __name__ == "__main__":
    run_tests()