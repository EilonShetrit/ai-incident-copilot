"""Integration tests: the tools against a real OpenSearch loaded with the scenario.

Skipped when OpenSearch is not reachable, unless REQUIRE_OPENSEARCH=1 (as in CI).
Data is anchored so the deploy happened 10 minutes ago and the alert fired 5 minutes ago.
"""

import os

import pytest

from app.clients.opensearch import get_client
from app.tools import (
    get_deploy_events,
    get_metrics,
    get_runbook,
    get_service_map,
    search_logs,
)
from generator.generate import generate, load_scenario
from generator.seed import install_templates, load

BEFORE = ("now-70m", "now-11m")  # healthy baseline
AFTER = ("now-6m", "now")  # after the incident is fully developed


@pytest.fixture(scope="module", autouse=True)
def seeded():
    client = get_client()
    if not client.ping():
        if os.environ.get("REQUIRE_OPENSEARCH") == "1":
            pytest.fail("OpenSearch is required but not reachable")
        pytest.skip("OpenSearch not reachable; run `make up` first")
    install_templates(client)
    load(client, generate(load_scenario("scenarios/5xx_after_deploy.yaml")))


def test_finds_the_payments_deploy():
    result = get_deploy_events(start="now-30m", end="now")
    assert result["count"] == 1
    assert result["deploys"][0]["service"] == "payments"
    assert result["deploys"][0]["to_version"] == "v2.4.0"


def test_no_deploys_in_baseline_window():
    assert get_deploy_events(*BEFORE)["count"] == 0


def test_gateway_errors_point_downstream():
    result = search_logs(*AFTER, service="api-gateway", level="ERROR")
    assert result["total"] > 20
    assert result["by_status_code"].keys() == {"502"}
    assert "upstream checkout" in result["top_messages"][0]["message"]


def test_payments_errors_show_pool_exhaustion_on_new_version():
    result = search_logs(*AFTER, service="payments", level="ERROR")
    assert "could not acquire connection from pool" in result["top_messages"][0]["message"]
    assert result["by_version"].keys() == {"v2.4.0"}


def test_free_text_query_finds_startup_config():
    result = search_logs("now-15m", "now", service="payments", query="pool.max_size")
    assert any("pool.max_size=5" in s["message"] for s in result["samples"])


def test_metrics_show_spike_on_gateway_only_after_deploy():
    before = get_metrics(*BEFORE, service="api-gateway")["summary"]["error_rate"]
    after = get_metrics(*AFTER, service="api-gateway")["summary"]["error_rate"]
    assert before["avg"] < 0.02
    assert after["avg"] > 0.10


def test_inventory_is_healthy():
    after = get_metrics(*AFTER, service="inventory")["summary"]["error_rate"]
    assert after["avg"] < 0.02


def test_payments_pool_shrank():
    before = get_metrics(*BEFORE, service="payments")["summary"]["db_pool_max"]
    after = get_metrics(*AFTER, service="payments")["summary"]["db_pool_max"]
    assert before["max"] == 50
    assert after["max"] == 5


def test_service_map_has_upstream_and_downstream():
    services = get_service_map()["services"]
    assert services["checkout"]["depends_on"] == ["payments", "inventory"]
    assert services["payments"]["called_by"] == ["checkout"]


def test_runbooks():
    assert set(get_runbook()["available"]) == {"deploy_regression", "high_5xx_rate"}
    assert "Roll back" in get_runbook("deploy_regression")["content"]
    assert "error" in get_runbook("nope")
