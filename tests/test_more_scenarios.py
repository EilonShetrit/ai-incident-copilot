"""The DNS, SQL migration and log pipeline scenarios end to end against OpenSearch.

Skipped when OpenSearch is not reachable, unless REQUIRE_OPENSEARCH=1 (as in CI).
"""

import os

import pytest

from app.catalog import failure_modes
from app.clients.opensearch import get_client
from app.scenarios import scenarios, seed
from app.tools import get_deploy_events, get_error_codes, get_metrics, get_runbook, search_logs

_seeded: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def opensearch():
    if not get_client().ping():
        if os.environ.get("REQUIRE_OPENSEARCH") == "1":
            pytest.fail("OpenSearch is required but not reachable")
        pytest.skip("OpenSearch not reachable; run `make up` first")
    yield
    _seeded.clear()


def use(name: str) -> None:
    if _seeded[-1:] != [name]:
        seed(scenarios()[name])
        _seeded.append(name)


def failed_share(service: dict) -> float:
    return service["failed"] / service["requests"]


@pytest.mark.parametrize("name", ["dns_failure", "sql_migration_error", "log_pipeline_delay"])
def test_failure_mode_and_alert_are_defined(name):
    truth = scenarios()[name]["ground_truth"]
    assert truth["failure_mode"] in failure_modes()
    assert scenarios()[name]["alert"]


def test_dns_change_is_the_latest_deploy_and_only_external_calls_fail():
    use("dns_failure")
    deploys = get_deploy_events("now-65m", "now")["deploys"]
    assert [(d["service"], d["to_version"]) for d in deploys] == [
        ("coredns", "cfg-42"),
        ("payments", "v2.4.1"),
    ]
    services = get_error_codes("now-8m", "now")["services"]
    assert services["payments"]["codes"][0]["code"] == 504
    assert failed_share(services["inventory"]) < 0.02  # cluster-internal names still resolve
    assert "coredns" not in services  # resolver log lines are not requests

    errors = search_logs("now-10m", "now", service="payments", level="ERROR")
    assert all("lookup psp.example.net" in m["message"] for m in errors["top_messages"])
    assert search_logs("now-10m", "now", service="coredns", query="healthy upstreams")["total"] >= 4
    assert get_metrics("now-8m", "now", "payments")["summary"]["latency_p95_ms"]["avg"] > 5000


def test_sql_errors_hit_only_the_reserve_endpoint_after_the_migration():
    use("sql_migration_error")
    errors = search_logs("now-10m", "now", service="inventory", level="ERROR", limit=50)
    assert errors["total"] > 50
    assert set(errors["by_path"]) == {"/inventory/reserve"}  # stock reads keep working
    assert "SQLSTATE 42703" in errors["samples"][0]["message"]

    migration = search_logs("now-15m", "now", service="inventory", query="0042_drop_reserved_qty")
    assert migration["total"] == 2
    assert get_metrics("now-8m", "now", "inventory")["summary"]["latency_p95_ms"]["max"] < 100

    services = get_error_codes("now-8m", "now")["services"]
    assert services["inventory"]["codes"][0]["code"] == 500
    assert failed_share(services["payments"]) < 0.02


def test_log_delay_hides_logs_but_not_traffic():
    use("log_pipeline_delay")
    before = search_logs("now-30m", "now-22m", service="checkout")["total"]
    after = search_logs("now-8m", "now", service="checkout")["total"]
    assert after < before * 0.3  # most recent lines have not arrived

    early = get_metrics("now-30m", "now-22m", "checkout")["summary"]
    late = get_metrics("now-8m", "now", "checkout")["summary"]
    assert late["requests"]["avg"] == early["requests"]["avg"]
    assert late["error_rate"]["max"] < 0.03

    shipper = get_metrics("now-8m", "now", "log-shipper")["summary"]
    assert shipper["ingest_lag_s"]["max"] > 300
    assert search_logs("now-12m", "now", service="log-shipper", query="429")["total"] >= 5
    assert all(s["failed"] == 0 for s in get_error_codes("now-8m", "now")["services"].values())


def test_new_runbooks_exist():
    for name in ("dns_failure", "db_migration_failure", "log_pipeline_lag"):
        assert get_runbook(name)["content"].startswith("# Runbook")
