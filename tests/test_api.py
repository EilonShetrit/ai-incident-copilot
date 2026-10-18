"""Webhook API tests. The agent is replaced with a fake, so no API key or OpenSearch needed."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent import IncidentReport, Investigation, InvestigationError, ToolCall
from app.api import main
from app.config import settings
from app.incidents import store

ALERT = json.loads(Path("samples/alert_5xx.json").read_text())
REPORT = IncidentReport.model_validate(
    {
        "title": "payments v2.4.0 shrank its DB pool",
        "severity": "SEV2",
        "summary": "Roll back payments.",
        "impact": "~18% of gateway requests fail.",
        "impacted_services": ["api-gateway", "checkout", "payments"],
        "healthy_services": ["inventory"],
        "root_cause": {
            "service": "payments",
            "hypothesis": "pool max_size 5",
            "trigger": "deploy v2.4.0",
            "confidence": "high",
        },
        "evidence": [],
        "timeline": [],
        "next_steps": ["Roll back payments to v2.3.0"],
        "runbook": "deploy_regression",
    }
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    store.clear()
    return TestClient(main.app)


@pytest.fixture
def fake_agent(monkeypatch):
    def investigate(alert, on_tool_call=None):
        on_tool_call(ToolCall(1, "get_deploy_events", {"start": "now-30m"}, {}, False, 5))
        return Investigation(report=REPORT, trace=[], turns=2, usage={"output_tokens": 10})

    monkeypatch.setattr(main, "investigate", investigate)


def test_webhook_starts_investigation_and_report_is_available(client, fake_agent):
    response = client.post("/webhooks/datadog", json=ALERT)
    assert response.status_code == 202
    incident_id = response.json()["incident_id"]
    assert response.headers["location"] == f"/incidents/{incident_id}"

    # TestClient runs background tasks before returning, so the investigation is done.
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["status"] == "resolved"
    assert incident["alert"]["tags"] == ["service:api-gateway", "env:prod", "team:platform"]
    assert incident["trace"][0]["tool"] == "get_deploy_events"
    assert incident["report"]["root_cause"]["service"] == "payments"

    markdown = client.get(f"/incidents/{incident_id}/report.md")
    assert markdown.headers["content-type"].startswith("text/plain")
    assert "Roll back payments" in markdown.text

    (listed,) = client.get("/incidents").json()
    assert listed["id"] == incident_id
    assert listed["service"] == "api-gateway"


def test_failed_investigation_is_recorded(client, monkeypatch):
    def investigate(alert, on_tool_call=None):
        raise InvestigationError("Claude declined")

    monkeypatch.setattr(main, "investigate", investigate)
    incident_id = client.post("/webhooks/datadog", json=ALERT).json()["incident_id"]
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["status"] == "failed"
    assert incident["error"] == "Claude declined"
    assert client.get(f"/incidents/{incident_id}/report.md").status_code == 409


def test_retry_of_an_open_alert_returns_the_same_incident(client, monkeypatch):
    monkeypatch.setattr(main, "run_investigation", lambda incident_id: None)  # stays open
    first = client.post("/webhooks/datadog", json=ALERT).json()
    second = client.post("/webhooks/datadog", json=ALERT)
    assert second.status_code == 200
    assert second.json() == {**first, "duplicate": True}


def test_recovery_notifications_are_ignored(client):
    response = client.post("/webhooks/datadog", json={**ALERT, "alert_transition": "Recovered"})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert client.get("/incidents").json() == []


def test_token_is_required_when_configured(client, fake_agent, monkeypatch):
    monkeypatch.setattr(settings, "webhook_token", "s3cret")
    assert client.post("/webhooks/datadog", json=ALERT).status_code == 401
    wrong = client.post("/webhooks/datadog", json=ALERT, headers={"X-Webhook-Token": "nope"})
    assert wrong.status_code == 401
    ok = client.post("/webhooks/datadog", json=ALERT, headers={"X-Webhook-Token": "s3cret"})
    assert ok.status_code == 202


def test_missing_api_key_is_a_clear_error(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    response = client.post("/webhooks/datadog", json=ALERT)
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_invalid_payload_is_rejected(client):
    assert client.post("/webhooks/datadog", json={"title": "no id"}).status_code == 422


def test_unknown_incident_is_404(client):
    assert client.get("/incidents/inc-nope").status_code == 404
