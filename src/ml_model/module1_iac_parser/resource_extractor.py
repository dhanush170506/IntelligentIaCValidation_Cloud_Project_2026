"""
resource_extractor.py

A production-ready resource extractor for Infrastructure-as-Code (IaC)
templates.

This module accepts the parsed Python dictionary produced by either
`terraform_parser.py` (Terraform) or `cloudformation_parser.py`
(CloudFormation) and extracts a flat, uniform list of cloud resources
from it. No dependency detection, JSON normalization, or AI reasoning
is performed here — this module is strictly concerned with identifying
"what resources exist" in a parsed IaC document.

Requirements:
    - Python 3.12

Typical usage:
    from terraform_parser import parse_terraform_file
    from resource_extractor import extract_resources

    parsed_data = parse_terraform_file("sample_terraform.tf")
    resources = extract_resources(parsed_data, provider="Terraform")
    print(resources)
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
class ResourceExtractorError(Exception):
    """Base exception for all errors raised by the resource extractor."""


# ---------------------------------------------------------------------------
# Provider labels
# ---------------------------------------------------------------------------
_PROVIDER_TERRAFORM = "Terraform"
_PROVIDER_CLOUDFORMATION = "CloudFormation"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _unwrap_terraform_properties(raw_properties: Any) -> Dict[str, Any]:
    """
    Normalize the shape of a Terraform resource's property block.

    The `python-hcl2` library wraps a resource's property block in a
    single-element list (e.g. `[{"ami": "...", "instance_type": "..."}]`).
    This helper unwraps that list so callers always receive a plain
    dictionary, without altering any of the underlying key/value data.

    Args:
        raw_properties: The raw properties value as produced by
            `python-hcl2` for a single resource.

    Returns:
        A dictionary of the resource's properties. Returns an empty
        dictionary if `raw_properties` is empty or not a recognizable
        shape.
    """
    if isinstance(raw_properties, list):
        if raw_properties and isinstance(raw_properties[0], dict):
            return raw_properties[0]
        return {}

    if isinstance(raw_properties, dict):
        return raw_properties

    logger.debug(
        "Unrecognized Terraform properties shape (%s); defaulting to empty dict.",
        type(raw_properties).__name__,
    )
    return {}


def extract_terraform_resources(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract cloud resources from a parsed Terraform configuration.

    Expects the input shape produced by `terraform_parser.py`, e.g.:
        {
            "resource": [
                {"aws_instance": {"web_server": {...}}},
                {"aws_security_group": {"web_sg": {...}}}
            ]
        }

    Args:
        parsed_data: The parsed Terraform configuration dictionary.

    Returns:
        A list of dictionaries, each with the keys "name", "type",
        "provider", and "properties". Returns an empty list if no
        `resource` blocks are present.

    Raises:
        ResourceExtractorError: If the `resource` block is present but
            is not in the expected list-of-dicts shape.
    """
    resource_blocks = parsed_data.get("resource", [])

    if not resource_blocks:
        logger.info("No Terraform resource blocks found in parsed data.")
        return []

    if not isinstance(resource_blocks, list):
        logger.error(
            "Expected Terraform 'resource' to be a list, got %s",
            type(resource_blocks).__name__,
        )
        raise ResourceExtractorError(
            f"Invalid Terraform 'resource' block shape: {type(resource_blocks).__name__}"
        )

    extracted: List[Dict[str, Any]] = []

    for resource_block in resource_blocks:
        if not isinstance(resource_block, dict):
            logger.warning(
                "Skipping malformed Terraform resource block: %r", resource_block
            )
            continue

        for resource_type, resources_by_name in resource_block.items():
            if not isinstance(resources_by_name, dict):
                logger.warning(
                    "Skipping malformed Terraform resource type entry for '%s'",
                    resource_type,
                )
                continue

            for resource_name, raw_properties in resources_by_name.items():
                properties = _unwrap_terraform_properties(raw_properties)
                extracted.append(
                    {
                        "name": resource_name,
                        "type": resource_type,
                        "provider": _PROVIDER_TERRAFORM,
                        "properties": properties,
                    }
                )
                logger.debug(
                    "Extracted Terraform resource: %s (%s)",
                    resource_name,
                    resource_type,
                )

    logger.info("Extracted %d Terraform resource(s).", len(extracted))
    return extracted


