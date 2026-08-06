"""
uir_validator.py

A structural validator for the Unified Intermediate Representation
(UIR) produced by `uir_schema.build_uir()`.

This module performs validation only. It never modifies its input,
never normalizes data, and never repairs a missing or malformed field
— it exists purely to answer one question: does a given UIR object
conform to the schema every later module (Graph Builder, Validation
Engine, Retrieval-Augmented Generation, the Multi-Agent Framework, the
LLM Explanation Engine) is expected to rely on? If it does not, this
module raises `UIRValidationError` describing exactly what is wrong,
rather than silently letting malformed data reach modules that assume
a correct shape.

Requirements:
    - Python 3.12

Typical usage:
    from uir_schema import build_uir
    from uir_validator import validate_uir

    uir = build_uir(normalized_json)
    validate_uir(uir)  # raises UIRValidationError if invalid
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .schema_constants import (
    KEY_DEPENDENCIES,
    KEY_DEPENDENCY_COUNT,
    KEY_METADATA,
    KEY_PROPERTIES,
    KEY_PROVIDER,
    KEY_RELATIONSHIP,
    KEY_RESOURCE_COUNT,
    KEY_RESOURCE_ID,
    KEY_RESOURCE_NAME,
    KEY_RESOURCE_TYPE,
    KEY_RESOURCES,
    KEY_SOURCE,
    KEY_TARGET,
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
class UIRValidationError(Exception):
    """Base exception for all errors raised while validating a UIR."""


# ---------------------------------------------------------------------------
# UIR-specific schema key
# ---------------------------------------------------------------------------
# "canonical_type" is introduced by the UIR itself (it does not exist
# in Module 1's schema, so it is absent from `schema_constants.py`).
# Kept local to this module rather than imported from `uir_schema.py`,
# since a validator should not depend on the internals of the module it
# validates.
_KEY_CANONICAL_TYPE = "canonical_type"

# ---------------------------------------------------------------------------
# Required key sets, declared once so they are never repeated as
# literal lists elsewhere in this module.
# ---------------------------------------------------------------------------
_REQUIRED_TOP_LEVEL_KEYS = (KEY_PROVIDER, KEY_METADATA, KEY_RESOURCES, KEY_DEPENDENCIES)
_REQUIRED_METADATA_KEYS = (KEY_RESOURCE_COUNT, KEY_DEPENDENCY_COUNT)
_REQUIRED_RESOURCE_KEYS = (
    KEY_RESOURCE_ID,
    KEY_PROVIDER,
    KEY_RESOURCE_TYPE,
    _KEY_CANONICAL_TYPE,
    KEY_RESOURCE_NAME,
    KEY_PROPERTIES,
)
_REQUIRED_RESOURCE_STRING_KEYS = (
    KEY_RESOURCE_ID,
    KEY_PROVIDER,
    KEY_RESOURCE_TYPE,
    _KEY_CANONICAL_TYPE,
    KEY_RESOURCE_NAME,
)
_REQUIRED_DEPENDENCY_KEYS = (KEY_SOURCE, KEY_TARGET, KEY_RELATIONSHIP, KEY_PROVIDER)


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------
def _require_non_empty_string(value: Any, field_name: str, context: str) -> None:
    """
    Validate that a field's value is a non-empty string.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message.
        context: A short description of where this field lives (e.g.
            "top-level", "resource at index 0"), used in the error
            message.

    Raises:
        UIRValidationError: If `value` is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        logger.error("%s: field '%s' must be a non-empty string, got %r", context, field_name, value)
        raise UIRValidationError(
            f"{context}: field '{field_name}' must be a non-empty string, got {value!r}"
        )


