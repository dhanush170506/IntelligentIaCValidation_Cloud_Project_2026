"""
uir_schema.py

Builds the canonical Unified Intermediate Representation (UIR) from the
normalized JSON produced by Module 1 (`parser_manager.process_iac_file()`
/ `json_normalizer.normalize_json()`).

Module 1's normalized JSON is already provider-agnostic in its
*envelope* shape (`provider`, `metadata`, `resources`, `dependencies`),
but each resource still carries only its provider-native `type` (e.g.
"aws_instance" or "AWS::EC2::Instance") and has no stable, globally
unique identifier a graph could key on. This module closes that final
gap: it enriches each resource with a canonical type (via
`provider_mapper.get_canonical_resource_type()`) and a stable `id`,
producing the single schema that every later module — Graph Builder,
Validation Engine, Retrieval-Augmented Generation, the Multi-Agent
Framework, and the LLM Explanation Engine — is expected to consume.

No parsing, extraction, or provider-specific business logic lives here.
This module only reshapes data that Module 1 has already validated and
extracted correctly.

Requirements:
    - Python 3.12

Typical usage:
    from parser_manager import process_iac_file
    from uir_schema import build_uir

    normalized = process_iac_file("sample_terraform.tf")
    uir = build_uir(normalized)
    print(uir)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .provider_mapper import get_canonical_resource_type
from .schema_constants import (
    KEY_DEPENDENCIES,
    KEY_METADATA,
    KEY_PROPERTIES,
    KEY_PROVIDER,
    KEY_RESOURCE_ID,
    KEY_RESOURCE_NAME,
    KEY_RESOURCE_TYPE,
    KEY_RESOURCES,
)

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
class UIRSchemaError(Exception):
    """Base exception for all errors raised while building the UIR."""


# ---------------------------------------------------------------------------
# UIR-specific schema key
# ---------------------------------------------------------------------------
# "canonical_type" is introduced by the UIR itself (Module 1 has no
# notion of a provider-agnostic type), so it does not exist in
# `schema_constants.py`. Declared once here, rather than as a repeated
# string literal, for the same reason every other schema key is a
# constant.
KEY_CANONICAL_TYPE = "canonical_type"

# ---------------------------------------------------------------------------
# Providers whose resource identifier is built as "type.name" rather
# than the bare resource name. Any provider not listed here (including
# CloudFormation and any future provider not yet special-cased) falls
# back to the bare-name identifier scheme.
# ---------------------------------------------------------------------------
_TYPE_QUALIFIED_ID_PROVIDERS = ("Terraform",)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_normalized_json(normalized_json: Dict[str, Any]) -> None:
    """
    Validate that the normalized JSON produced by Module 1 contains the
    top-level fields the UIR builder depends on.

    Args:
        normalized_json: The normalized JSON object to validate.

    Raises:
        UIRSchemaError: If `normalized_json` is not a dict, or if
            `provider`, `resources`, or `dependencies` is missing.
    """
    if not isinstance(normalized_json, dict):
        logger.error(
            "Expected normalized_json to be a dict, got %s",
            type(normalized_json).__name__,
        )
        raise UIRSchemaError(
            f"Invalid normalized_json type: {type(normalized_json).__name__}"
        )

    if not normalized_json.get(KEY_PROVIDER):
        logger.error("Normalized JSON is missing required field: '%s'", KEY_PROVIDER)
        raise UIRSchemaError(f"Normalized JSON is missing required field: '{KEY_PROVIDER}'")

    if KEY_RESOURCES not in normalized_json:
        logger.error("Normalized JSON is missing required field: '%s'", KEY_RESOURCES)
        raise UIRSchemaError(f"Normalized JSON is missing required field: '{KEY_RESOURCES}'")

    if KEY_DEPENDENCIES not in normalized_json:
        logger.error(
            "Normalized JSON is missing required field: '%s'", KEY_DEPENDENCIES
        )
        raise UIRSchemaError(
            f"Normalized JSON is missing required field: '{KEY_DEPENDENCIES}'"
        )


def _validate_resource_entry(resource: Dict[str, Any], index: int) -> None:
    """
    Validate that a single resource entry contains the fields required
    to build its UIR representation.

    Args:
        resource: The resource dictionary to validate.
        index: The resource's position in the `resources` list, used
            only for error messages.

    Raises:
        UIRSchemaError: If `resource` is not a dict, or if `type`,
            `name`, or `properties` is missing.
    """
    if not isinstance(resource, dict):
        logger.error("Resource at index %d is not a dict: %r", index, resource)
        raise UIRSchemaError(f"Invalid resource entry at index {index}: {resource!r}")

    if KEY_RESOURCE_TYPE not in resource:
        logger.error("Resource at index %d is missing required field: 'type'", index)
        raise UIRSchemaError(f"Resource at index {index} is missing required field: 'type'")

    if KEY_RESOURCE_NAME not in resource:
        logger.error("Resource at index %d is missing required field: 'name'", index)
        raise UIRSchemaError(f"Resource at index {index} is missing required field: 'name'")

    if KEY_PROPERTIES not in resource:
        logger.error(
            "Resource at index %d is missing required field: 'properties'", index
        )
        raise UIRSchemaError(
            f"Resource at index {index} is missing required field: 'properties'"
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _build_resource_id(resource_type: str, resource_name: str, provider: str) -> str:
    """
    Build a stable, provider-appropriate identifier for a resource.

    Terraform identifiers are ambiguous by name alone (multiple resource
    types can share a name), so they are qualified as "type.name" (e.g.
    "aws_instance.web_server") — matching the identifier scheme already
    used by `dependency_extractor.py`'s Terraform output. CloudFormation
    logical names are already unique within a template, so the bare
    resource name is used (e.g. "WebServerInstance") — also matching
    `dependency_extractor.py`'s CloudFormation output. Any other
    provider defaults to the bare-name scheme.

    Args:
        resource_type: The resource's provider-native type.
        resource_name: The resource's logical/declared name.
        provider: The IaC provider that produced the resource.

    Returns:
        The resource's UIR identifier.
    """
    if provider in _TYPE_QUALIFIED_ID_PROVIDERS:
        return f"{resource_type}.{resource_name}"

    return resource_name


def _build_uir_resource(resource: Dict[str, Any], index: int, provider: str) -> Dict[str, Any]:
    """
    Convert a single Module 1 resource entry into its UIR representation.

    Args:
        resource: The resource dictionary as produced by
            `resource_extractor.extract_resources()`.
        index: The resource's position in the `resources` list, used
            only for error messages.
        provider: The top-level IaC provider from the normalized JSON,
            used as a fallback if the resource entry itself has no
            `provider` field.

    Returns:
        A UIR resource dictionary containing `id`, `provider`, `type`,
        `canonical_type`, `name`, and `properties`.

    Raises:
        UIRSchemaError: If the resource entry is missing required
            fields.
    """
    _validate_resource_entry(resource, index)

    resource_type = resource[KEY_RESOURCE_TYPE]
    resource_name = resource[KEY_RESOURCE_NAME]
    resource_provider = resource.get(KEY_PROVIDER, provider)

    uir_resource = {
        KEY_RESOURCE_ID: _build_resource_id(resource_type, resource_name, resource_provider),
        KEY_PROVIDER: resource_provider,
        KEY_RESOURCE_TYPE: resource_type,
        KEY_CANONICAL_TYPE: get_canonical_resource_type(resource_type),
        KEY_RESOURCE_NAME: resource_name,
        KEY_PROPERTIES: resource[KEY_PROPERTIES],
    }

    logger.debug(
        "Built UIR resource '%s' (canonical_type=%s) from index %d",
        uir_resource[KEY_RESOURCE_ID],
        uir_resource[KEY_CANONICAL_TYPE],
        index,
    )
    return uir_resource


def build_uir(normalized_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the canonical Unified Intermediate Representation (UIR) from
    the normalized JSON produced by Module 1.

    This is the main public entry point of the module. Every resource
    in the input is enriched with a stable `id` and a `canonical_type`
    (via `provider_mapper.get_canonical_resource_type()`), while its
    original provider-native `type`, `name`, and `properties` are
    carried through unchanged. `dependencies` and `metadata` are passed
    through as-is: `dependencies` already reference resources using the
    same identifier scheme applied here (Terraform's "type.name",
    CloudFormation's bare name), and `metadata`'s resource/dependency
    counts remain accurate since no resources or dependencies are added
    or removed.

    Args:
        normalized_json: The normalized JSON object produced by
            `json_normalizer.normalize_json()` /
            `parser_manager.process_iac_file()`.

    Returns:
        A UIR dictionary with the shape:
            {
                "provider": "...",
                "metadata": {
                    "resource_count": ...,
                    "dependency_count": ...
                },
                "resources": [
                    {
                        "id": "...",
                        "provider": "...",
                        "type": "...",
                        "canonical_type": "...",
                        "name": "...",
                        "properties": {...}
                    }
                ],
                "dependencies": [...]
            }

    Raises:
        UIRSchemaError: If `normalized_json` is missing `provider`,
            `resources`, or `dependencies`, or if any resource entry is
            missing `type`, `name`, or `properties`.
    """
    logger.info("Starting UIR construction.")

    _validate_normalized_json(normalized_json)

    provider = normalized_json[KEY_PROVIDER]
    resources = normalized_json[KEY_RESOURCES]
    dependencies = normalized_json[KEY_DEPENDENCIES]

    uir_resources: List[Dict[str, Any]] = [
        _build_uir_resource(resource, index, provider)
        for index, resource in enumerate(resources)
    ]

    uir: Dict[str, Any] = {
        KEY_PROVIDER: provider,
        KEY_METADATA: normalized_json.get(KEY_METADATA, {}),
        KEY_RESOURCES: uir_resources,
        KEY_DEPENDENCIES: dependencies,
    }

    logger.info(
        "Completed UIR construction for provider: %s (resources=%d, dependencies=%d)",
        provider,
        len(uir_resources),
        len(dependencies),
    )
    return uir

__all__ = [
    "UIRSchemaError",
    "build_uir",
]