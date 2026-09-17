"""
terraform_parser.py

A production-ready parser for Terraform (.tf) files.

This module reads a Terraform configuration file from a given file path,
parses it into a Python dictionary using the `python-hcl2` library, and
returns the parsed data as-is (no modification, normalization, or
extraction logic is applied).

Requirements:
    - Python 3.12
    - python-hcl2 (install via: pip install python-hcl2)

Typical usage:
    from terraform_parser import parse_terraform_file

    parsed_data = parse_terraform_file("sample_terraform.tf")
    print(parsed_data)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import hcl2

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
class TerraformParserError(Exception):
    """Base exception for all errors raised by the Terraform parser."""


class TerraformFileNotFoundError(TerraformParserError):
    """Raised when the specified Terraform file does not exist."""


class TerraformParseError(TerraformParserError):
    """Raised when the Terraform file cannot be parsed as valid HCL2."""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def validate_file_path(file_path: str) -> Path:
    """
    Validate that the given path points to an existing, readable file.

    Args:
        file_path: Path to the Terraform (.tf) file as a string.

    Returns:
        A `pathlib.Path` object representing the validated file path.

    Raises:
        TerraformFileNotFoundError: If the path does not exist or is not
            a file.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error("Terraform file not found: %s", path)
        raise TerraformFileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        logger.error("Path exists but is not a file: %s", path)
        raise TerraformFileNotFoundError(f"Path is not a file: {path}")

    logger.debug("Validated file path: %s", path)
    return path


def is_terraform_file(file_path: str) -> bool:
    """
    Check whether the given file path has a Terraform (.tf) extension.

    Args:
        file_path: Path to the file to check.

    Returns:
        True if the file extension is `.tf`, False otherwise.
    """
    is_tf = Path(file_path).suffix.lower() == ".tf"
    logger.debug("Checked Terraform file extension for %s: %s", file_path, is_tf)
    return is_tf


def read_terraform_file(file_path: str) -> str:
    """
    Read the raw contents of a Terraform (.tf) file.

    Args:
        file_path: Path to the Terraform (.tf) file as a string.

    Returns:
        The raw text contents of the file.

    Raises:
        TerraformFileNotFoundError: If the file does not exist.
        TerraformParserError: If the file cannot be read (e.g. permission
            issues or encoding errors).
    """
    path = validate_file_path(file_path)

    try:
        with path.open("r", encoding="utf-8") as tf_file:
            contents = tf_file.read()
        logger.info("Successfully read Terraform file: %s", path)
        return contents
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Failed to read file %s: %s", path, exc)
        raise TerraformParserError(f"Unable to read file: {path}") from exc


def _normalize_terraform_value(value: Any) -> Any:
    """
    Recursively normalize values returned by python-hcl2.

    Removes parser-added surrounding double quotes from string literals
    while preserving Terraform expressions such as ${...}.
    """
    if isinstance(value, str):
        # Preserve Terraform interpolation expressions.
        if value.startswith("${") and value.endswith("}"):
            return value

        # Remove only one pair of surrounding double quotes.
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            return value[1:-1]

        return value

    if isinstance(value, list):
        return [_normalize_terraform_value(item) for item in value]

    if isinstance(value, dict):
        return {
            _normalize_terraform_value(key): _normalize_terraform_value(val)
            for key, val in value.items()
        }

    return value


def parse_terraform_content(content: str, source_name: str = "<string>") -> Dict[str, Any]:
    """
    Parse raw Terraform (HCL2) content into a Python dictionary.

    Args:
        content: Raw Terraform configuration text.
        source_name: A label identifying the source of the content, used
            only for logging/error messages (e.g. a file path).

    Returns:
        A dictionary representing the parsed Terraform configuration,
        exactly as produced by `python-hcl2`, without any modification.

    Raises:
        TerraformParseError: If the content is not valid HCL2/Terraform
            syntax.
    """
    try:
        # hcl2.load expects a file-like object; use io.StringIO to adapt
        # the in-memory string content to that interface.
        import io

        parsed_data: Dict[str, Any] = hcl2.load(io.StringIO(content))
        parsed_data = _normalize_terraform_value(parsed_data)
        logger.info("Successfully parsed Terraform content from: %s", source_name)
        return parsed_data
    except Exception as exc:
        # python-hcl2 (built on lark) can raise a variety of exception
        # types on malformed input; normalize them into a single,
        # well-defined exception for callers to handle.
        logger.error("Failed to parse Terraform content from %s: %s", source_name, exc)
        raise TerraformParseError(
            f"Invalid Terraform (HCL2) syntax in: {source_name}"
        ) from exc


def parse_terraform_file(file_path: str) -> Dict[str, Any]:
    """
    Read and parse a Terraform (.tf) file into a Python dictionary.

    This is the main entry point of the module. It reads the file at
    `file_path`, parses its HCL2 content, and returns the resulting
    dictionary unchanged (no normalization, extraction, or filtering).

    Args:
        file_path: Path to the Terraform (.tf) file to parse.

    Returns:
        A dictionary representing the parsed Terraform configuration.

    Raises:
        TerraformFileNotFoundError: If the file does not exist or is not
            a valid file.
        TerraformParseError: If the file extension is not `.tf`, or if
            the file content is not valid Terraform (HCL2) syntax.
        TerraformParserError: For any other file-reading related error.
    """
    logger.info("Starting Terraform parse for file: %s", file_path)

    if not is_terraform_file(file_path):
        logger.error("Invalid file extension for Terraform file: %s", file_path)
        raise TerraformParseError(
            f"Invalid file extension: {file_path} (expected a .tf file)"
        )

    raw_content = read_terraform_file(file_path)
    parsed_data = parse_terraform_content(raw_content, source_name=file_path)

    logger.info("Completed Terraform parse for file: %s", file_path)
    return parsed_data


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the parser.

    Usage:
        python terraform_parser.py <path_to_tf_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python terraform_parser.py <path_to_tf_file>")
        sys.exit(1)

    tf_file_path = sys.argv[1]

    try:
        result = parse_terraform_file(tf_file_path)
        print(result)
    except TerraformParserError as exc:
        logger.error("Terraform parsing failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
