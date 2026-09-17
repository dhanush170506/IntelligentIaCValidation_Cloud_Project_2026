"""
dependency_extractor.py

A production-ready dependency extractor for Infrastructure-as-Code (IaC)
templates.

This module accepts the parsed Python dictionary produced by either
`terraform_parser.py` (Terraform) or `cloudformation_parser.py`
(CloudFormation) and detects relationships between the cloud resources
declared within it — e.g. an EC2 instance that references a security
group. It operates directly on the raw parsed dictionary (the same
input shape consumed by `resource_extractor.py`), not on the resource
extractor's output, so that parsing, resource extraction, and
dependency extraction remain three independent, composable stages.

No JSON normalization, resource-shape unification, or AI reasoning is
performed here — this module is strictly concerned with answering
"what depends on what".

Requirements:
    - Python 3.12

Typical usage:
    from terraform_parser import parse_terraform_file
    from dependency_extractor import extract_dependencies

    parsed_data = parse_terraform_file("sample_terraform.tf")
    dependencies = extract_dependencies(parsed_data, provider="Terraform")
    print(dependencies)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set, Tuple

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
class DependencyExtractorError(Exception):
    """Base exception for all errors raised by the dependency extractor."""


# ---------------------------------------------------------------------------
# Provider labels
# ---------------------------------------------------------------------------
_PROVIDER_TERRAFORM = "Terraform"
_PROVIDER_CLOUDFORMATION = "CloudFormation"

# ---------------------------------------------------------------------------
# Relationship labels
# ---------------------------------------------------------------------------
_RELATIONSHIP_DEPENDS_ON = "depends_on"
_RELATIONSHIP_REF = "Ref"
_RELATIONSHIP_DEPENDS_ON_CFN = "DependsOn"
_RELATIONSHIP_GET_ATT = "Fn::GetAtt"
_RELATIONSHIP_SUB = "Fn::Sub"
_RELATIONSHIP_IMPORT_VALUE = "Fn::ImportValue"

# Matches ${...} interpolation placeholders used in Terraform expressions
# and CloudFormation Fn::Sub templates (e.g. "${aws_security_group.web_sg.id}").
_INTERPOLATION_PATTERN = re.compile(r"\$\{([^}]+)\}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _build_dependency(
    source: str, target: str, relationship: str, provider: str
) -> Dict[str, str]:
    """
    Build a single dependency record in the uniform output shape shared
    by both Terraform and CloudFormation dependency extraction.

    Args:
        source: The name/identifier of the resource that holds the
            reference.
        target: The name/identifier of the resource being referenced.
        relationship: The kind of reference (e.g. "depends_on", "Ref",
            "Fn::GetAtt").
        provider: The IaC provider the dependency was detected in
            ("Terraform" or "CloudFormation").

    Returns:
        A dictionary with the keys "source", "target", "relationship",
        and "provider".
    """
    return {
        "source": source,
        "target": target,
        "relationship": relationship,
        "provider": provider,
    }


# Matches a dot-delimited reference chain (e.g. "aws_security_group.web_sg"
# or "aws_security_group.web_sg.id"). Used to pull candidate "type.name"
# resource references out of the text found inside a "${...}"
# interpolation expression.
_TERRAFORM_REFERENCE_CHAIN_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)+"
)


# ---------------------------------------------------------------------------
# Terraform dependency extraction
# ---------------------------------------------------------------------------
def _collect_terraform_candidate_strings(value: Any, collected: List[str]) -> None:
    """
    Recursively walk a Terraform resource's raw property structure and
    collect every candidate string that could contain a resource
    reference — both string leaf values (list elements, `depends_on`
    entries, nested block attributes) and dictionary keys.

    Walking the real structure directly (instead of serializing it to
    text) guarantees a reference is found regardless of how deeply it
    is nested inside lists or dictionaries.

    Args:
        value: The value to walk (dict, list, string, or any scalar).
        collected: The accumulator list that candidate strings are
            appended to. Mutated in place.
    """
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if isinstance(key, str):
                collected.append(key)
            _collect_terraform_candidate_strings(nested_value, collected)
    elif isinstance(value, list):
        for item in value:
            _collect_terraform_candidate_strings(item, collected)
    elif isinstance(value, str):
        collected.append(value)


def _extract_terraform_targets(
    raw_value: Any, known_identifiers: Set[str], exclude_identifier: str
) -> List[str]:
    """
    Identify which known Terraform resource identifiers are referenced
    within an arbitrarily-shaped raw property value.

    `python-hcl2` represents a resource reference as a plain string,
    which may be:
        - A bare, unquoted expression, valid in modern Terraform, e.g.
          "aws_security_group.web_sg.id" (no interpolation braces —
          this is what `python-hcl2` actually produces for a native,
          unquoted HCL2 expression like
          `vpc_security_group_ids = [aws_security_group.web_sg.id]`).
        - A legacy quoted interpolation, e.g.
          "${aws_security_group.web_sg.id}" (only produced when the
          reference appears inside a quoted string in the source).

    This function recursively walks the real structure of `raw_value`
    (via `_collect_terraform_candidate_strings`) to find every
    candidate string, then extracts dot-delimited reference chains
    from each one (e.g. pulling "aws_security_group.web_sg" out of
    "aws_security_group.web_sg.id" or "${aws_security_group.web_sg.id}"
    — the "$", "{", and "}" characters are simply not part of the
    identifier character class, so the same chain pattern matches both
    forms without any special-casing).

    Args:
        raw_value: The raw property value to inspect, in whatever shape
            `python-hcl2` produced it.
        known_identifiers: The set of known "type.name" resource
            identifiers declared in the template.
        exclude_identifier: The identifier of the resource that owns
            `raw_value`, excluded from the results to avoid self-loops.

    Returns:
        A sorted list of referenced resource identifiers (a subset of
        `known_identifiers`), without duplicates.
    """
    candidate_strings: List[str] = []
    _collect_terraform_candidate_strings(raw_value, candidate_strings)

    targets: Set[str] = set()

    for candidate in candidate_strings:
        candidate = candidate.strip('"')
        for chain in _TERRAFORM_REFERENCE_CHAIN_PATTERN.findall(candidate):
            segments = chain.split(".")
            if len(segments) < 2:
                continue

            target_identifier = f"{segments[0]}.{segments[1]}"
            if target_identifier in known_identifiers and target_identifier != exclude_identifier:
                targets.add(target_identifier)

    return sorted(targets)


def _iter_terraform_resource_entries(resource_data: Any):
    """
    Yield every `(resource_type, resource_name, raw_properties)` triple
    found in a parsed Terraform `resource` structure.

    `python-hcl2` wraps repeatable HCL blocks in lists, but exactly how
    many levels of that wrapping appear can vary (e.g. the top-level
    `resource` value, or the mapping of resource names beneath a given
    type, may each be either a plain dict or a single/multi-element
    list of dicts). This generator normalizes over both possibilities
    at every level so that no declared resource is silently skipped
    because of an unexpected wrapping shape.

    Args:
        resource_data: The value of the parsed data's `"resource"` key,
            in whatever shape `python-hcl2` produced it.

    Yields:
        Tuples of `(resource_type, resource_name, raw_properties)` for
        every resource found.
    """
    if isinstance(resource_data, dict):
        blocks = [resource_data]
    elif isinstance(resource_data, list):
        blocks = resource_data
    else:
        return

    for block in blocks:
        if not isinstance(block, dict):
            logger.warning("Skipping malformed Terraform resource block: %r", block)
            continue

        for resource_type, resources_by_name in block.items():
            if isinstance(resources_by_name, dict):
                name_dicts = [resources_by_name]
            elif isinstance(resources_by_name, list):
                name_dicts = [item for item in resources_by_name if isinstance(item, dict)]
            else:
                logger.warning(
                    "Skipping malformed Terraform resource type entry for '%s'",
                    resource_type,
                )
                continue

            for name_dict in name_dicts:
                for resource_name, raw_properties in name_dict.items():
                    # Normalize quoted labels returned by python-hcl2 8.x
                    resource_type = resource_type.strip('"')
                    resource_name = resource_name.strip('"')

                    yield resource_type, resource_name, raw_properties


def extract_terraform_dependencies(parsed_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract dependencies from Terraform resources.
    """

    resource_data = parsed_data.get("resource", [])

    dependencies = []
    seen = set()

    resources = {}

    # Build resource map using the robust iterator
    for resource_type, resource_name, properties in _iter_terraform_resource_entries(resource_data):
        identifier = f"{resource_type}.{resource_name}"
        resources[identifier] = properties

    known_identifiers = set(resources.keys())

    # Detect dependencies
    for source_identifier, properties in resources.items():

        targets = _extract_terraform_targets(
            raw_value=properties,
            known_identifiers=known_identifiers,
            exclude_identifier=source_identifier,
        )

        for target_identifier in targets:

            key = (source_identifier, target_identifier)

            if key not in seen:
                seen.add(key)

                dependencies.append(
                    _build_dependency(
                        source=source_identifier,
                        target=target_identifier,
                        relationship="depends_on",
                        provider="Terraform",
                    )
                )

    logger.info(
        "Extracted %d Terraform dependency/dependencies.",
        len(dependencies),
    )

    return dependencies


