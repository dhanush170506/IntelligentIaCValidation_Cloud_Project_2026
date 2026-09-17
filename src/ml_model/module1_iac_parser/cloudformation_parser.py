"""
cloudformation_parser.py

A production-ready parser for AWS CloudFormation templates.

This module reads a CloudFormation template file (YAML, YML, or JSON)
from a given file path, parses it into a Python dictionary, and returns
the parsed data as-is (no modification, resource extraction, dependency
detection, or normalization is applied).

Requirements:
    - Python 3.12
    - PyYAML (install via: pip install PyYAML)

Typical usage:
    from cloudformation_parser import parse_cloudformation_file

    parsed_data = parse_cloudformation_file("sample_cloudformation.yaml")
    print(parsed_data)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

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
class CloudFormationParserError(Exception):
    """Base exception for all errors raised by the CloudFormation parser."""


class CloudFormationFileNotFoundError(CloudFormationParserError):
    """Raised when the specified CloudFormation file does not exist."""


class CloudFormationParseError(CloudFormationParserError):
    """Raised when the CloudFormation file cannot be parsed as valid
    YAML or JSON, or when the file extension is unsupported."""


# ---------------------------------------------------------------------------
# Supported file extensions
# ---------------------------------------------------------------------------
_SUPPORTED_EXTENSIONS = (".yaml", ".yml", ".json")


# ---------------------------------------------------------------------------
# CloudFormation-aware YAML loader
# ---------------------------------------------------------------------------
class _CloudFormationYamlLoader(yaml.SafeLoader):
    """
    A `yaml.SafeLoader` subclass that understands AWS CloudFormation's
    short-form intrinsic function tags (e.g. `!Ref`, `!GetAtt`, `!Sub`).

    Each recognized tag is converted into a dictionary of the form
    `{"Fn::TagName": value}` (or `{"Ref": value}` for `!Ref`), mirroring
    the long-form JSON/YAML representation. This allows CloudFormation
    templates using short-form syntax to be parsed without raising
    `yaml.constructor.ConstructorError`.
    """


def _make_intrinsic_constructor(tag_suffix: str):
    """
    Build a PyYAML constructor function for a CloudFormation intrinsic
    function tag.

    Args:
        tag_suffix: The intrinsic function name (e.g. "Ref", "GetAtt").

    Returns:
        A constructor function suitable for registration with
        `yaml.SafeLoader.add_constructor`.
    """

    def constructor(loader: yaml.SafeLoader, node: yaml.Node) -> Dict[str, Any]:
        if isinstance(node, yaml.ScalarNode):
            value: Any = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            value = loader.construct_sequence(node)
        elif isinstance(node, yaml.MappingNode):
            value = loader.construct_mapping(node)
        else:
            value = None

        key = "Ref" if tag_suffix == "Ref" else f"Fn::{tag_suffix}"
        return {key: value}

    return constructor


_INTRINSIC_TAGS = (
    "Ref",
    "GetAtt",
    "GetAZs",
    "ImportValue",
    "Join",
    "Sub",
    "Select",
    "Split",
    "FindInMap",
    "Base64",
    "Cidr",
    "Condition",
    "And",
    "Or",
    "Not",
    "Equals",
    "If",
)

for _tag in _INTRINSIC_TAGS:
    _CloudFormationYamlLoader.add_constructor(
        f"!{_tag}", _make_intrinsic_constructor(_tag)
    )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def validate_file_path(file_path: str) -> Path:
    """
    Validate that the given path points to an existing, readable file.

    Args:
        file_path: Path to the CloudFormation template file as a string.

    Returns:
        A `pathlib.Path` object representing the validated file path.

    Raises:
        CloudFormationFileNotFoundError: If the path does not exist or
            is not a file.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error("CloudFormation file not found: %s", path)
        raise CloudFormationFileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        logger.error("Path exists but is not a file: %s", path)
        raise CloudFormationFileNotFoundError(f"Path is not a file: {path}")

    logger.debug("Validated file path: %s", path)
    return path


def is_cloudformation_file(file_path: str) -> bool:
    """
    Check whether the given file path has a supported CloudFormation
    template extension.

    Args:
        file_path: Path to the file to check.

    Returns:
        True if the file extension is `.yaml`, `.yml`, or `.json`,
        False otherwise.
    """
    is_supported = Path(file_path).suffix.lower() in _SUPPORTED_EXTENSIONS
    logger.debug(
        "Checked CloudFormation file extension for %s: %s", file_path, is_supported
    )
    return is_supported


