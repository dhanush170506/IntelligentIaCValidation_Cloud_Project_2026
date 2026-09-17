"""AWS-isolated providers and deterministic local providers for Module 6."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .schemas import CollectionError, CollectionStatus, ConfigState, RuntimeState, TelemetryDatum

DEFAULT_TELEMETRY_PROFILES = {
    "compute_instance": {"Namespace": "AWS/EC2", "Metrics": ("CPUUtilization", "NetworkIn", "NetworkOut")},
    "database": {"Namespace": "AWS/RDS", "Metrics": ("CPUUtilization", "DatabaseConnections")},
    "load_balancer": {"Namespace": "AWS/ApplicationELB", "Metrics": ("RequestCount", "HTTPCode_ELB_5XX_Count")},
}


class CloudWatchProvider(ABC):
    @abstractmethod
    def collect(self, resource: Mapping[str, Any]) -> tuple[tuple[TelemetryDatum, ...], tuple[CollectionError, ...]]: ...


class ConfigProvider(ABC):
    @abstractmethod
    def collect(self, resource: Mapping[str, Any]) -> tuple[ConfigState | None, tuple[CollectionError, ...]]: ...


class MockCloudWatchProvider(CloudWatchProvider):
    def __init__(self, telemetry: Iterable[TelemetryDatum] = (), failures: Iterable[CollectionError] = ()) -> None:
        self.telemetry, self.failures = tuple(telemetry), tuple(failures)

    def collect(self, resource: Mapping[str, Any]) -> tuple[tuple[TelemetryDatum, ...], tuple[CollectionError, ...]]:
        resource_id = str(resource.get("id", ""))
        return tuple(x for x in self.telemetry if x.resource_id == resource_id), tuple(x for x in self.failures if x.resource_id in (None, resource_id))


class MockConfigProvider(ConfigProvider):
    def __init__(self, states: Iterable[ConfigState] = (), failures: Iterable[CollectionError] = ()) -> None:
        self.states, self.failures = tuple(states), tuple(failures)

    def collect(self, resource: Mapping[str, Any]) -> tuple[ConfigState | None, tuple[CollectionError, ...]]:
        resource_id = str(resource.get("id", ""))
        state = next((x for x in self.states if x.resource_id == resource_id), None)
        return state, tuple(x for x in self.failures if x.resource_id in (None, resource_id))


class AwsCloudWatchProvider(CloudWatchProvider):
    """Boto3 adapter. Imports boto3 only when real collection is requested."""
    def __init__(
        self,
        client: Any = None,
        *,
        telemetry_profiles: Mapping[str, Mapping[str, Any]] | None = None,
        lookback_minutes: int = 60,
        period_seconds: int = 300,
    ) -> None:
        if lookback_minutes <= 0:
            raise ValueError("lookback_minutes must be positive")

        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")

        self.client = client
        self.telemetry_profiles = dict(DEFAULT_TELEMETRY_PROFILES) | dict(
            telemetry_profiles or {}
        )
        self.lookback_minutes = lookback_minutes
        self.period_seconds = period_seconds

    def _queries(
        self,
        resource: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:

        # Explicit IaC/application queries take precedence.
        explicit = resource.get("telemetry_queries")

        if explicit:
            return tuple(
                x for x in explicit
                if isinstance(x, Mapping)
            )

        profile = self.telemetry_profiles.get(
            str(resource.get("canonical_type", ""))
        )

        if not profile:
            return ()

        dimensions = resource.get("telemetry_dimensions", ())

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(
            minutes=self.lookback_minutes
        )

        return tuple(
            {
                "Namespace": profile["Namespace"],
                "MetricName": metric,
                "Dimensions": dimensions,
                "Statistics": ["Average"],
                "StartTime": start_time,
                "EndTime": end_time,
                "Period": self.period_seconds,
            }
            for metric in profile.get("Metrics", ())
        )
    def collect(self, resource: Mapping[str, Any]) -> tuple[tuple[TelemetryDatum, ...], tuple[CollectionError, ...]]:
        rid = str(resource.get("id", ""))
        try:
            client = self.client
            if client is None:
                import boto3  # type: ignore
                client = boto3.client("cloudwatch")
            queries = self._queries(resource)
            if not queries:
                return (), ()
            data, errors = [], []
            for query in queries:
                try:
                    response = client.get_metric_statistics(**dict(query))
                    for point in response.get("Datapoints", []):
                        data.append(TelemetryDatum(resource_id=rid, resource_type=str(resource.get("type", "unknown")), metric_name=str(query.get("MetricName", "unknown")), namespace=str(query.get("Namespace", "unknown")), timestamp=str(point["Timestamp"]), value=float(point.get(query.get("Statistics", ["Average"])[0], 0.0)), unit=str(point.get("Unit", "None")), statistic=str(query.get("Statistics", ["Average"])[0]), dimensions={str(x.get("Name")): str(x.get("Value")) for x in query.get("Dimensions", [])}))
                except Exception as exc:
                    errors.append(CollectionError(source="CLOUDWATCH", resource_id=rid, code="API_ERROR", message=str(exc)))
            return tuple(sorted(data, key=lambda x: (x.resource_id, x.metric_name, x.timestamp))), tuple(errors)
        except ImportError:
            return (), (CollectionError(source="CLOUDWATCH", resource_id=rid, code="UNAVAILABLE", message="boto3 is unavailable"),)
        except Exception as exc:
            return (), (CollectionError(source="CLOUDWATCH", resource_id=rid, code="API_ERROR", message=str(exc)),)


class AwsConfigProvider(ConfigProvider):
    def __init__(self, client: Any = None) -> None: self.client = client

    def collect(self, resource: Mapping[str, Any]) -> tuple[ConfigState | None, tuple[CollectionError, ...]]:
        rid = str(resource.get("id", ""))
        try:
            client = self.client
            if client is None:
                import boto3  # type: ignore
                client = boto3.client("config")
            response = client.get_resource_config_history(resourceType=str(resource.get("aws_config_type", resource.get("type", ""))), resourceId=rid, laterTime=__import__("datetime").datetime.utcnow(), limit=1)
            items = response.get("configurationItems", [])
            if not items:
                return None, (CollectionError(source="AWS_CONFIG", resource_id=rid, code="NOT_FOUND", message="No configuration item returned"),)
            item = items[0]
            configuration = item.get("configuration", {})
            if isinstance(configuration, str):
                import json
                configuration = json.loads(configuration)
            if not isinstance(configuration, dict): raise ValueError("malformed configuration")
            return ConfigState(resource_id=rid, resource_type=str(resource.get("type", "unknown")), provider="AWS", configuration=configuration, relationships=tuple(item.get("relationships", ())), capture_timestamp=str(item.get("configurationItemCaptureTime", ""))), ()
        except ImportError:
            return None, (CollectionError(source="AWS_CONFIG", resource_id=rid, code="UNAVAILABLE", message="boto3 is unavailable"),)
        except Exception as exc:
            return None, (CollectionError(source="AWS_CONFIG", resource_id=rid, code="API_ERROR", message=str(exc)),)


class RuntimeStateCollector:
    def __init__(self, config_provider: ConfigProvider, telemetry_provider: CloudWatchProvider, *, timestamp: str = "1970-01-01T00:00:00Z") -> None:
        self.config_provider, self.telemetry_provider, self.timestamp = config_provider, telemetry_provider, timestamp

    def collect(self, uir: Mapping[str, Any]) -> RuntimeState:
        resources, telemetry, errors, evidence = [], [], [], []
        for desired in sorted(uir.get("resources", ()), key=lambda x: str(x.get("id", ""))):
            state, config_errors = self.config_provider.collect(desired)
            metrics, metric_errors = self.telemetry_provider.collect(desired)
            if state: resources.append(state); evidence.append(state.to_dict())
            telemetry.extend(metrics); evidence.extend(x.to_dict() for x in metrics)
            errors.extend(config_errors); errors.extend(metric_errors)
        status = CollectionStatus.SUCCESS if not errors else (CollectionStatus.PARTIAL_SUCCESS if resources or telemetry else CollectionStatus.FAILED)
        return RuntimeState(resources=tuple(resources), telemetry=tuple(sorted(telemetry, key=lambda x: (x.resource_id, x.metric_name, x.timestamp))), collection_evidence=tuple(evidence), collection_errors=tuple(errors), timestamp=self.timestamp, metadata={"collection_status": status.value, "mode": "mock" if isinstance(self.config_provider, MockConfigProvider) else "aws"})
