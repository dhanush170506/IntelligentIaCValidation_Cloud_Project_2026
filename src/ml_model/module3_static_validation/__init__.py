"""module3_static_validation.

Module 3 of the Telemetry-Aware Multi-Agent Infrastructure-as-Code
Assurance System for Smart Manufacturing Cloud Environments.

This package implements the Static Validation Engine: a provider- and
tool-independent layer that runs external IaC validation/security
tools (Terraform Validate, Checkov, TFLint, CFN-Lint) against the
Unified Intermediate Representation (UIR) produced by Module 2, and
aggregates their results into one standardized internal
representation. No native tool output format is exposed beyond this
package's boundary.

Currently implemented:
    - validation_schema: the standardized internal validation result
      schema (`ValidationFinding`, `ValidationSummary`,
      `ValidationReport`) that every tool adapter and the result
      aggregator build on.
"""
