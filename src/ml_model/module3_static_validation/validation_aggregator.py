"""validation_aggregator.py.

Combines already-normalized `ValidationReport` objects — produced by
the Module 3 tool adapters (Terraform Validate, Checkov, TFLint,
CFN-Lint) — into a single, unified `ValidationReport`.

    Terraform Validate adapter --\\
    Checkov adapter            ---+--> ValidationReport(s) -> validation_aggregator.py -> ValidationReport
    TFLint adapter             --/
    CFN-Lint adapter          -/

This module owns no tool-specific parsing and defines no new schema
fields. It operates exclusively on already-constructed
`ValidationReport` objects: it concatenates their findings (preserving
report order and finding order, and discarding nothing), determines
the aggregated report's `provider` (the shared provider if every input
report agrees, or `"MULTI_PROVIDER"` if they differ), and delegates to
`validation_result.py`'s existing helpers (`combine_findings()`,
`summary_from_findings()`, `build_report()`) to recompute the summary
and construct the final report. Any `ValidationResultError` raised by
that layer is caught and re-raised as `ValidationAggregatorError`, so
callers of this module only ever need to handle one exception type —
matching the same wrapping pattern `validation_result.py` itself uses
around `validation_schema.ValidationSchemaError`.

Requirements:
    - Python 3.12

Typical usage:
    from validation_aggregator import ValidationAggregator

    aggregator = ValidationAggregator()
    combined_report = aggregator.aggregate(
        [terraform_report, checkov_report, tflint_report]
    )
"""

from __future__ import annotations

import logging
from typing import Iterable

# Relative imports are used since this module lives inside the
# `module3_static_validation` package alongside `validation_result.py`.
# A fallback to absolute (flat) imports is provided so this module also
# runs correctly when executed or imported directly without package
# context, matching the same pattern used by the other Module 3
# adapters (e.g. `tflint_adapter.py`, `checkov_adapter.py`).
try:
    from .validation_result import (
        ValidationResultError,
        build_report,
        combine_findings,
    )
    from .validation_schema import ValidationReport
except ImportError:
    from validation_result import (  # type: ignore[no-redef]
        ValidationResultError,
        build_report,
        combine_findings,
    )
    from validation_schema import ValidationReport  # type: ignore[no-redef]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class ValidationAggregatorError(Exception):
    """Raised when multiple `ValidationReport` objects cannot be aggregated.

    Every failure this module can encounter — a report that is not a
    `ValidationReport`, an empty input collection, or a
    `ValidationResultError` raised while recomputing the combined
    summary/report — is normalized into this single exception type.
    """


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
class ValidationAggregator:
    """Combines multiple `ValidationReport` objects into one.

    This is a report-level aggregation step: it takes the already-built
    `ValidationReport` output of the individual Module 3 tool adapters
    (Terraform Validate, Checkov, TFLint, CFN-Lint) and merges them into
    a single `ValidationReport` whose findings are the union of every
    input report's findings, and whose summary is recomputed from that
    complete, combined collection.
    """

    MULTI_PROVIDER = "MULTI_PROVIDER"

    def aggregate(self, reports: Iterable[ValidationReport]) -> ValidationReport:
        """Aggregate multiple `ValidationReport` objects into one.

        Every finding from every report is preserved — none are
        discarded or deduplicated — and both report order and each
        report's internal finding order are preserved in the combined
        report.

        Args:
            reports: The `ValidationReport` objects to combine, e.g.
                the output of the Terraform Validate, Checkov, TFLint,
                and CFN-Lint adapters. May be any iterable, including a
                one-shot generator.

        Returns:
            A new `ValidationReport` containing every finding from
            every input report, in order, with its `provider` set to
            the shared provider if all input reports agree, or
            `"MULTI_PROVIDER"` otherwise, and its `validation_summary`
            recomputed from the complete combined finding collection.

        Raises:
            ValidationAggregatorError: If `reports` is not iterable, if
                any element of `reports` is not a `ValidationReport`,
                if `reports` is empty, or if the underlying
                `validation_result` layer rejects the combined data.
        """
        try:
            report_list = list(reports)
        except TypeError as exc:
            logger.error("ValidationAggregator: reports is not iterable: %r", reports)
            raise ValidationAggregatorError(
                f"reports must be an iterable of ValidationReport, got {reports!r}"
            ) from exc

        for index, report in enumerate(report_list):
            if not isinstance(report, ValidationReport):
                logger.error(
                    "ValidationAggregator: reports[%d] must be a ValidationReport, got %s",
                    index,
                    type(report).__name__,
                )
                raise ValidationAggregatorError(
                    f"reports[{index}] must be a ValidationReport, got "
                    f"{type(report).__name__}"
                )

        if not report_list:
            logger.error("ValidationAggregator: no reports were provided to aggregate.")
            raise ValidationAggregatorError(
                "Cannot aggregate an empty collection of reports: a ValidationReport "
                "requires a non-empty 'provider', so no aggregated report can be "
                "constructed without at least one input report."
            )

        provider = self._determine_provider(report_list)

        try:
            combined_findings = combine_findings(
                *(report.findings for report in report_list)
            )
            return build_report(provider=provider, findings=combined_findings)
        except ValidationResultError as exc:
            logger.error("ValidationAggregator: failed to build aggregated report: %s", exc)
            raise ValidationAggregatorError(
                f"Failed to build aggregated validation report: {exc}"
            ) from exc

    def _determine_provider(self, reports: list[ValidationReport]) -> str:
        """Determine the aggregated report's provider.

        Args:
            reports: The (already-validated, non-empty) list of input
                reports.

        Returns:
            The shared provider if every report in `reports` has the
            same provider, or `self.MULTI_PROVIDER` if two or more
            distinct providers are present.
        """
        providers = {report.provider for report in reports}

        if len(providers) == 1:
            return next(iter(providers))

        logger.info(
            "ValidationAggregator: reports span %d distinct providers %s; using '%s'.",
            len(providers),
            sorted(providers),
            self.MULTI_PROVIDER,
        )
        return self.MULTI_PROVIDER


__all__ = [
    "ValidationAggregator",
    "ValidationAggregatorError",
]