# ---------------------------------------------------------------------------
# CloudFormation dependency extraction
# ---------------------------------------------------------------------------
def _extract_getatt_target(value: Any) -> str | None:
    """
    Extract the referenced resource name from a `Fn::GetAtt` value.

    `Fn::GetAtt` may appear as a dot-delimited string (short-form,
    e.g. "WebServerInstance.PublicIp") or as a two-element list
    (long-form, e.g. ["WebServerInstance", "PublicIp"]).

    Args:
        value: The raw `Fn::GetAtt` value.

    Returns:
        The referenced resource's logical name, or None if the value is
        not in a recognizable shape.
    """
    if isinstance(value, str):
        return value.split(".")[0] if "." in value else value

    if isinstance(value, list) and value:
        first_element = value[0]
        return first_element if isinstance(first_element, str) else None

    return None


def _extract_sub_targets(value: Any, known_identifiers: Set[str]) -> List[str]:
    """
    Extract referenced resource names from a `Fn::Sub` value.

    `Fn::Sub` may appear as a plain template string containing
    `${ResourceName}` / `${ResourceName.Attribute}` placeholders, or as
    a two-element list `[template_string, variable_mapping]`.

    Args:
        value: The raw `Fn::Sub` value.
        known_identifiers: The set of known resource logical names in
            the template, used to filter out pseudo parameters (e.g.
            "${AWS::Region}") and user-defined mapping keys.

    Returns:
        A list of resource identifiers referenced by the template
        string's interpolation placeholders.
    """
    template_string = value[0] if isinstance(value, list) and value else value

    if not isinstance(template_string, str):
        return []

    targets: List[str] = []
    for placeholder in _INTERPOLATION_PATTERN.findall(template_string):
        candidate = placeholder.split(".")[0].strip()
        if candidate in known_identifiers:
            targets.append(candidate)

    return targets


