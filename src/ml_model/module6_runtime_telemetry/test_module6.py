"""Offline Module 6 verification; run as a module from project root."""
from __future__ import annotations

from src.ml_model.module6_runtime_telemetry import *


def uir():
    return {"provider": "Terraform", "resources": [{"id": "aws_instance.web", "type": "aws_instance", "canonical_type": "compute_instance", "properties": {"instance_type": "t3.micro", "tags": {"Environment": "production"}}}], "graph": {"edges": []}}

class FakeCloudWatchClient:

    def __init__(self):
        self.queries = []

    def get_metric_statistics(self, **kwargs):
        self.queries.append(kwargs)
        return {"Datapoints": []}

def test_cloudwatch_query_contains_time_window():

    client = FakeCloudWatchClient()

    provider = AwsCloudWatchProvider(
        client=client,
        lookback_minutes=60,
        period_seconds=300,
    )

    resource = {
        "id": "aws_instance.web",
        "type": "aws_instance",
        "canonical_type": "compute_instance",
        "properties": {},
    }

    provider.collect(resource)

    assert len(client.queries) > 0

    query = client.queries[0]

    assert "StartTime" in query
    assert "EndTime" in query
    assert "Period" in query

    assert query["Period"] == 300
    assert query["EndTime"] > query["StartTime"]


def main() -> None:
    state = ConfigState(resource_id="aws_instance.web", resource_type="aws_instance", provider="AWS", configuration={"instance_type": "t3.large", "tags": {"Environment": "production"}}, capture_timestamp="2026-01-01T00:00:00Z")
    metric = TelemetryDatum(resource_id="aws_instance.web", resource_type="aws_instance", metric_name="CPUUtilization", namespace="AWS/EC2", timestamp="2026-01-01T00:00:00Z", value=97.0, unit="Percent")
    collector = RuntimeStateCollector(MockConfigProvider([state]), MockCloudWatchProvider([metric]), timestamp="2026-01-01T00:00:00Z")
    runtime = collector.collect(uir())
    assert runtime.metadata["collection_status"] == "SUCCESS"
    assert runtime.to_dict() == collector.collect(uir()).to_dict()
    assert runtime.telemetry[0].evidence_id == metric.evidence_id
    assessment = TelemetryIntentDriftAnalyzer().analyze(uir(), runtime)[0]
    assert assessment.category == DriftCategory.CONFIRMED_DRIFT and 0 <= assessment.score <= 1
    assert assessment.factors["criticality"] > 0 and assessment.evidence_id.startswith("runtime-drift:")
    no_telemetry = RuntimeStateCollector(MockConfigProvider([ConfigState(resource_id="aws_instance.web", resource_type="aws_instance", provider="AWS", configuration=uir()["resources"][0]["properties"])]), MockCloudWatchProvider()).collect(uir())
    assert TelemetryIntentDriftAnalyzer().analyze(uir(), no_telemetry)[0].category == DriftCategory.INSUFFICIENT_EVIDENCE
    partial = RuntimeStateCollector(MockConfigProvider([], [CollectionError(source="AWS_CONFIG", resource_id="aws_instance.web", code="NOT_FOUND", message="missing")]), MockCloudWatchProvider()).collect(uir())
    assert partial.metadata["collection_status"] == "FAILED"
    failed = RuntimeStateCollector(MockConfigProvider([], [CollectionError(source="AWS_CONFIG", resource_id="aws_instance.web", code="API_ERROR", message="access denied")]), MockCloudWatchProvider()).collect(uir())
    assert TelemetryIntentDriftAnalyzer().analyze(uir(), failed)[0].category == DriftCategory.INSUFFICIENT_EVIDENCE
    print("MODULE 6 UNIT TESTS: PASSED")


if __name__ == "__main__": main()
