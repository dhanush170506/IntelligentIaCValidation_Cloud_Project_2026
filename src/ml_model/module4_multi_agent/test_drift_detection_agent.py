"""Tests for Configuration Drift Detection Agent."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_schema import AgentSeverity, AgentStatus, AgentType
from drift_detection_agent import DriftDetectionAgent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def desired_uir():
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
                "properties": {
                    "name": "web-sg",
                    "ingress": {"port": 80},
                },
            },
            {
                "id": "aws_instance.web_server",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "web_server",
                "properties": {
                    "ami": "ami-example",
                    "instance_type": "t3.micro",
                    "tags": {"Name": "web-server"},
                },
            },
        ],
        "dependencies": [],
    }


def observed_clean():
    return {
        "resources": [
            {
                "id": "aws_security_group.web_sg",
                "properties": {
                    "name": "web-sg",
                    "ingress": {"port": 80},
                },
            },
            {
                "id": "aws_instance.web_server",
                "properties": {
                    "ami": "ami-example",
                    "instance_type": "t3.micro",
                    "tags": {"Name": "web-server"},
                },
            },
        ]
    }


def rules(result):
    return [f.rule_id for f in result.findings]


def main() -> None:
    agent = DriftDetectionAgent()

    result = agent.run(uir=desired_uir(), observed_state=observed_clean())
    check(result.agent_type == AgentType.DRIFT_DETECTION, "Agent type is correct")
    check(result.status == AgentStatus.COMPLETED, "Clean comparison completes")
    check(result.findings == (), "Clean comparison has no findings")
    check(result.confidence == 1.0, "Clean comparison confidence is 1.0")

    observed = observed_clean()
    observed["resources"].pop(1)
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_MISSING_RESOURCE" in rules(result), "Missing resource is detected")
    check(any(f.severity == AgentSeverity.CRITICAL for f in result.findings),
          "Missing resource is CRITICAL")

    observed = observed_clean()
    observed["resources"].append({
        "id": "aws_instance.unmanaged",
        "properties": {"instance_type": "t3.nano"},
    })
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_UNEXPECTED_RESOURCE" in rules(result),
          "Unexpected runtime resource is detected")

    observed = observed_clean()
    observed["resources"][1]["properties"]["instance_type"] = "t3.large"
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_PROPERTY_CHANGE" in rules(result),
          "Changed property is detected")
    check(any(f.severity == AgentSeverity.HIGH for f in result.findings),
          "Instance type drift is HIGH severity")

    observed = observed_clean()
    del observed["resources"][1]["properties"]["tags"]
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_PROPERTY_CHANGE" in rules(result),
          "Removed desired property is detected")

    observed = observed_clean()
    observed["resources"][0]["properties"]["extra_runtime_setting"] = True
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_PROPERTY_CHANGE" in rules(result),
          "Added runtime property is detected")

    observed = observed_clean()
    observed["resources"][1]["properties"]["tags"]["Environment"] = "production"
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_PROPERTY_CHANGE" in rules(result),
          "Nested property drift is detected")

    observed = observed_clean()
    observed["resources"].append({
        "id": "aws_instance.web_server",
        "properties": {},
    })
    result = agent.run(uir=desired_uir(), observed_state=observed)
    check("DRIFT_DUPLICATE_RESOURCE_ID" in rules(result),
          "Duplicate observed resource ID is detected")

    invalid = agent.run(uir=desired_uir(), observed_state=None)
    check(invalid.status == AgentStatus.FAILED,
          "Missing observed state returns FAILED result")
    check("observed_state is required" in invalid.message,
          "Failure message identifies missing observed state")

    print("All Configuration Drift Detection Agent tests PASSED.")


if __name__ == "__main__":
    main()
