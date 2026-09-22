"""Built-in deterministic IaC security checks (Module 3).

Why this exists
---------------
The normal upload flow wires Checkov as the Module 3 security validator
(``src/ml_model/api.py``). On machines where the optional Checkov binary is
not installed, every upload degrades to "Module 3 validator unavailable"
and the pipeline runs with an empty ``validation_reports`` tuple. All
agents then see no static findings, so materially different uploads
produce identical reports (security 100, readiness 45, confidence ~0.59).

This adapter implements a small, deterministic, offline rule set so the
standard upload path produces content-derived findings without installing
anything new and without touching the M1-M9 scoring logic.

Design constraints:
  * Parsing reuses the existing Module 1 parser and Module 2 UIR
    (``process_iac_file`` + ``build_uir``) — the exact same normalized
    resource shapes the rest of the pipeline consumes. No duplicate
    parsing logic, no hcl2-version quirks.
  * Findings carry ``tool="IAC_BUILTIN"`` — never mislabeled as Checkov.
  * Findings derive only from the actual uploaded configuration; no
    runtime, drift, or score is invented here.
  * Deterministic: the same input always yields the same findings.
  * The absence of a finding means the pattern was not present in the
    file, not that the resource is certified secure.

Rule severity aligns with the penalties Module 8 already applies
(CRITICAL 45, HIGH 25, MEDIUM 10, LOW 3 — ``engine.py::_security``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module3_static_validation.validation_result import build_report
from src.ml_model.module3_static_validation.validation_schema import (
    ValidationFinding,
    ValidationSeverity,
    ValidationStatus,
)

TOOL_NAME = "IAC_BUILTIN"

_SCAN_EXTENSIONS = {".tf", ".yaml", ".yml", ".json"}

# Severity ladder mirrors the penalties M8 applies (engine.py::_security):
# CRITICAL 45, HIGH 25, MEDIUM 10, LOW 3.
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}
_PUBLIC_ACLS = {"public-read", "public-read-write", "authenticated-read"}


def _unwrap(value: Any) -> Any:
    """Unwrap single-element lists (python-hcl2 artifacts surviving normalization)."""
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    return value


def _text(value: Any) -> str:
    return str(_unwrap(value)).strip().strip('"').strip("'")


def _blocks(value: Any) -> List[Dict[str, Any]]:
    """Return the dict blocks inside a repeated-block attribute value."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _cidrs(block: Dict[str, Any], key: str) -> set[str]:
    raw = _unwrap(block.get(key, ()))
    if isinstance(raw, (list, tuple)):
        return {_text(item) for item in raw}
    return {_text(raw)} if raw != "" else set()


def _port_range(block: Dict[str, Any], from_key: str, to_key: str) -> Optional[Tuple[int, int]]:
    try:
        from_port = int(float(_unwrap(block.get(from_key, 0))))
        to_port = int(float(_unwrap(block.get(to_key, 0))))
    except (TypeError, ValueError):
        return None
    return from_port, to_port


# ---------------------------------------------------------------------------
# Terraform checks. Each returns (rule_id, severity, message) or None.
# ---------------------------------------------------------------------------

