from datetime import UTC, datetime, timedelta

import pytest

from generator.generate import generate, load_scenario

ANCHOR = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def scenario():
    return load_scenario("scenarios/5xx_after_deploy.yaml")


@pytest.fixture(scope="module")
def data(scenario):
    return generate(scenario, anchor=ANCHOR)


def _error_rate(metrics, service, start, end):
    """Mean error rate for a service between minutes T+start and T+end."""
    lo, hi = ANCHOR + timedelta(minutes=start), ANCHOR + timedelta(minutes=end)
    rows = [
        m
        for m in metrics
        if m["service"] == service
        and lo <= datetime.fromisoformat(m["@timestamp"].replace("Z", "+00:00")) < hi
    ]
    return sum(m["error_rate"] for m in rows) / len(rows)


def test_output_is_deterministic(scenario, data):
    again = generate(scenario, anchor=ANCHOR)
    assert again.logs == data.logs
    assert again.metrics == data.metrics


def test_deploy_event_for_payments(data):
    assert len(data.deploys) == 1
    deploy = data.deploys[0]
    assert deploy["service"] == "payments"
    assert deploy["to_version"] == "v2.4.0"
    assert deploy["@timestamp"].startswith("2026-01-01T12:00")


def test_baseline_is_healthy(data):
    for service in ("api-gateway", "checkout", "payments", "inventory"):
        assert _error_rate(data.metrics, service, -60, 0) < 0.02


def test_5xx_spike_after_deploy(data):
    assert _error_rate(data.metrics, "api-gateway", 4, 10) > 0.10
    assert _error_rate(data.metrics, "checkout", 4, 10) > 0.10
    assert _error_rate(data.metrics, "payments", 3, 10) > 0.12


def test_inventory_stays_healthy(data):
    assert _error_rate(data.metrics, "inventory", 0, 10) < 0.02


def test_pool_shrinks_with_deploy(data):
    payments = [m for m in data.metrics if m["service"] == "payments"]
    before = [m["db_pool_max"] for m in payments if m["version"] == "v2.3.0"]
    after = [m["db_pool_max"] for m in payments if m["version"] == "v2.4.0"]
    assert set(before) == {50}
    assert set(after) == {5}


def test_root_cause_evidence_in_logs(data):
    messages = [log["message"] for log in data.logs if log["service"] == "payments"]
    assert any("pool.max_size=5" in m for m in messages)
    assert any("could not acquire connection from pool" in m for m in messages)
