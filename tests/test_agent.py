"""Agent loop tests with a scripted fake Claude client and fake tools.

No API key, network or OpenSearch needed.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.agent import IncidentReport, InvestigationError, investigate
from app.agent import loop as agent_loop
from app.agent.prompts import build_user_message
from app.agent.tool_registry import TOOL_DEFINITIONS, TOOL_SPECS
from app.models import DatadogAlert
from app.tools import TOOLS

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

REPORT = {
    "title": "5xx spike on api-gateway caused by payments v2.4.0",
    "severity": "SEV2",
    "summary": "payments v2.4.0 shrank its DB pool from 50 to 5.",
    "impact": "~18% of gateway requests fail with 502 since 11:52 UTC.",
    "impacted_services": ["api-gateway", "checkout", "payments"],
    "healthy_services": ["inventory"],
    "root_cause": {
        "service": "payments",
        "hypothesis": "DB pool max_size 5 cannot serve the load; requests time out.",
        "trigger": "deploy payments v2.3.0 -> v2.4.0",
        "confidence": "high",
    },
    "failure_mode": {
        "id": "db_connection_pool_exhaustion",
        "name": "Database connection pool exhaustion",
        "why": "pool 5/5 in use, 503 'could not acquire connection'",
    },
    "error_codes": [
        {"service": "payments", "code": 503, "count": 77},
        {"service": "checkout", "code": 502, "count": 28},
        {"service": "checkout", "code": 504, "count": 9},
        {"service": "api-gateway", "code": 502, "count": 36},
        {"service": "api-gateway", "code": 504, "count": 7},
        {"service": "api-gateway", "code": 460, "count": 2},
    ],
    "evidence": [{"tool": "get_deploy_events", "finding": "payments v2.4.0 at 11:50"}],
    "timeline": [{"time": "2026-10-17T11:50:00Z", "event": "payments v2.4.0 deployed"}],
    "next_steps": ["Roll back payments to v2.3.0"],
    "runbook": "deploy_regression",
}


def tool_use(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def response(stop_reason, *content):
    usage = SimpleNamespace(input_tokens=100, output_tokens=20)
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage)


def final(report=REPORT):
    text = json.dumps(report) if isinstance(report, dict) else report
    return response("end_turn", SimpleNamespace(type="text", text=text))


class FakeClaude:
    """Returns scripted responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Snapshot messages: the loop keeps appending to the same list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


