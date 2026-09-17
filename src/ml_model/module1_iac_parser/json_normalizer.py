"""
json_normalizer.py

A production-ready JSON normalizer for Infrastructure-as-Code (IaC)
assurance pipelines.

This module accepts the outputs already produced by the earlier stages
of the pipeline — the IaC provider label, the flat list of extracted
resources (`resource_extractor.py`), and the flat list of extracted
dependencies (`dependency_extractor.py`) — and combines them into a
single, standardized JSON-serializable object. No resource or
dependency data is altered, re-derived, or re-shaped in the process;
this module only assembles and validates a consistent envelope around
data that has already been extracted.

Requirements:
    - Python 3.12

Typical usage:
    from terraform_parser import parse_terraform_file
    from resource_extractor import extract_resources
    from dependency_extractor import extract_dependencies
    from json_normalizer import normalize_json

    parsed_data = parse_terraform_file("sample_terraform.tf")
    resources = extract_resources(parsed_data, provider="Terraform")
    dependencies = extract_dependencies(parsed_data, provider="Terraform")

    normalized = normalize_json(
        provider="Terraform",
        resources=resources,
        dependencies=dependencies,
    )
    print(normalized)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

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
class JSONNormalizerError(Exception):
    """Base exception for all errors raised by the JSON normalizer."""


# ---------------------------------------------------------------------------
# Supported providers
# ---------------------------------------------------------------------------
_SUPPORTED_PROVIDERS = ("Terraform", "CloudFormation")

# ---------------------------------------------------------------------------
# Required top-level and nested schema keys
# ---------------------------------------------------------------------------
_REQUIRED_TOP_LEVEL_KEYS = ("provider", "metadata", "resources", "dependencies")
_REQUIRED_METADATA_KEYS = ("resource_count", "dependency_count")
_REQUIRED_RESOURCE_KEYS = ("name", "type", "provider", "properties")
_REQUIRED_DEPENDENCY_KEYS = ("source", "target", "relationship", "provider")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_provider(provider: str) -> str:
    """
    Validate that a provider label is a non-empty, recognized string.

    Args:
        provider: The IaC provider label to validate (e.g. "Terraform").

    Returns:
        The provider label unchanged.

    Raises:
        JSONNormalizerError: If `provider` is not a non-empty string, or
            is not one of the recognized provider values.
    """
    if not isinstance(provider, str) or not provider.strip():
        logger.error("Invalid provider value: %r", provider)
        raise JSONNormalizerError(f"Invalid provider value: {provider!r}")

    if provider not in _SUPPORTED_PROVIDERS:
        logger.error("Unsupported provider requested: %s", provider)
        raise JSONNormalizerError(
            f"Unsupported provider: {provider} (expected one of "
            f"{_SUPPORTED_PROVIDERS})"
        )

    return provider


def _validate_resources(resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate that resources are provided in the expected list-of-dicts
    shape, without inspecting or hardcoding any specific resource type.

    Args:
        resources: The list of extracted resource dictionaries, as
            produced by `resource_extractor.extract_resources()`.

    Returns:
        `resources` unchanged.

    Raises:
        JSONNormalizerError: If `resources` is not a list, or if any
            entry is not a dict containing the required keys.
    """
    if not isinstance(resources, list):
        logger.error("Expected resources to be a list, got %s", type(resources).__name__)
        raise JSONNormalizerError(
            f"Invalid resources shape: expected a list, got {type(resources).__name__}"
        )

    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            logger.error("Resource at index %d is not a dict: %r", index, resource)
            raise JSONNormalizerError(f"Invalid resource entry at index {index}: {resource!r}")

        missing_keys = [key for key in _REQUIRED_RESOURCE_KEYS if key not in resource]
        if missing_keys:
            logger.error(
                "Resource at index %d is missing required keys: %s", index, missing_keys
            )
            raise JSONNormalizerError(
                f"Resource at index {index} is missing required keys: {missing_keys}"
            )

    return resources