def _walk_cloudformation_value(
    value: Any,
    source_name: str,
    known_identifiers: Set[str],
    dependencies: List[Dict[str, str]],
    seen: Set[Tuple[str, str, str]],
) -> None:
    """
    Recursively walk a CloudFormation resource's `Properties` structure,
    detecting intrinsic-function references to other resources.

    Handles `Ref`, `Fn::GetAtt`, `Fn::Sub`, and `Fn::ImportValue`. Any
    other keys are walked transparently in search of nested intrinsic
    functions.

    Args:
        value: The current value being walked.
        source_name: The logical name of the resource that owns this
            property structure.
        known_identifiers: The set of known resource logical names in
            the template.
        dependencies: The accumulator list that detected dependencies
            are appended to. Mutated in place.
        seen: A set of (source, target, relationship) tuples used to
            avoid emitting duplicate dependency records.
    """
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key == "Ref" and isinstance(nested_value, str):
                if nested_value in known_identifiers and nested_value != source_name:
                    _append_cloudformation_dependency(
                        source_name,
                        nested_value,
                        _RELATIONSHIP_REF,
                        dependencies,
                        seen,
                    )
            elif key == "Fn::GetAtt":
                target = _extract_getatt_target(nested_value)
                if target and target in known_identifiers and target != source_name:
                    _append_cloudformation_dependency(
                        source_name,
                        target,
                        _RELATIONSHIP_GET_ATT,
                        dependencies,
                        seen,
                    )
            elif key == "Fn::Sub":
                for target in _extract_sub_targets(nested_value, known_identifiers):
                    if target != source_name:
                        _append_cloudformation_dependency(
                            source_name,
                            target,
                            _RELATIONSHIP_SUB,
                            dependencies,
                            seen,
                        )
                if isinstance(nested_value, list) and len(nested_value) > 1:
                    _walk_cloudformation_value(
                        nested_value[1], source_name, known_identifiers, dependencies, seen
                    )
            elif key == "Fn::ImportValue":
                if isinstance(nested_value, str):
                    _append_cloudformation_dependency(
                        source_name,
                        nested_value,
                        _RELATIONSHIP_IMPORT_VALUE,
                        dependencies,
                        seen,
                    )
                else:
                    _walk_cloudformation_value(
                        nested_value, source_name, known_identifiers, dependencies, seen
                    )
            else:
                _walk_cloudformation_value(
                    nested_value, source_name, known_identifiers, dependencies, seen
                )
    elif isinstance(value, list):
        for item in value:
            _walk_cloudformation_value(item, source_name, known_identifiers, dependencies, seen)


