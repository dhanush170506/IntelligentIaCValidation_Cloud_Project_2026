"""Tests for Deployment Validation Agent."""

from __future__ import annotations

import sys
from pathlib import Path

# Support direct execution from /mnt/data and package-style imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deployment_validation_agent import DeploymentValidationAgent
from agent_schema import AgentSeverity, AgentStatus, AgentType


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def clean_uir():
    return {
        "provider": "Terraform",
        "metadata": {"resource_count": 2, "dependency_count": 1},
        "resources": [
            {
                "id": "aws_security_group.web_sg",
                "provider": "Terraform",
                "type": "aws_security_group",
                "canonical_type": "security_group",
                "name": "web_sg",
                "properties": {"name": "web-sg"},
            },
            {
                "id": "aws_instance.web_server",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "web_server",
                "properties": {
                    "ami": "ami-example",
                    "vpc_security_group_ids": ["${aws_security_group.web_sg.id}"],
                },
            },
        ],
        "dependencies": [
            {
                "source": "aws_instance.web_server",
                "target": "aws_security_group.web_sg",
                "relationship": "depends_on",
                "provider": "Terraform",
            }
        ],
    }


def finding_rules(result):
    return {finding.rule_id for finding in result.findings}


def main() -> None:
    agent = DeploymentValidationAgent()

    result = agent.run(uir=clean_uir())
    check(result.agent_type == AgentType.DEPLOYMENT_VALIDATION, "Agent type is correct")
    check(result.status == AgentStatus.COMPLETED, "Clean UIR completes successfully")
    check(result.findings == (), "Clean UIR has no deployment findings")
    check(result.confidence == 1.0, "Clean UIR confidence is 1.0")

    uir = clean_uir()
    uir["dependencies"].append({
        "source": "aws_instance.web_server",
        "target": "aws_missing.missing",
        "relationship": "depends_on",
        "provider": "Terraform",
    })
    result = agent.run(uir=uir)
    check("DEPLOYMENT_UNKNOWN_DEPENDENCY_TARGET" in finding_rules(result),
          "Unknown dependency target is detected")
    check(any(f.severity == AgentSeverity.HIGH for f in result.findings),
          "Unknown dependency target has HIGH severity")

    uir = clean_uir()
    uir["dependencies"] = [
        {
            "source": "aws_instance.web_server",
            "target": "aws_security_group.web_sg",
            "relationship": "depends_on",
            "provider": "AWS",
        }
    ]
    result = agent.run(uir=uir)
    check("DEPLOYMENT_PROVIDER_MISMATCH" in finding_rules(result),
          "Dependency provider mismatch is detected")

    uir = clean_uir()
    uir["dependencies"] = [
        {
            "source": "aws_instance.web_server",
            "target": "aws_instance.web_server",
            "relationship": "depends_on",
            "provider": "Terraform",
        }
    ]
    result = agent.run(uir=uir)
    check("DEPLOYMENT_SELF_DEPENDENCY" in finding_rules(result),
          "Self dependency is detected")
    check(any(f.severity == AgentSeverity.CRITICAL for f in result.findings),
          "Self dependency has CRITICAL severity")

    uir = clean_uir()
    uir["dependencies"] = [
        {
            "source": "aws_instance.web_server",
            "target": "aws_security_group.web_sg",
            "relationship": "depends_on",
            "provider": "Terraform",
        },
        {
            "source": "aws_security_group.web_sg",
            "target": "aws_instance.web_server",
            "relationship": "depends_on",
            "provider": "Terraform",
        },
    ]
    result = agent.run(uir=uir)
    check("DEPLOYMENT_DEPENDENCY_CYCLE" in finding_rules(result),
          "Dependency cycle is detected")
    check(sum(1 for f in result.findings if f.rule_id == "DEPLOYMENT_DEPENDENCY_CYCLE") == 2,
          "All cycle resources are reported")

    uir = clean_uir()
    uir["resources"][1]["properties"]["bad"] = "${aws.missing.id}"
    result = agent.run(uir=uir)
    check("DEPLOYMENT_UNRESOLVED_REFERENCE" in finding_rules(result),
          "Unresolved resource reference is detected")

    uir = clean_uir()
    uir["resources"][0]["canonical_type"] = ""
    result = agent.run(uir=uir)
    check("DEPLOYMENT_MISSING_CANONICAL_TYPE" in finding_rules(result),
          "Missing canonical type is detected")

    invalid = agent.run(uir=None)
    check(invalid.status == AgentStatus.FAILED, "Invalid input returns FAILED result")
    check("uir must be a mapping" in invalid.message,
          "Invalid input message identifies the UIR problem")

    print("All Deployment Validation Agent tests PASSED.")


if __name__ == "__main__":
    main()