def _validate_dependencies(dependencies: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Validate that dependencies are provided in the expected list-of-dicts
    shape, without inspecting or hardcoding any specific relationship
    type.

    Args:
        dependencies: The list of extracted dependency dictionaries, as
            produced by `dependency_extractor.extract_dependencies()`.

    Returns:
        `dependencies` unchanged.

    Raises:
        JSONNormalizerError: If `dependencies` is not a list, or if any
            entry is not a dict containing the required keys.
    """
    if not isinstance(dependencies, list):
        logger.error(
            "Expected dependencies to be a list, got %s", type(dependencies).__name__
        )
        raise JSONNormalizerError(
            f"Invalid dependencies shape: expected a list, got "
            f"{type(dependencies).__name__}"
        )

    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            logger.error("Dependency at index %d is not a dict: %r", index, dependency)
            raise JSONNormalizerError(
                f"Invalid dependency entry at index {index}: {dependency!r}"
            )

        missing_keys = [key for key in _REQUIRED_DEPENDENCY_KEYS if key not in dependency]
        if missing_keys:
            logger.error(
                "Dependency at index %d is missing required keys: %s", index, missing_keys
            )
            raise JSONNormalizerError(
                f"Dependency at index {index} is missing required keys: {missing_keys}"
            )

    return dependencies


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def normalize_json(
    provider: str,
    resources: List[Dict[str, Any]],
    dependencies: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Combine a provider label, extracted resources, and extracted
    dependencies into a single standardized JSON-serializable object.

    This is the main entry point of the module. It performs no
    transformation of the resource or dependency data itself — each
    resource and dependency dictionary is carried through exactly as
    given — and only assembles the uniform envelope described below,
    computing summary counts for the `metadata` block.

    Output shape:
        {
            "provider": "...",
            "metadata": {
                "resource_count": ...,
                "dependency_count": ...
            },
            "resources": [...],
            "dependencies": [...]
        }

    Args:
        provider: The IaC provider that produced the resources and
            dependencies ("Terraform" or "CloudFormation").
        resources: The list of extracted resource dictionaries, as
            produced by `resource_extractor.extract_resources()`.
        dependencies: The list of extracted dependency dictionaries, as
            produced by `dependency_extractor.extract_dependencies()`.

    Returns:
        A standardized dictionary combining the provider, resources,
        dependencies, and summary metadata.

    Raises:
        JSONNormalizerError: If `provider` is invalid or unsupported, or
            if `resources` / `dependencies` are not in their expected
            shapes.
    """
    logger.info("Starting JSON normalization for provider: %s", provider)

    validated_provider = _validate_provider(provider)
    validated_resources = _validate_resources(resources)
    validated_dependencies = _validate_dependencies(dependencies)

    normalized_data: Dict[str, Any] = {
        "provider": validated_provider,
        "metadata": {
            "resource_count": len(validated_resources),
            "dependency_count": len(validated_dependencies),
        },
        "resources": validated_resources,
        "dependencies": validated_dependencies,
    }

    logger.info(
        "Completed JSON normalization for provider: %s (resources=%d, dependencies=%d)",
        validated_provider,
        len(validated_resources),
        len(validated_dependencies),
    )
    return normalized_data


def validate_normalized_json(normalized_data: Dict[str, Any]) -> bool:
    """
    Validate that a normalized JSON object conforms to the standardized
    schema produced by `normalize_json()`.

    This function is intended for consumers of already-normalized data
    (e.g. a future Parser Manager or the Unified Intermediate
    Representation module) to confirm the schema is intact before
    relying on it further.

    Args:
        normalized_data: The normalized JSON object to validate.

    Returns:
        True if `normalized_data` conforms to the expected schema.

    Raises:
        JSONNormalizerError: If `normalized_data` is not a dict, is
            missing required top-level or metadata keys, has resource or
            dependency entries missing required keys, or if the
            `metadata` counts do not match the actual list lengths.
    """
    if not isinstance(normalized_data, dict):
        logger.error(
            "Expected normalized_data to be a dict, got %s",
            type(normalized_data).__name__,
        )
        raise JSONNormalizerError(
            f"Invalid normalized_data type: {type(normalized_data).__name__}"
        )

    missing_top_level_keys = [
        key for key in _REQUIRED_TOP_LEVEL_KEYS if key not in normalized_data
    ]
    if missing_top_level_keys:
        logger.error(
            "Normalized JSON is missing required top-level keys: %s",
            missing_top_level_keys,
        )
        raise JSONNormalizerError(
            f"Normalized JSON is missing required top-level keys: "
            f"{missing_top_level_keys}"
        )

    _validate_provider(normalized_data["provider"])

    metadata = normalized_data["metadata"]
    if not isinstance(metadata, dict):
        logger.error("Expected 'metadata' to be a dict, got %s", type(metadata).__name__)
        raise JSONNormalizerError(
            f"Invalid 'metadata' shape: expected a dict, got {type(metadata).__name__}"
        )

    missing_metadata_keys = [
        key for key in _REQUIRED_METADATA_KEYS if key not in metadata
    ]
    if missing_metadata_keys:
        logger.error(
            "Normalized JSON metadata is missing required keys: %s", missing_metadata_keys
        )
        raise JSONNormalizerError(
            f"Normalized JSON metadata is missing required keys: {missing_metadata_keys}"
        )

    resources = _validate_resources(normalized_data["resources"])
    dependencies = _validate_dependencies(normalized_data["dependencies"])

    if metadata["resource_count"] != len(resources):
        logger.error(
            "Metadata resource_count (%s) does not match actual resource count (%d)",
            metadata["resource_count"],
            len(resources),
        )
        raise JSONNormalizerError(
            f"Metadata 'resource_count' ({metadata['resource_count']}) does not match "
            f"actual resource count ({len(resources)})"
        )

    if metadata["dependency_count"] != len(dependencies):
        logger.error(
            "Metadata dependency_count (%s) does not match actual dependency count (%d)",
            metadata["dependency_count"],
            len(dependencies),
        )
        raise JSONNormalizerError(
            f"Metadata 'dependency_count' ({metadata['dependency_count']}) does not "
            f"match actual dependency count ({len(dependencies)})"
        )

    logger.info("Normalized JSON schema validated successfully.")
    return True


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the JSON
    normalizer against a Terraform or CloudFormation file, running the
    full parse -> extract resources -> extract dependencies -> normalize
    pipeline.

    Usage:
        python json_normalizer.py <path_to_tf_or_cfn_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python json_normalizer.py <path_to_tf_or_cfn_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        from .dependency_extractor import extract_dependencies
        from .resource_extractor import extract_resources

        if file_path.endswith(".tf"):
            from .terraform_parser import parse_terraform_file

            provider = "Terraform"
            parsed_data = parse_terraform_file(file_path)
        elif file_path.endswith((".yaml", ".yml", ".json")):
            from .cloudformation_parser import parse_cloudformation_file

            provider = "CloudFormation"
            parsed_data = parse_cloudformation_file(file_path)
        else:
            logger.error("Unsupported file type: %s", file_path)
            sys.exit(1)

        resources = extract_resources(parsed_data, provider=provider)
        dependencies = extract_dependencies(parsed_data, provider=provider)
        normalized = normalize_json(
            provider=provider, resources=resources, dependencies=dependencies
        )
        validate_normalized_json(normalized)
        print(normalized)
    except JSONNormalizerError as exc:
        logger.error("JSON normalization failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
