"""
provider_mapper.py

A production-ready provider-to-canonical resource type mapper for the
Unified Intermediate Representation (UIR).

Module 1's parsers and extractors deliberately preserve each provider's
native resource type string unchanged (e.g. Terraform's "aws_instance"
or CloudFormation's "AWS::EC2::Instance") — that is correct for Module
1, whose job is faithful extraction, not interpretation. Module 2
builds a provider-agnostic representation on top of that data, so
every downstream module (Graph Construction, the Validation Engine,
the Multi-Agent Framework, LLM Integration) needs a single, canonical
resource type per real-world concept (e.g. "compute_instance"),
regardless of which IaC provider originally declared it.

This module performs that translation and nothing else: it does not
parse, extract, or validate IaC documents, and it never raises on an
unrecognized resource type — an unmapped type is returned unchanged so
that resources from providers not yet covered by `RESOURCE_TYPE_MAPPING`
(e.g. Azure ARM, Pulumi) continue to flow through the pipeline without
being dropped or blocked.

Requirements:
    - Python 3.12

Typical usage:
    from provider_mapper import get_canonical_resource_type

    canonical_type = get_canonical_resource_type("aws_instance")
    # -> "compute_instance"

    canonical_type = get_canonical_resource_type("AWS::EC2::Instance")
    # -> "compute_instance"
"""

from __future__ import annotations

import logging
from typing import Dict

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
class ProviderMapperError(Exception):
    """Base exception for all errors raised by the provider mapper."""


# ---------------------------------------------------------------------------
# Canonical resource type labels
# ---------------------------------------------------------------------------
# Each canonical label represents one real-world infrastructure concept,
# independent of which IaC provider declared it. Declared once here so
# the mapping table below never repeats a canonical string literal.
_CANONICAL_COMPUTE_INSTANCE = "compute_instance"
_CANONICAL_SECURITY_GROUP = "security_group"
_CANONICAL_STORAGE_BUCKET = "storage_bucket"
_CANONICAL_VIRTUAL_NETWORK = "virtual_network"
_CANONICAL_SUBNET = "subnet"
_CANONICAL_INTERNET_GATEWAY = "internet_gateway"
_CANONICAL_ROUTE_TABLE = "route_table"
_CANONICAL_IAM_ROLE = "iam_role"
_CANONICAL_SERVERLESS_FUNCTION = "serverless_function"
_CANONICAL_DATABASE_INSTANCE = "database_instance"
_CANONICAL_LOAD_BALANCER = "load_balancer"
_CANONICAL_AUTO_SCALING_GROUP = "auto_scaling_group"


