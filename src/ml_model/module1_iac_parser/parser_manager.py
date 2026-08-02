"""
parser_manager.py

The single public entry point for Module 1 (Infrastructure-as-Code
parsing and normalization).

This module orchestrates the existing Terraform/CloudFormation parsers,
the resource extractor, the dependency extractor, and the JSON
normalizer into one end-to-end workflow. It contains no parsing,
extraction, or normalization logic of its own — it only detects the
input file's IaC provider and delegates each pipeline stage to the
appropriate existing module, in order.

Requirements:
    - Python 3.12

Typical usage:
    from parser_manager import process_iac_file

    normalized = process_iac_file("sample_terraform.tf")
    print(normalized)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from cloudformation_parser import (
    CloudFormationParserError,
    parse_cloudformation_file,
)
from dependency_extractor import DependencyExtractorError, extract_dependencies
from json_normalizer import (
    JSONNormalizerError,
    normalize_json,
    validate_normalized_json,
)
from resource_extractor import ResourceExtractorError, extract_resources
from terraform_parser import TerraformParserError, parse_terraform_file

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
class ParserManagerError(Exception):
    """Base exception for all errors raised by the Parser Manager."""


# ---------------------------------------------------------------------------
# Provider labels and supported extensions
# ---------------------------------------------------------------------------
_PROVIDER_TERRAFORM = "Terraform"
_PROVIDER_CLOUDFORMATION = "CloudFormation"

_TERRAFORM_EXTENSIONS = (".tf",)
_CLOUDFORMATION_EXTENSIONS = (".yaml", ".yml", ".json")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def detect_provider(file_path: str) -> str:
    """
    Detect which IaC provider a file belongs to, based on its
    extension.

    Args:
        file_path: Path to the IaC file to inspect.

    Returns:
        Either "Terraform" or "CloudFormation".

    Raises:
        ParserManagerError: If the file extension does not match any
            supported provider.
    """
    extension = Path(file_path).suffix.lower()

    if extension in _TERRAFORM_EXTENSIONS:
        logger.debug("Detected provider 'Terraform' for file: %s", file_path)
        return _PROVIDER_TERRAFORM

    if extension in _CLOUDFORMATION_EXTENSIONS:
        logger.debug("Detected provider 'CloudFormation' for file: %s", file_path)
        return _PROVIDER_CLOUDFORMATION

    logger.error("Unable to detect provider for file: %s", file_path)
    raise ParserManagerError(
        f"Unsupported file extension: {extension} (expected .tf, .yaml, "
        f".yml, or .json)"
    )


def _parse_iac_file(file_path: str, provider: str) -> Dict[str, Any]:
    """
    Parse an IaC file using the parser appropriate for its provider.

    Args:
        file_path: Path to the IaC file to parse.
        provider: The detected provider ("Terraform" or
            "CloudFormation").

    Returns:
        The parsed configuration dictionary, exactly as returned by the
        underlying provider-specific parser.

    Raises:
        ParserManagerError: If parsing fails for the detected provider.
    """
    try:
        if provider == _PROVIDER_TERRAFORM:
            return parse_terraform_file(file_path)
        return parse_cloudformation_file(file_path)
    except (TerraformParserError, CloudFormationParserError) as exc:
        logger.error("Parsing failed for file %s: %s", file_path, exc)
        raise ParserManagerError(f"Parsing failed for file: {file_path}") from exc


def process_iac_file(file_path: str) -> Dict[str, Any]:
    """
    Run the full Infrastructure-as-Code processing pipeline on a single
    file and return the final normalized JSON object.

    This is the sole public entry point for Module 1. It performs, in
    order:
        1. Provider detection (`detect_provider`).
        2. Parsing, via `terraform_parser.py` or
           `cloudformation_parser.py`.
        3. Resource extraction, via `resource_extractor.py`.
        4. Dependency extraction, via `dependency_extractor.py`.
        5. JSON normalization and schema validation, via
           `json_normalizer.py`.

    Args:
        file_path: Path to the Terraform (.tf) or CloudFormation
            (.yaml, .yml, .json) file to process.

    Returns:
        The normalized JSON object produced by
        `json_normalizer.normalize_json()`, with the shape:
            {
                "provider": "...",
                "metadata": {
                    "resource_count": ...,
                    "dependency_count": ...
                },
                "resources": [...],
                "dependencies": [...]
            }

    Raises:
        ParserManagerError: If provider detection, parsing, resource
            extraction, dependency extraction, or JSON normalization
            fails at any stage of the pipeline.
    """
    logger.info("Starting IaC processing pipeline for file: %s", file_path)

    provider = detect_provider(file_path)
    parsed_data = _parse_iac_file(file_path, provider)

    try:
        resources = extract_resources(parsed_data, provider=provider)
    except ResourceExtractorError as exc:
        logger.error("Resource extraction failed for file %s: %s", file_path, exc)
        raise ParserManagerError(f"Resource extraction failed for file: {file_path}") from exc

    try:
        dependencies = extract_dependencies(parsed_data, provider=provider)
    except DependencyExtractorError as exc:
        logger.error("Dependency extraction failed for file %s: %s", file_path, exc)
        raise ParserManagerError(
            f"Dependency extraction failed for file: {file_path}"
        ) from exc

    try:
        normalized_data = normalize_json(
            provider=provider, resources=resources, dependencies=dependencies
        )
        validate_normalized_json(normalized_data)
    except JSONNormalizerError as exc:
        logger.error("JSON normalization failed for file %s: %s", file_path, exc)
        raise ParserManagerError(f"JSON normalization failed for file: {file_path}") from exc

    logger.info("Completed IaC processing pipeline for file: %s", file_path)
    return normalized_data


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the Parser
    Manager against a Terraform or CloudFormation file.

    Usage:
        python parser_manager.py <path_to_tf_or_cfn_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python parser_manager.py <path_to_tf_or_cfn_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        result = process_iac_file(file_path)
        print(result)
    except ParserManagerError as exc:
        logger.error("IaC processing pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
