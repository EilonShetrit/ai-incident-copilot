"""The OOM scenario end to end against OpenSearch, plus the demo endpoints.

Skipped when OpenSearch is not reachable, unless REQUIRE_OPENSEARCH=1 (as in CI).
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.clients.opensearch import get_client
from app.config import settings
from app.incidents import store
from app.scenarios import alert_for, scenarios, seed
from app.tools import get_deploy_events, get_error_codes, get_metrics, search_logs
from generator.generate import generate

OOM = scenarios()["oom_memory_leak"]


@pytest.fixture(scope="module", autouse=True)
def seeded():
    if not get_client().ping():
        if os.environ.get("REQUIRE_OPENSEARCH") == "1":
            pytest.fail("OpenSearch is required but not reachable")
        pytest.skip("OpenSearch not reachable; run `make up` first")
    seed(OOM)


def test_every_scenario_has_an_alert_and_ground_truth():
    assert set(scenarios()) >= {"5xx_after_deploy", "oom_memory_leak"}
    for scenario in scenarios().values():
        alert = alert_for(scenario)
        assert alert.service == scenario["ground_truth"]["alerted_service"]
        assert scenario["ground_truth"]["failure_mode"]


def test_latest_deploy_is_a_red_herring():
    deploys = get_deploy_events("now-75m", "now")["deploys"]
    assert [d["service"] for d in deploys] == ["api-gateway", "inventory"]  # newest first


def test_memory_climbs_to_the_limit_then_restarts():
    early = get_metrics("now-70m", "now-62m", "inventory")["summary"]
    late = get_metrics("now-14m", "now-11m", "inventory")["summary"]
    after = get_metrics("now-9m", "now", "inventory")["summary"]
    assert early["memory_mb"]["max"] < 200
    assert late["memory_mb"]["max"] > 470
    assert after["restarts"]["max"] >= 1
    assert after["memory_limit_mb"]["max"] == 512


def test_oom_kills_are_in_the_logs():
    result = search_logs("now-10m", "now", service="inventory", query="OOMKilled")
    assert result["total"] >= 5
    assert "exceeded memory limit 512Mi" in result["samples"][0]["message"]


def test_checkout_sees_502_and_503_payments_healthy():
    services = get_error_codes("now-8m", "now")["services"]
    checkout = {c["code"] for c in services["checkout"]["codes"]}
    assert {502, 503} <= checkout
    payments_failed = services["payments"]["failed"] / services["payments"]["requests"]
    assert payments_failed < 0.02


def test_events_are_deterministic():
    a, b = generate(OOM), generate(OOM)
    assert [x["message"] for x in a.logs] == [x["message"] for x in b.logs]


def test_demo_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(main, "run_investigation", lambda incident_id: None)
    store.clear()
    client = TestClient(main.app)

    listed = {s["name"]: s for s in client.get("/demo/scenarios").json()}
    assert "checkout 5xx" in listed["oom_memory_leak"]["alert"]

    fired = client.post("/demo/scenarios/oom_memory_leak/fire")
    assert fired.status_code == 202
    incident = client.get(f"/incidents/{fired.json()['incident_id']}").json()
    assert incident["alert"]["tags"][0] == "service:checkout"
    assert client.post("/demo/scenarios/nope/fire").status_code == 404