# ---------------------------------------------------------------------------
# Provider-specific resource type -> canonical UIR resource type
# ---------------------------------------------------------------------------
# Keys are the exact resource type strings as produced by Module 1's
# extractors (Terraform's `type` values from `resource_extractor.py`,
# CloudFormation's `Type` values from the same). Unrecognized keys are
# intentionally absent — `get_canonical_resource_type()` falls back to
# returning the original string unchanged for anything not listed here,
# so new providers or new resource types never need a code change to
# keep flowing through the pipeline.
RESOURCE_TYPE_MAPPING: Dict[str, str] = {
    # -- Terraform --------------------------------------------------------
    "aws_instance": _CANONICAL_COMPUTE_INSTANCE,
    "aws_security_group": _CANONICAL_SECURITY_GROUP,
    "aws_s3_bucket": _CANONICAL_STORAGE_BUCKET,
    "aws_vpc": _CANONICAL_VIRTUAL_NETWORK,
    "aws_subnet": _CANONICAL_SUBNET,
    "aws_internet_gateway": _CANONICAL_INTERNET_GATEWAY,
    "aws_route_table": _CANONICAL_ROUTE_TABLE,
    "aws_iam_role": _CANONICAL_IAM_ROLE,
    "aws_lambda_function": _CANONICAL_SERVERLESS_FUNCTION,
    "aws_db_instance": _CANONICAL_DATABASE_INSTANCE,
    "aws_lb": _CANONICAL_LOAD_BALANCER,
    "aws_autoscaling_group": _CANONICAL_AUTO_SCALING_GROUP,
    # -- CloudFormation -----------------------------------------------------
    "AWS::EC2::Instance": _CANONICAL_COMPUTE_INSTANCE,
    "AWS::EC2::SecurityGroup": _CANONICAL_SECURITY_GROUP,
    "AWS::S3::Bucket": _CANONICAL_STORAGE_BUCKET,
    "AWS::EC2::VPC": _CANONICAL_VIRTUAL_NETWORK,
    "AWS::EC2::Subnet": _CANONICAL_SUBNET,
    "AWS::EC2::InternetGateway": _CANONICAL_INTERNET_GATEWAY,
    "AWS::EC2::RouteTable": _CANONICAL_ROUTE_TABLE,
    "AWS::IAM::Role": _CANONICAL_IAM_ROLE,
    "AWS::Lambda::Function": _CANONICAL_SERVERLESS_FUNCTION,
    "AWS::RDS::DBInstance": _CANONICAL_DATABASE_INSTANCE,
    "AWS::ElasticLoadBalancingV2::LoadBalancer": _CANONICAL_LOAD_BALANCER,
    "AWS::AutoScaling::AutoScalingGroup": _CANONICAL_AUTO_SCALING_GROUP,
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _validate_resource_type(resource_type: str) -> str:
    """
    Validate that a resource type value is a non-empty string.

    Args:
        resource_type: The provider-specific resource type string to
            validate.

    Returns:
        `resource_type` unchanged.

    Raises:
        ProviderMapperError: If `resource_type` is not a non-empty
            string.
    """
    if not isinstance(resource_type, str) or not resource_type.strip():
        logger.error("Invalid resource type value: %r", resource_type)
        raise ProviderMapperError(f"Invalid resource type value: {resource_type!r}")

    return resource_type


def get_canonical_resource_type(resource_type: str) -> str:
    """
    Translate a provider-specific resource type into its canonical UIR
    resource type.

    This is the main entry point of the module. If `resource_type` is
    found in `RESOURCE_TYPE_MAPPING`, the corresponding canonical type
    is returned. If it is not found — including resource types from
    providers not yet covered by this mapping — `resource_type` is
    returned unchanged, so unknown types are never dropped or blocked.

    Args:
        resource_type: The provider-specific resource type string (e.g.
            "aws_instance" or "AWS::EC2::Instance").

    Returns:
        The canonical UIR resource type if a mapping exists, otherwise
        `resource_type` unchanged.

    Raises:
        ProviderMapperError: If `resource_type` is not a non-empty
            string.
    """
    validated_type = _validate_resource_type(resource_type)

    canonical_type = RESOURCE_TYPE_MAPPING.get(validated_type)

    if canonical_type is None:
        logger.debug(
            "No canonical mapping found for '%s'; returning unchanged.", validated_type
        )
        return validated_type

    logger.debug("Mapped '%s' to canonical type '%s'.", validated_type, canonical_type)
    return canonical_type


def is_supported_resource_type(resource_type: str) -> bool:
    """
    Check whether a provider-specific resource type has a known
    canonical mapping.

    Args:
        resource_type: The provider-specific resource type string to
            check.

    Returns:
        True if `resource_type` is present in `RESOURCE_TYPE_MAPPING`,
        False otherwise.

    Raises:
        ProviderMapperError: If `resource_type` is not a non-empty
            string.
    """
    validated_type = _validate_resource_type(resource_type)
    is_supported = validated_type in RESOURCE_TYPE_MAPPING

    logger.debug(
        "Checked resource type support for '%s': %s", validated_type, is_supported
    )
    return is_supported

__all__ = [
    "ProviderMapperError",
    "RESOURCE_TYPE_MAPPING",
    "get_canonical_resource_type",
    "is_supported_resource_type",
]