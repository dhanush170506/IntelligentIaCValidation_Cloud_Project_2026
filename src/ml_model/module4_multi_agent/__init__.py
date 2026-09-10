"""module4_multi_agent.

Module 4 of the Telemetry-Aware Multi-Agent Infrastructure-as-Code
Assurance System for Smart Manufacturing Cloud Environments.

This package implements the foundation of the Intelligent Multi-Agent
Framework: the standardized result schema (`AgentFinding`,
`AgentResult`) and the abstract execution lifecycle (`BaseAgent`) that
the future Coordinator Agent and every specialized agent (syntax
validation, security validation, deployment validation, drift
detection, cost analysis, evidence collection) will be built on.

Module 4 receives structured outputs from Modules 1-3:
    - Module 1: parsed IaC.
    - Module 2: the Unified Intermediate Representation (UIR), the
      resource graph, and the dependency graph.
    - Module 3: `ValidationReport`, `ValidationFinding`, and
      `ValidationSummary`.

and converts them into standardized multi-agent execution results. It
does not itself call Terraform, Checkov, TFLint, CFN-Lint, any AWS API
(including CloudWatch, AWS Config, or Bedrock), or any LLM — those
integrations belong to the concrete agents built on this foundation.

Currently implemented:
    - agent_schema: the standardized internal finding schema
      (`AgentType`, `AgentStatus`, `AgentSeverity`, `AgentFinding`)
      that `agent_result.py` and every future agent build on.
    - agent_result: `AgentResult`, representing the complete output of
      one agent execution.
    - base_agent: `BaseAgent`, the abstract base class providing the
      common `PENDING -> RUNNING -> COMPLETED`/`FAILED` execution
      lifecycle every future agent shares.

Not yet implemented (a later task):
    - The Coordinator Agent.
    - Any specialized agent (syntax validation, security validation,
      deployment validation, drift detection, cost analysis, evidence
      collection).
"""
