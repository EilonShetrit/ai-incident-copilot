"""Claude tool definitions for the investigation tools in app.tools.

Each tool has a Pydantic input model. The model is the single source of truth: it generates
the JSON schema Claude sees, and it validates the arguments Claude sends back.
"""

from pydantic import BaseModel, ConfigDict, Field

TIME_HELP = "ISO-8601 UTC timestamp, or OpenSearch date math such as now-15m"


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchLogsInput(_Input):
    start: str = Field(description=TIME_HELP)
    end: str = Field(description=TIME_HELP)
    service: str | None = Field(None, description="Only this service")
    level: str | None = Field(None, description="Log level: INFO, WARN or ERROR")
    query: str | None = Field(None, description="Full-text search on the message field")
    limit: int = Field(10, ge=1, le=50, description="Number of sample lines to return")


class GetMetricsInput(_Input):
    start: str = Field(description=TIME_HELP)
    end: str = Field(description=TIME_HELP)
    service: str


class GetDeployEventsInput(_Input):
    start: str = Field(description=TIME_HELP)
    end: str = Field(description=TIME_HELP)
    service: str | None = Field(None, description="Only this service")


class GetServiceMapInput(_Input):
    pass


class GetRunbookInput(_Input):
    name: str | None = Field(None, description="Runbook name. Omit to list available runbooks")


class GetErrorCodesInput(_Input):
    start: str = Field(description=TIME_HELP)
    end: str = Field(description=TIME_HELP)
    service: str | None = Field(None, description="Only this service")


class GetFailureModesInput(_Input):
    pass


TOOL_SPECS: dict[str, tuple[type[_Input], str]] = {
    "search_logs": (
        SearchLogsInput,
        "Summarize application logs in a time window: total count, counts by level, HTTP "
        "status code and service version, the five most frequent messages, and a few sample "
        "lines (newest first). Use it to see what errors a service is returning and from "
        "which version.",
    ),
    "get_metrics": (
        GetMetricsInput,
        "Per-minute metrics for one service (error_rate, latency_p95_ms, requests, "
        "db_pool_max, db_pool_active, version) plus min/avg/max of each. Use it to measure "
        "how bad an incident is and exactly when it started.",
    ),
    "get_deploy_events": (
        GetDeployEventsInput,
        "Deploys in a time window, newest first, with from/to version, commit, author and "
        "change description. Use it to find a change that lines up with the incident.",
    ),
    "get_service_map": (
        GetServiceMapInput,
        "The service catalog: each service's owning team, what it depends on and what "
        "calls it. Use it to follow errors downstream and to find sibling services.",
    ),
    "get_runbook": (
        GetRunbookInput,
        "Read an operational runbook by name, or list the available runbooks.",
    ),
    "get_error_codes": (
        GetErrorCodesInput,
        "Failed requests per service broken down by HTTP status code, with each code's share "
        "of requests. Monitored codes (460, 500, 501, 502, 503, 504) come with their meaning "
        "and common real-world causes. Use it to see which services fail and how.",
    ),
    "get_failure_modes": (
        GetFailureModesInput,
        "The catalog of real-world failure modes (pool exhaustion, bad deploy, timeout "
        "cascade, OOM, DNS, expired certificate, ...) with the signals that identify each one. "
        "Use it to classify the incident.",
    ),
}


def _schema(model: type[_Input]) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


TOOL_DEFINITIONS = [
    {"name": name, "description": description, "input_schema": _schema(model)}
    for name, (model, description) in TOOL_SPECS.items()
]