def _tf_s3_public_acl(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    value = _text(props.get("acl", ""))
    if value in _PUBLIC_ACLS:
        return (
            "TF_S3_PUBLIC_ACL",
            ValidationSeverity.HIGH,
            f"S3 bucket ACL grants public access (acl='{value}'); use a private ACL with block-public-access settings.",
        )
    return None


def _tf_s3_unencrypted(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    if "server_side_encryption_configuration" not in props:
        return (
            "TF_S3_UNENCRYPTED",
            ValidationSeverity.MEDIUM,
            "S3 bucket has no server_side_encryption_configuration; enable AES256 or aws:kms encryption at rest.",
        )
    return None


def _tf_sg_open_ingress(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("ingress")):
        for cidr in _cidrs(block, "cidr_blocks") & _OPEN_CIDRS:
            return (
                "TF_SG_WORLD_OPEN_INGRESS",
                ValidationSeverity.HIGH,
                f"Security group ingress is open to the internet (cidr '{cidr}') — restrict source CIDR ranges.",
            )
    return None


def _tf_sg_ssh_open(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("ingress")):
        if not (_cidrs(block, "cidr_blocks") & _OPEN_CIDRS):
            continue
        ports = _port_range(block, "from_port", "to_port")
        if ports and ports[0] <= 22 <= ports[1]:
            return (
                "TF_SG_SSH_WORLD_OPEN",
                ValidationSeverity.HIGH,
                f"Security group allows SSH (port 22) from anywhere (port range {ports[0]}-{ports[1]}) — restrict to management networks.",
            )
    return None


def _tf_sg_open_egress(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("egress")):
        for cidr in _cidrs(block, "cidr_blocks") & _OPEN_CIDRS:
            return (
                "TF_SG_WORLD_OPEN_EGRESS",
                ValidationSeverity.LOW,
                f"Security group egress allows all destinations (cidr '{cidr}').",
            )
    return None


def _tf_imdsv1_allowed(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    options = _blocks(props.get("metadata_options"))
    if not options:
        # AWS defaults allow IMDSv1 when metadata_options is unset.
        return (
            "TF_IMDSV1_ALLOWED",
            ValidationSeverity.LOW,
            'EC2 instance metadata service allows IMDSv1 (metadata_options unset); set http_tokens = "required".',
        )
    for block in options:
        tokens = _text(block.get("http_tokens", "")).lower()
        if tokens != "required":
            return (
                "TF_IMDSV1_ALLOWED",
                ValidationSeverity.LOW,
                f"EC2 instance metadata service allows IMDSv1 (http_tokens='{tokens or 'unset'}'); set http_tokens = \"required\".",
            )
    return None


def _tf_root_volume_unencrypted(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    # Absent block means encryption is not explicitly enabled on the root
    # volume, matching how Checkov treats unset encryption attributes.
    blocks = _blocks(props.get("root_block_device"))
    if not blocks:
        return (
            "TF_ROOT_VOLUME_UNENCRYPTED",
            ValidationSeverity.MEDIUM,
            "EC2 instance does not explicitly encrypt its root EBS volume (root_block_device unset); set root_block_device.encrypted = true.",
        )
    for block in blocks:
        encrypted = _unwrap(block.get("encrypted", None))
        if encrypted is not True and _text(encrypted).lower() != "true":
            return (
                "TF_ROOT_VOLUME_UNENCRYPTED",
                ValidationSeverity.MEDIUM,
                "EC2 instance root EBS volume is not encrypted; set root_block_device.encrypted = true.",
            )
    return None


_TERRAFORM_CHECKS = {
    "aws_s3_bucket": (_tf_s3_public_acl, _tf_s3_unencrypted),
    "aws_security_group": (_tf_sg_open_ingress, _tf_sg_ssh_open, _tf_sg_open_egress),
    "aws_instance": (_tf_imdsv1_allowed, _tf_root_volume_unencrypted),
}


# ---------------------------------------------------------------------------
# CloudFormation checks (same semantics, CFN property names).
# ---------------------------------------------------------------------------

def _cfn_bucket_public_acl(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    value = _text(props.get("AccessControl", ""))
    if value.replace("_", "").lower() in {"publicread", "publicreadwrite", "authenticatedread"}:
        return (
            "CFN_S3_PUBLIC_ACL",
            ValidationSeverity.HIGH,
            f"S3 bucket grants public access (AccessControl='{value}'); use a private ACL with PublicAccessBlock configuration.",
        )
    return None


def _cfn_bucket_unencrypted(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    if "BucketEncryption" not in props:
        return (
            "CFN_S3_UNENCRYPTED",
            ValidationSeverity.MEDIUM,
            "S3 bucket has no BucketEncryption configuration; enable SSE-S3 or SSE-KMS encryption at rest.",
        )
    return None


def _cfn_sg_open_ingress(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("SecurityGroupIngress")):
        for key in ("CidrIp", "CidrIpv6"):
            if _text(block.get(key, "")) in _OPEN_CIDRS:
                return (
                    "CFN_SG_WORLD_OPEN_INGRESS",
                    ValidationSeverity.HIGH,
                    f"Security group ingress is open to the internet ({key}='{block.get(key)}') — restrict source CIDR ranges.",
                )
    return None


def _cfn_sg_ssh_open(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("SecurityGroupIngress")):
        if not any(_text(block.get(key, "")) in _OPEN_CIDRS for key in ("CidrIp", "CidrIpv6")):
            continue
        ports = _port_range(block, "FromPort", "ToPort")
        if ports and ports[0] <= 22 <= ports[1]:
            return (
                "CFN_SG_SSH_WORLD_OPEN",
                ValidationSeverity.HIGH,
                f"Security group allows SSH (port 22) from anywhere (port range {ports[0]}-{ports[1]}) — restrict to management networks.",
            )
    return None


def _cfn_sg_open_egress(props: Dict[str, Any]) -> Optional[Tuple[str, ValidationSeverity, str]]:
    for block in _blocks(props.get("SecurityGroupEgress")):
        for key in ("CidrIp", "CidrIpv6"):
            if _text(block.get(key, "")) in _OPEN_CIDRS:
                return (
                    "CFN_SG_WORLD_OPEN_EGRESS",
                    ValidationSeverity.LOW,
                    f"Security group egress allows all destinations ({key}='{block.get(key)}').",
                )
    return None


_CFN_CHECKS = {
    "AWS::S3::Bucket": (_cfn_bucket_public_acl, _cfn_bucket_unencrypted),
    "AWS::EC2::SecurityGroup": (_cfn_sg_open_ingress, _cfn_sg_ssh_open, _cfn_sg_open_egress),
}


def _finding(
    provider: str,
    resource_id: str,
    result: Tuple[str, ValidationSeverity, str],
) -> ValidationFinding:
    rule_id, severity, message = result
    return ValidationFinding(
        tool=TOOL_NAME,
        provider=provider,
        status=ValidationStatus.FAILED,
        severity=severity,
        rule_id=rule_id,
        message=message,
        resource_id=resource_id,
    )


def _scan_resource(findings: List[ValidationFinding], resource: Dict[str, Any]) -> None:
    provider = str(resource.get("provider") or "Terraform")
    resource_type = str(resource.get("type") or "")
    resource_id = str(resource.get("id") or resource.get("name") or "unknown")
    properties = resource.get("properties") or {}
    checks = (
        _CFN_CHECKS.get(resource_type)
        if provider == "CloudFormation"
        else _TERRAFORM_CHECKS.get(resource_type)
    )
    for check in checks or ():
        result = check(properties)
        if result is not None:
            findings.append(_finding(provider, resource_id, result))


def _scan_file(path: Path, findings: List[ValidationFinding]) -> bool:
    """Parse one file through M1+M2 and run the checks on its UIR resources.

    Returns True when the file was parsed, False when M1 could not handle
    it (unparseable input contributes no builtin findings; syntax-level
    problems remain the syntax agents' domain).
    """
    try:
        resources = build_uir(process_iac_file(str(path)))["resources"]
    except Exception:
        return False
    for resource in resources:
        if isinstance(resource, dict):
            _scan_resource(findings, resource)
    return True


class BuiltinSecurityAdapter:
    """Module 3 validator adapter over the built-in deterministic rule set.

    Accepts a file OR a directory (the orchestrator passes ``source.parent``
    to non-CFNLint validators). Scans every ``.tf``/``.yaml``/``.yml``/
    ``.json`` file and returns one merged ``ValidationReport``.
    """

    def validate(self, path: Any) -> Any:
        target = Path(path)
        files = (
            sorted(
                p for p in target.iterdir()
                if p.suffix.lower() in _SCAN_EXTENSIONS and p.is_file()
            )
            if target.is_dir()
            else [target]
        )
        findings: List[ValidationFinding] = []
        providers: set[str] = set()
        for file_path in files:
            before = len(findings)
            if _scan_file(file_path, findings):
                providers.update(finding.provider for finding in findings[before:])
        provider = providers.pop() if len(providers) == 1 else (next(iter(providers)) if providers else "Terraform")
        return build_report(provider=provider, findings=findings)