def read_cloudformation_file(file_path: str) -> str:
    """
    Read the raw contents of a CloudFormation template file.

    Args:
        file_path: Path to the CloudFormation template file as a string.

    Returns:
        The raw text contents of the file.

    Raises:
        CloudFormationFileNotFoundError: If the file does not exist.
        CloudFormationParserError: If the file cannot be read (e.g.
            permission issues or encoding errors).
    """
    path = validate_file_path(file_path)

    try:
        with path.open("r", encoding="utf-8") as cfn_file:
            contents = cfn_file.read()
        logger.info("Successfully read CloudFormation file: %s", path)
        return contents
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Failed to read file %s: %s", path, exc)
        raise CloudFormationParserError(f"Unable to read file: {path}") from exc


def parse_cloudformation_content(
    content: str, file_extension: str, source_name: str = "<string>"
) -> Dict[str, Any]:
    """
    Parse raw CloudFormation template content into a Python dictionary.

    Args:
        content: Raw CloudFormation template text (YAML or JSON).
        file_extension: The file extension (e.g. ".yaml", ".yml",
            ".json") used to decide which parser to apply.
        source_name: A label identifying the source of the content, used
            only for logging/error messages (e.g. a file path).

    Returns:
        A dictionary representing the parsed CloudFormation template,
        exactly as produced by the underlying parser, without any
        modification.

    Raises:
        CloudFormationParseError: If the content is not valid YAML or
            JSON, or if the file extension is unsupported.
    """
    extension = file_extension.lower()

    try:
        if extension == ".json":
            parsed_data: Dict[str, Any] = json.loads(content)
        elif extension in (".yaml", ".yml"):
            parsed_data = yaml.load(content, Loader=_CloudFormationYamlLoader)
        else:
            logger.error(
                "Unsupported CloudFormation file extension '%s' for: %s",
                extension,
                source_name,
            )
            raise CloudFormationParseError(
                f"Unsupported file extension: {extension} (expected "
                f".yaml, .yml, or .json)"
            )

        logger.info(
            "Successfully parsed CloudFormation content from: %s", source_name
        )
        return parsed_data
    except CloudFormationParseError:
        raise
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        logger.error(
            "Failed to parse CloudFormation content from %s: %s", source_name, exc
        )
        raise CloudFormationParseError(
            f"Invalid CloudFormation (YAML/JSON) syntax in: {source_name}"
        ) from exc


def parse_cloudformation_file(file_path: str) -> Dict[str, Any]:
    """
    Read and parse a CloudFormation template file into a Python
    dictionary.

    This is the main entry point of the module. It reads the file at
    `file_path`, parses its YAML or JSON content, and returns the
    resulting dictionary unchanged (no normalization, extraction, or
    filtering).

    Args:
        file_path: Path to the CloudFormation template file to parse.

    Returns:
        A dictionary representing the parsed CloudFormation template.

    Raises:
        CloudFormationFileNotFoundError: If the file does not exist or
            is not a valid file.
        CloudFormationParseError: If the file extension is unsupported,
            or if the file content is not valid YAML/JSON syntax.
        CloudFormationParserError: For any other file-reading related
            error.
    """
    logger.info("Starting CloudFormation parse for file: %s", file_path)

    if not is_cloudformation_file(file_path):
        logger.error("Invalid file extension for CloudFormation file: %s", file_path)
        raise CloudFormationParseError(
            f"Invalid file extension: {file_path} (expected .yaml, .yml, "
            f"or .json)"
        )

    raw_content = read_cloudformation_file(file_path)
    file_extension = Path(file_path).suffix
    parsed_data = parse_cloudformation_content(
        raw_content, file_extension=file_extension, source_name=file_path
    )

    logger.info("Completed CloudFormation parse for file: %s", file_path)
    return parsed_data


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the parser.

    Usage:
        python cloudformation_parser.py <path_to_template_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python cloudformation_parser.py <path_to_template_file>")
        sys.exit(1)

    template_path = sys.argv[1]

    try:
        result = parse_cloudformation_file(template_path)
        print(result)
    except CloudFormationParserError as exc:
        logger.error("CloudFormation parsing failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