def _append_cloudformation_dependency(
    source: str,
    target: str,
    relationship: str,
    dependencies: List[Dict[str, str]],
    seen: Set[Tuple[str, str, str]],
) -> None:
    """
    Append a CloudFormation dependency record if it has not already
    been recorded.

    Args:
        source: The logical name of the resource holding the reference.
        target: The logical name of the referenced resource or import.
        relationship: The intrinsic function that produced the
            reference (e.g. "Ref", "Fn::GetAtt").
        dependencies: The accumulator list that the record is appended
            to. Mutated in place.
        seen: A set of (source, target, relationship) tuples used to
            avoid emitting duplicate dependency records. Mutated in
            place.
    """
    dedupe_key = (source, target, relationship)
    if dedupe_key in seen:
        return

    seen.add(dedupe_key)
    dependencies.append(
        _build_dependency(
            source=source,
            target=target,
            relationship=relationship,
            provider=_PROVIDER_CLOUDFORMATION,
        )
    )
    logger.debug(
        "Detected CloudFormation dependency: %s -[%s]-> %s", source, relationship, target
    )


def extract_cloudformation_dependencies(
    parsed_data: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Extract resource-to-resource dependencies from a parsed
    CloudFormation template.

    Detects dependencies expressed through `DependsOn`, `Ref`,
    `Fn::GetAtt`, `Fn::Sub`, and `Fn::ImportValue`.

    Expects the input shape produced by `cloudformation_parser.py`,
    e.g.:
        {
            "Resources": {
                "WebServerInstance": {
                    "Type": "AWS::EC2::Instance",
                    "Properties": {"SecurityGroupIds": [{"Ref": "WebServerSecurityGroup"}]}
                }
            }
        }

    Args:
        parsed_data: The parsed CloudFormation template dictionary.

    Returns:
        A list of dependency dictionaries, each with the keys "source",
        "target", "relationship", and "provider". Returns an empty list
        if no `Resources` block is present.

    Raises:
        DependencyExtractorError: If the `Resources` block is present
            but is not in the expected dict shape.
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
        raise DependencyExtractorError(
            f"Invalid CloudFormation 'Resources' block shape: "
            f"{type(resources).__name__}"
        )

    known_identifiers: Set[str] = set(resources.keys())
    dependencies: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()

    for resource_name, resource_definition in resources.items():
        if not isinstance(resource_definition, dict):
            logger.warning(
                "Skipping malformed CloudFormation resource: %s", resource_name
            )
            continue

        depends_on = resource_definition.get("DependsOn")
        if depends_on is not None:
            targets = depends_on if isinstance(depends_on, list) else [depends_on]
            for target in targets:
                if isinstance(target, str):
                    _append_cloudformation_dependency(
                        resource_name,
                        target,
                        _RELATIONSHIP_DEPENDS_ON_CFN,
                        dependencies,
                        seen,
                    )

        properties = resource_definition.get("Properties", {})
        _walk_cloudformation_value(
            properties, resource_name, known_identifiers, dependencies, seen
        )

    logger.info(
        "Extracted %d CloudFormation dependency/dependencies.", len(dependencies)
    )
    return dependencies


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------
def extract_dependencies(
    parsed_data: Dict[str, Any], provider: str
) -> List[Dict[str, str]]:
    """
    Extract resource dependencies from a parsed IaC document, dispatching
    to the appropriate provider-specific extractor.

    This is the main entry point of the module. It routes the parsed
    data to `extract_terraform_dependencies()` or
    `extract_cloudformation_dependencies()` based on the given
    `provider`, and returns a uniform list of dependency dictionaries.

    Args:
        parsed_data: The parsed IaC configuration dictionary, as
            returned by `terraform_parser.parse_terraform_file()` or
            `cloudformation_parser.parse_cloudformation_file()`.
        provider: The IaC provider that produced `parsed_data`. Must be
            one of "Terraform" or "CloudFormation" (case-insensitive).

    Returns:
        A list of dependency dictionaries, each with the keys "source",
        "target", "relationship", and "provider".

    Raises:
        DependencyExtractorError: If `provider` is not a recognized
            value, or if the underlying provider-specific extraction
            fails.
    """
    if not isinstance(parsed_data, dict):
        logger.error(
            "Expected parsed_data to be a dict, got %s", type(parsed_data).__name__
        )
        raise DependencyExtractorError(
            f"Invalid parsed_data type: {type(parsed_data).__name__}"
        )

    normalized_provider = provider.strip().lower()
    logger.info("Starting dependency extraction for provider: %s", provider)

    if normalized_provider == _PROVIDER_TERRAFORM.lower():
        dependencies = extract_terraform_dependencies(parsed_data)
    elif normalized_provider == _PROVIDER_CLOUDFORMATION.lower():
        dependencies = extract_cloudformation_dependencies(parsed_data)
    else:
        logger.error("Unsupported provider requested: %s", provider)
        raise DependencyExtractorError(
            f"Unsupported provider: {provider} (expected 'Terraform' or "
            f"'CloudFormation')"
        )

    logger.info("Completed dependency extraction for provider: %s", provider)
    return dependencies


# ---------------------------------------------------------------------------
# Script entry point (manual/local testing convenience)
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Simple command-line entry point for manually testing the dependency
    extractor against a Terraform or CloudFormation file.

    Usage:
        python dependency_extractor.py <path_to_tf_or_cfn_file>
    """
    import sys

    if len(sys.argv) != 2:
        logger.error("Usage: python dependency_extractor.py <path_to_tf_or_cfn_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        if file_path.endswith(".tf"):
            from .terraform_parser import parse_terraform_file

            parsed_data = parse_terraform_file(file_path)
            dependencies = extract_dependencies(parsed_data, provider=_PROVIDER_TERRAFORM)
        elif file_path.endswith((".yaml", ".yml", ".json")):
            from .cloudformation_parser import parse_cloudformation_file

            parsed_data = parse_cloudformation_file(file_path)
            dependencies = extract_dependencies(
                parsed_data, provider=_PROVIDER_CLOUDFORMATION
            )
        else:
            logger.error("Unsupported file type: %s", file_path)
            sys.exit(1)

        print(dependencies)
    except DependencyExtractorError as exc:
        logger.error("Dependency extraction failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