def extract_cloudformation_resources(
    parsed_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract cloud resources from a parsed CloudFormation template.

    Expects the input shape produced by `cloudformation_parser.py`, e.g.:
        {
            "Resources": {
                "WebServerInstance": {
                    "Type": "AWS::EC2::Instance",
                    "Properties": {...}
                }
            }
        }

    Args:
        parsed_data: The parsed CloudFormation template dictionary.

    Returns:
        A list of dictionaries, each with the keys "name", "type",
        "provider", and "properties". Returns an empty list if no
        `Resources` block is present.

    Raises:
        ResourceExtractorError: If the `Resources` block is present but
            is not in the expected dict shape.
    """
    resources = parsed_data.get("Resources", {})

    if not resources:
        logger.info("No CloudFormation 'Resources' block found in parsed data.")
        return []

    if not isinstance(resources, dict):
        logger.error(
            "Expected CloudFormation 'Resources' to be a dict, got %s",
            type(resources).__name__,
        )
        raise ResourceExtractorError(
            f"Invalid CloudFormation 'Resources' block shape: "
            f"{type(resources).__name__}"
        )

    extracted: List[Dict[str, Any]] = []

    for resource_name, resource_definition in resources.items():
        if not isinstance(resource_definition, dict):
            logger.warning(
                "Skipping malformed CloudFormation resource: %s", resource_name
            )
            continue

        resource_type = resource_definition.get("Type", "Unknown")
        properties = resource_definition.get("Properties", {})

        if not isinstance(properties, dict):
            logger.debug(
                "Non-dict properties for CloudFormation resource '%s'; "
                "defaulting to empty dict.",
                resource_name,
            )
            properties = {}

        extracted.append(
            {
                "name": resource_name,
                "type": resource_type,
                "provider": _PROVIDER_CLOUDFORMATION,
                "properties": properties,
            }
        )
        logger.debug(
            "Extracted CloudFormation resource: %s (%s)",
            resource_name,
            resource_type,
        )

    logger.info("Extracted %d CloudFormation resource(s).", len(extracted))
    return extracted


def extract_resources(
    parsed_data: Dict[str, Any], provider: str
) -> List[Dict[str, Any]]:
    """
    Extract cloud resources from a parsed IaC document, dispatching to
    the appropriate provider-specific extractor.

    This is the main entry point of the module. It routes the parsed
    data to `extract_terraform_resources()` or
    `extract_cloudformation_resources()` based on the given `provider`,
    and returns a uniform list of resource dictionaries.

    Args:
        parsed_data: The parsed IaC configuration dictionary, as
            returned by `terraform_parser.parse_terraform_file()` or
            `cloudformation_parser.parse_cloudformation_file()`.
        provider: The IaC provider that produced `parsed_data`. Must be
            one of "Terraform" or "CloudFormation" (case-insensitive).

    Returns:
        A list of dictionaries, each with the keys "name", "type",
        "provider", and "properties".

    Raises:
        ResourceExtractorError: If `provider` is not a recognized value,
            or if the underlying provider-specific extraction fails.
    """
    if not isinstance(parsed_data, dict):
        logger.error(
            "Expected parsed_data to be a dict, got %s", type(parsed_data).__name__
        )
        raise ResourceExtractorError(
            f"Invalid parsed_data type: {type(parsed_data).__name__}"
        )

    normalized_provider = provider.strip().lower()
    logger.info("Starting resource extraction for provider: %s", provider)

    if normalized_provider == _PROVIDER_TERRAFORM.lower():
        resources = extract_terraform_resources(parsed_data)
    elif normalized_provider == _PROVIDER_CLOUDFORMATION.lower():
        resources = extract_cloudformation_resources(parsed_data)
    else:
        logger.error("Unsupported provider requested: %s", provider)
        raise ResourceExtractorError(
            f"Unsupported provider: {provider} (expected 'Terraform' or "
            f"'CloudFormation')"
        )

    logger.info("Completed resource extraction for provider: %s", provider)
    return resources


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the extractor
    against an already-parsed Terraform or CloudFormation file.

    Usage:
        python resource_extractor.py <path_to_tf_or_cfn_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python resource_extractor.py <path_to_tf_or_cfn_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        if file_path.endswith(".tf"):
            from .terraform_parser import parse_terraform_file

            parsed_data = parse_terraform_file(file_path)
            resources = extract_resources(parsed_data, provider=_PROVIDER_TERRAFORM)
        elif file_path.endswith((".yaml", ".yml", ".json")):
            from .cloudformation_parser import parse_cloudformation_file

            parsed_data = parse_cloudformation_file(file_path)
            resources = extract_resources(
                parsed_data, provider=_PROVIDER_CLOUDFORMATION
            )
        else:
            logger.error("Unsupported file type: %s", file_path)
            sys.exit(1)

        print(resources)
    except ResourceExtractorError as exc:
        logger.error("Resource extraction failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
