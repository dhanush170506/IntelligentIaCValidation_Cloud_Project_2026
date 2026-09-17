"""
schema_constants.py

Centralized schema key constants for the Unified Intermediate
Representation (UIR).

Module 1 (`terraform_parser.py`, `cloudformation_parser.py`,
`resource_extractor.py`, `dependency_extractor.py`, `json_normalizer.py`,
`parser_manager.py`) produces a normalized JSON object with a fixed set
of dictionary keys (e.g. `"provider"`, `"resources"`, `"source"`). Module
2 (the Unified Intermediate Representation) and every module built on
top of it consume that same schema repeatedly.

Rather than hardcoding these key strings throughout the codebase — where
a typo or an inconsistent rename could silently break a downstream
module — every constant is declared once here and imported everywhere
else. This file defines no classes, no functions, and no logic: it is a
single source of truth for schema key names only.

Requirements:
    - Python 3.12

Typical usage:
    from schema_constants import KEY_PROVIDER, KEY_RESOURCES

    provider = normalized_data[KEY_PROVIDER]
    resources = normalized_data[KEY_RESOURCES]
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Top-level normalized JSON keys
# ---------------------------------------------------------------------------
# Keys present at the root of the object returned by
# `json_normalizer.normalize_json()` / `parser_manager.process_iac_file()`.
KEY_PROVIDER: str = "provider"          # IaC provider label ("Terraform" or "CloudFormation")
KEY_METADATA: str = "metadata"          # Summary metadata block
KEY_RESOURCES: str = "resources"        # List of extracted resource records
KEY_DEPENDENCIES: str = "dependencies"  # List of extracted dependency records

# ---------------------------------------------------------------------------
# Metadata block keys
# ---------------------------------------------------------------------------
# Keys nested under KEY_METADATA.
KEY_RESOURCE_COUNT: str = "resource_count"      # Number of entries in KEY_RESOURCES
KEY_DEPENDENCY_COUNT: str = "dependency_count"  # Number of entries in KEY_DEPENDENCIES

# ---------------------------------------------------------------------------
# Resource record keys
# ---------------------------------------------------------------------------
# Keys present on each dictionary within the KEY_RESOURCES list.
KEY_RESOURCE_ID: str = "id"          # Unique identifier assigned to a resource in the UIR
KEY_RESOURCE_NAME: str = "name"      # Resource's logical/declared name
KEY_RESOURCE_TYPE: str = "type"      # Resource's IaC type (e.g. "aws_instance", "AWS::EC2::Instance")
KEY_PROPERTIES: str = "properties"   # Resource's raw, unmodified property block

# ---------------------------------------------------------------------------
# Dependency record keys
# ---------------------------------------------------------------------------
# Keys present on each dictionary within the KEY_DEPENDENCIES list.
KEY_SOURCE: str = "source"            # Identifier of the resource holding the reference
KEY_TARGET: str = "target"            # Identifier of the referenced resource
KEY_RELATIONSHIP: str = "relationship"  # Kind of reference (e.g. "depends_on", "Ref", "Fn::GetAtt")
KEY_NODES: str = "nodes"
KEY_EDGES: str = "edges"

KEY_NODE_ID: str = "id"
KEY_EDGE_ID: str = "id"

KEY_CANONICAL_TYPE: str = "canonical_type"

KEY_UIR_VERSION: str = "uir_version"
# ---------------------------------------------------------------------------
# Public export list
# ---------------------------------------------------------------------------
__all__ = [
    # Top-level normalized JSON keys
    "KEY_PROVIDER",
    "KEY_METADATA",
    "KEY_RESOURCES",
    "KEY_DEPENDENCIES",
    # Metadata block keys
    "KEY_RESOURCE_COUNT",
    "KEY_DEPENDENCY_COUNT",
    # Resource record keys
    "KEY_RESOURCE_ID",
    "KEY_RESOURCE_NAME",
    "KEY_RESOURCE_TYPE",
    "KEY_PROPERTIES",
    # Dependency record keys
    "KEY_SOURCE",
    "KEY_TARGET",
    "KEY_RELATIONSHIP",
    "KEY_NODES",
    "KEY_EDGES",

    "KEY_NODE_ID",
    "KEY_EDGE_ID",

    "KEY_CANONICAL_TYPE",

    "KEY_UIR_VERSION"
]
