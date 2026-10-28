"""Streamlit UI tests with Streamlit's AppTest and a faked API client."""

import pytest
from streamlit.testing.v1 import AppTest

from ui import api_client

REPORT = {
    "title": "payments v2.4.0 shrank its DB pool",
    "severity": "SEV2",
    "summary": "Roll back payments.",
    "impact": "~18% of gateway requests fail.",
    "impacted_services": ["api-gateway", "payments"],
    "healthy_services": ["inventory"],
    "root_cause": {
        "service": "payments",
        "hypothesis": "pool max_size 5",
        "trigger": "deploy v2.4.0",
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
    "evidence": [{"tool": "get_deploy_events", "finding": "payments v2.4.0"}],
    "timeline": [{"time": "2026-10-18T12:00:00Z", "event": "deploy"}],
    "next_steps": ["Roll back payments to v2.3.0"],
    "runbook": "deploy_regression",
}
CALL = {
    "turn": 1,
    "tool": "get_deploy_events",
    "input": {"start": "2026-10-18T11:30:00Z", "end": "now"},
    "result": {"count": 1},
    "is_error": False,
    "duration_ms": 6,
}


def incident(status, report=None, error=None):
    return {
        "id": "inc-1",
        "status": status,
        "alert": {
            "title": "[Triggered] api-gateway 5xx rate is above 5%",
            "date": "2026-10-18T12:05:00Z",
            "tags": ["service:api-gateway"],
        },
        "trace": [CALL],
        "report": report,
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 5},
        "error": error,
    }


@pytest.fixture
def fake_api(monkeypatch):
    state = {"incident": None}

    def listing():
        i = state["incident"]
        if i is None:
            return []
        return [
            {
                "id": i["id"],
                "status": i["status"],
                "service": "api-gateway",
                "created_at": "2026-10-18T12:05:00Z",
            }
        ]

    monkeypatch.setattr(api_client, "is_up", lambda: True)
    monkeypatch.setattr(
        api_client,
        "list_scenarios",
        lambda: [{"name": "5xx_after_deploy", "description": "d", "alert": "api-gateway 5xx"}],
    )
    monkeypatch.setattr(api_client, "list_incidents", listing)
    monkeypatch.setattr(api_client, "get_incident", lambda _id: state["incident"])
    monkeypatch.setattr(api_client, "get_report_markdown", lambda _id: "# report")
    monkeypatch.setattr(
        api_client,
        "status_codes",
        lambda: {
            "502": {"emoji": "🌐", "label": "Bad Gateway"},
            "501": {"emoji": "🚫", "label": "Not Implemented"},
        },
    )
    monkeypatch.setattr(
        api_client,
        "service_metrics",
        lambda service, minutes=30: {
            "series": [{"@timestamp": "2026-10-18T12:00:00Z", "error_rate": 0.2}]
        },
    )
    return state


def run():
    return AppTest.from_file("../ui/app.py", default_timeout=10).run()


def test_api_down_shows_how_to_start_it(monkeypatch):
    monkeypatch.setattr(api_client, "is_up", lambda: False)
    at = run()
    assert "make api" in at.error[0].value


def test_empty_state(fake_api):
    at = run()
    assert at.header[0].value == "No incidents yet"
    assert "Fire alert" in at.info[0].value


def test_investigating_shows_live_trace(fake_api):
    fake_api["incident"] = incident("investigating")
    at = run()
    assert not at.exception
    assert "investigating" in at.info[0].value
    assert "Investigating" in "".join(m.value for m in at.markdown)
    assert "get_deploy_events" in at.expander[0].label
    assert "11:30–now" in at.expander[0].label


def test_resolved_shows_report(fake_api):
    fake_api["incident"] = incident("resolved", report=REPORT)
    at = run()
    assert not at.exception
    text = "".join(m.value for m in at.markdown)
    assert 'kpi-value">payments<' in text
    assert 'kpi-value">High<' in text
    assert "pool max_size 5" in text
    assert "<b>Do now:</b> Roll back payments to v2.3.0" in text
    assert "Database connection pool exhaustion" in text
    assert "502 - 🌐 Bad Gateway" in text
    assert '<tr class="dim"><td class="code">501 - 🚫 Not Implemented' in text


def test_failed_shows_error(fake_api):
    fake_api["incident"] = incident("failed", error="Claude declined")
    at = run()
    assert "Claude declined" in at.error[0].value
