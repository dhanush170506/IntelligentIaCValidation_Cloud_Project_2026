# IntelligentIaCValidation_Cloud_Project_2026

## Dataset evaluation and pipeline mapping

This repository contains an evidence-driven IaC assurance pipeline for Terraform and AWS CloudFormation templates. The system keeps the existing single-file validation flow and adds a dataset evaluation workflow that reuses the same pipeline stages.

### Repository dataset

- dataset/data.csv: repository metadata with Terraform prompt and rule intent examples.
- dataset/test.csv: CloudFormation sample metadata and expected remediation targets.
- dataset/terragoat-master/terraform: real Terraform working examples used as pipeline inputs.
- benchmarks/independent_fixtures: deterministic Terraform benchmark cases.

These CSV files are metadata records, not directly executable IaC, and are converted into pipeline-compatible samples by reading their `initial` or `source` payloads and preserving the original metadata as sample metadata.

### Mapping to the assurance pipeline

Dataset sample
-> M1 IaC parser
-> M2 UIR/resource graph
-> M3 static validation
-> M4 multi-agent validation
-> M5 LLM reasoning
-> M6 runtime telemetry / drift analysis
-> M7 consensus / blast radius / remediation gate
-> M8 recommendations
-> M9 evaluation metrics

The implementation reuses `AssuranceOrchestrator` and wraps it in a dataset batch service instead of duplicating the pipeline stages.

### Backend API

- POST /validate: single-file validation
- POST /dataset-evaluations: start a dataset run
- GET /dataset-evaluations: list previous runs
- GET /dataset-evaluations/{run_id}: current status
- GET /dataset-evaluations/{run_id}/results: per-sample results
- GET /dashboard: aggregate validation and dataset metrics

### Offline / mock-safe behavior

The default pipeline continues to use the local mock Bedrock and runtime providers. Real AWS Bedrock behavior is only enabled when explicitly configured and is never assumed by default.

### Metrics

The backend records only metrics supported by the dataset and pipeline. Where no ground-truth labels are available, aggregate metrics remain descriptive pipeline metrics rather than classification metrics.