@pytest.fixture
def alert():
    return DatadogAlert(
        id="1",
        title="[Triggered] api-gateway 5xx rate is above 5%",
        tags="service:api-gateway,env:prod",
        date=datetime(2026, 10, 17, 11, 55, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
def fake_tools(monkeypatch):
    calls = []

    def deploys(start, end, service=None):
        calls.append(("get_deploy_events", start, end, service))
        return {"count": 1, "deploys": [{"service": "payments", "to_version": "v2.4.0"}]}

    def broken(**kwargs):
        raise ConnectionError("OpenSearch down")

    monkeypatch.setitem(TOOLS, "get_deploy_events", deploys)
    monkeypatch.setitem(TOOLS, "get_metrics", broken)
    return calls


def test_runs_tools_then_returns_report(alert, fake_tools):
    first = response(
        "tool_use",
        SimpleNamespace(type="thinking", thinking="check deploys", signature="sig"),
        tool_use("t1", "get_deploy_events", {"start": "now-30m", "end": "now"}),
    )
    claude = FakeClaude(first, final())
    seen = []

    result = investigate(alert, client=claude, now=NOW, on_tool_call=seen.append)

    assert isinstance(result.report, IncidentReport)
    assert result.report.root_cause.service == "payments"
    assert result.turns == 2
    assert result.usage["input_tokens"] == 200
    assert result.usage["output_tokens"] == 40
    assert fake_tools == [("get_deploy_events", "now-30m", "now", None)]
    assert [c.tool for c in result.trace] == [c.tool for c in seen] == ["get_deploy_events"]

    # Second request: the assistant turn goes back unchanged, then the tool result.
    messages = claude.requests[1]["messages"]
    assert messages[1] == {"role": "assistant", "content": first.content}
    (tool_result,) = messages[2]["content"]
    assert tool_result["tool_use_id"] == "t1"
    assert tool_result["is_error"] is False
    assert json.loads(tool_result["content"])["count"] == 1


def test_request_shape(alert):
    claude = FakeClaude(final())
    investigate(alert, client=claude, now=NOW)
    request = claude.requests[0]
    assert request["tools"] == TOOL_DEFINITIONS
    assert request["output_config"]["effort"] == "high"
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["fallbacks"] == "default"
    assert request["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in request


def test_html_entities_in_report_are_decoded(alert):
    report = {**REPORT, "summary": "change &#39;Refactor DB client&#39; &amp; more"}
    result = investigate(alert, client=FakeClaude(final(report)), now=NOW)
    assert result.report.summary == "change 'Refactor DB client' & more"


def test_parallel_tool_calls_return_in_one_message(alert):
    claude = FakeClaude(
        response(
            "tool_use",
            tool_use("a", "get_deploy_events", {"start": "now-30m", "end": "now"}),
            tool_use("b", "get_service_map", {}),
        ),
        final(),
    )
    investigate(alert, client=claude, now=NOW)
    results = claude.requests[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


@pytest.mark.parametrize(
    "name, input, expected",
    [
        ("get_deploy_events", {"start": "now-30m"}, "Invalid arguments"),
        ("get_deploy_events", {"start": "a", "end": "b", "colour": "red"}, "Invalid arguments"),
        ("drop_database", {}, "Unknown tool"),
        ("get_metrics", {"start": "a", "end": "b", "service": "x"}, "ConnectionError"),
    ],
)
def test_tool_errors_go_back_to_claude(alert, name, input, expected):
    claude = FakeClaude(response("tool_use", tool_use("t1", name, input)), final())
    result = investigate(alert, client=claude, now=NOW)
    (tool_result,) = claude.requests[1]["messages"][2]["content"]
    assert tool_result["is_error"] is True
    assert expected in tool_result["content"]
    assert result.trace[0].is_error


@pytest.mark.parametrize(
    "responses, message",
    [
        ([response("refusal")], "declined"),
        ([response("max_tokens")], "max_tokens"),
        ([final("not json")], "schema"),
        ([final({**REPORT, "severity": "SEV9"})], "schema"),
    ],
)
def test_failures_raise(alert, responses, message):
    with pytest.raises(InvestigationError, match=message):
        investigate(alert, client=FakeClaude(*responses), now=NOW)


def test_stops_after_max_turns(alert):
    loop_forever = [
        response("tool_use", tool_use(f"t{i}", "get_service_map", {})) for i in range(3)
    ]
    with pytest.raises(InvestigationError, match="after 3 turns"):
        investigate(alert, client=FakeClaude(*loop_forever), now=NOW, max_turns=3)


def test_every_tool_has_a_definition():
    assert TOOL_SPECS.keys() == TOOLS.keys()
    for definition in TOOL_DEFINITIONS:
        assert definition["input_schema"]["type"] == "object"
        assert definition["description"]


def test_report_schema_is_strict():
    schema = agent_loop.REPORT_FORMAT["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(IncidentReport.model_fields)
    assert "Roll back payments" in IncidentReport.model_validate(REPORT).to_markdown()


def test_alert_parses_datadog_tags(alert):
    assert alert.tags == ["service:api-gateway", "env:prod"]
    assert alert.service == "api-gateway"
    assert alert.tag("team") is None


def test_user_message_has_times_and_service(alert):
    message = build_user_message(alert, NOW)
    assert "Current time: 2026-10-17T12:00:00+00:00" in message
    assert "Alert fired at: 2026-10-17T11:55:00+00:00" in message
    assert "Alerted service: api-gateway" in message