def _require_non_negative_int(value: Any, field_name: str, context: str) -> None:
    """
    Validate that a field's value is an integer greater than or equal
    to zero.

    Args:
        value: The value to validate.
        field_name: The name of the field being validated, used in the
            error message.
        context: A short description of where this field lives, used
            in the error message.

    Raises:
        UIRValidationError: If `value` is not an int, or is negative.
            `bool` is explicitly rejected even though it is technically
            an `int` subclass in Python, since a boolean is not a
            meaningful count.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        logger.error(
            "%s: field '%s' must be a non-negative integer, got %r", context, field_name, value
        )
        raise UIRValidationError(
            f"{context}: field '{field_name}' must be a non-negative integer, got {value!r}"
        )


# ---------------------------------------------------------------------------
# Structural validation helpers
# ---------------------------------------------------------------------------
def _validate_top_level(uir: Any) -> None:
    """
    Validate that the UIR object is a dict containing all required
    top-level keys.

    Args:
        uir: The UIR object to validate.

    Raises:
        UIRValidationError: If `uir` is not a dict, or if any required
            top-level key is missing.
    """
    if not isinstance(uir, dict):
        logger.error("UIR must be a dict, got %s", type(uir).__name__)
        raise UIRValidationError(f"UIR must be a dict, got {type(uir).__name__}")

    missing_keys = [key for key in _REQUIRED_TOP_LEVEL_KEYS if key not in uir]
    if missing_keys:
        logger.error("UIR is missing required top-level keys: %s", missing_keys)
        raise UIRValidationError(f"UIR is missing required top-level keys: {missing_keys}")

    _require_non_empty_string(uir[KEY_PROVIDER], KEY_PROVIDER, "top-level")


def _validate_metadata(metadata: Any) -> None:
    """
    Validate the UIR's `metadata` block.

    Args:
        metadata: The value of the UIR's `metadata` field.

    Raises:
        UIRValidationError: If `metadata` is not a dict, is missing
            `resource_count` or `dependency_count`, or if either is not
            a non-negative integer.
    """
    if not isinstance(metadata, dict):
        logger.error("'%s' must be a dict, got %s", KEY_METADATA, type(metadata).__name__)
        raise UIRValidationError(
            f"'{KEY_METADATA}' must be a dict, got {type(metadata).__name__}"
        )

    missing_keys = [key for key in _REQUIRED_METADATA_KEYS if key not in metadata]
    if missing_keys:
        logger.error("'%s' is missing required keys: %s", KEY_METADATA, missing_keys)
        raise UIRValidationError(f"'{KEY_METADATA}' is missing required keys: {missing_keys}")

    _require_non_negative_int(metadata[KEY_RESOURCE_COUNT], KEY_RESOURCE_COUNT, "metadata")
    _require_non_negative_int(metadata[KEY_DEPENDENCY_COUNT], KEY_DEPENDENCY_COUNT, "metadata")


def _validate_resource(resource: Any, index: int) -> None:
    """
    Validate a single resource entry within the UIR's `resources` list.

    Args:
        resource: The resource entry to validate.
        index: The resource's position in the `resources` list, used
            only for error messages.

    Raises:
        UIRValidationError: If `resource` is not a dict, is missing any
            required key, if any of `id`/`provider`/`type`/
            `canonical_type`/`name` is not a non-empty string, or if
            `properties` is not a dict.
    """
    context = f"resource at index {index}"

    if not isinstance(resource, dict):
        logger.error("%s is not a dict: %r", context, resource)
        raise UIRValidationError(f"{context} is not a dict: {resource!r}")

    missing_keys = [key for key in _REQUIRED_RESOURCE_KEYS if key not in resource]
    if missing_keys:
        logger.error("%s is missing required keys: %s", context, missing_keys)
        raise UIRValidationError(f"{context} is missing required keys: {missing_keys}")

    for field_name in _REQUIRED_RESOURCE_STRING_KEYS:
        _require_non_empty_string(resource[field_name], field_name, context)

    if not isinstance(resource[KEY_PROPERTIES], dict):
        logger.error(
            "%s: field '%s' must be a dict, got %s",
            context,
            KEY_PROPERTIES,
            type(resource[KEY_PROPERTIES]).__name__,
        )
        raise UIRValidationError(
            f"{context}: field '{KEY_PROPERTIES}' must be a dict, got "
            f"{type(resource[KEY_PROPERTIES]).__name__}"
        )


def _validate_resources(resources: Any) -> None:
    """
    Validate the UIR's `resources` list and every entry within it.

    Args:
        resources: The value of the UIR's `resources` field.

    Raises:
        UIRValidationError: If `resources` is not a list, or if any
            entry fails `_validate_resource`.
    """
    if not isinstance(resources, list):
        logger.error("'%s' must be a list, got %s", KEY_RESOURCES, type(resources).__name__)
        raise UIRValidationError(
            f"'{KEY_RESOURCES}' must be a list, got {type(resources).__name__}"
        )

    for index, resource in enumerate(resources):
        _validate_resource(resource, index)


def _validate_dependency(dependency: Any, index: int) -> None:
    """
    Validate a single dependency entry within the UIR's `dependencies`
    list.

    Args:
        dependency: The dependency entry to validate.
        index: The dependency's position in the `dependencies` list,
            used only for error messages.

    Raises:
        UIRValidationError: If `dependency` is not a dict, is missing
            any required key, or if any of `source`/`target`/
            `relationship`/`provider` is not a non-empty string.
    """
    context = f"dependency at index {index}"

    if not isinstance(dependency, dict):
        logger.error("%s is not a dict: %r", context, dependency)
        raise UIRValidationError(f"{context} is not a dict: {dependency!r}")

    missing_keys = [key for key in _REQUIRED_DEPENDENCY_KEYS if key not in dependency]
    if missing_keys:
        logger.error("%s is missing required keys: %s", context, missing_keys)
        raise UIRValidationError(f"{context} is missing required keys: {missing_keys}")

    for field_name in _REQUIRED_DEPENDENCY_KEYS:
        _require_non_empty_string(dependency[field_name], field_name, context)


def _validate_dependencies(dependencies: Any) -> None:
    """
    Validate the UIR's `dependencies` list and every entry within it.

    Args:
        dependencies: The value of the UIR's `dependencies` field.

    Raises:
        UIRValidationError: If `dependencies` is not a list, or if any
            entry fails `_validate_dependency`.
    """
    if not isinstance(dependencies, list):
        logger.error(
            "'%s' must be a list, got %s", KEY_DEPENDENCIES, type(dependencies).__name__
        )
        raise UIRValidationError(
            f"'{KEY_DEPENDENCIES}' must be a list, got {type(dependencies).__name__}"
        )

    for index, dependency in enumerate(dependencies):
        _validate_dependency(dependency, index)


def _validate_counts_match(
    metadata: Dict[str, Any], resources: List[Any], dependencies: List[Any]
) -> None:
    """
    Validate that the metadata's summary counts match the actual
    lengths of `resources` and `dependencies`.

    Args:
        metadata: The UIR's `metadata` block.
        resources: The UIR's `resources` list.
        dependencies: The UIR's `dependencies` list.

    Raises:
        UIRValidationError: If `metadata["resource_count"]` does not
            equal `len(resources)`, or if
            `metadata["dependency_count"]` does not equal
            `len(dependencies)`.
    """
    resource_count = metadata[KEY_RESOURCE_COUNT]
    if resource_count != len(resources):
        logger.error(
            "'%s' (%s) does not match actual resource count (%d)",
            KEY_RESOURCE_COUNT,
            resource_count,
            len(resources),
        )
        raise UIRValidationError(
            f"'{KEY_RESOURCE_COUNT}' ({resource_count}) does not match actual "
            f"resource count ({len(resources)})"
        )

    dependency_count = metadata[KEY_DEPENDENCY_COUNT]
    if dependency_count != len(dependencies):
        logger.error(
            "'%s' (%s) does not match actual dependency count (%d)",
            KEY_DEPENDENCY_COUNT,
            dependency_count,
            len(dependencies),
        )
        raise UIRValidationError(
            f"'{KEY_DEPENDENCY_COUNT}' ({dependency_count}) does not match actual "
            f"dependency count ({len(dependencies)})"
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def validate_uir(uir: Dict[str, Any]) -> None:
    """
    Validate that a UIR object conforms to the expected schema.

    This is the main public entry point of the module. It performs
    structural validation only — it never modifies `uir`, never
    normalizes any value, and never repairs a missing or malformed
    field. Validation proceeds in order: top-level shape, `metadata`,
    `resources` (and every entry within it), `dependencies` (and every
    entry within it), and finally that `metadata`'s summary counts
    match the actual list lengths.

    Args:
        uir: The UIR object to validate, as produced by
            `uir_schema.build_uir()`.

    Returns:
        None, if `uir` is valid.

    Raises:
        UIRValidationError: If `uir` fails any validation rule. The
            exception message identifies exactly which field or entry
            failed and why.
    """
    logger.info("Starting UIR validation.")

    _validate_top_level(uir)
    _validate_metadata(uir[KEY_METADATA])
    _validate_resources(uir[KEY_RESOURCES])
    _validate_dependencies(uir[KEY_DEPENDENCIES])
    _validate_counts_match(uir[KEY_METADATA], uir[KEY_RESOURCES], uir[KEY_DEPENDENCIES])

    logger.info(
        "UIR validation succeeded for provider: %s (resources=%d, dependencies=%d)",
        uir[KEY_PROVIDER],
        len(uir[KEY_RESOURCES]),
        len(uir[KEY_DEPENDENCIES]),
    )

__all__ = [
    "UIRValidationError",
    "validate_uir",
]