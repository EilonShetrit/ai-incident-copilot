from app.agent import IncidentReport
from evals.run import to_markdown
from evals.scoring import score
from generator.generate import load_scenario

TRUTH = load_scenario("scenarios/5xx_after_deploy.yaml")["ground_truth"]

GOOD = {
    "title": "t",
    "severity": "SEV2",
    "summary": "s",
    "impact": "i",
    "impacted_services": ["payments", "api-gateway", "checkout"],
    "healthy_services": ["inventory"],
    "root_cause": {
        "service": "payments",
        "hypothesis": "The DB connection pool max_size dropped from 50 to 5.",
        "trigger": "deploy payments v2.3.0 -> v2.4.0",
        "confidence": "high",
    },
    "evidence": [
        {"tool": "get_deploy_events", "finding": "..."},
        {"tool": "search_logs", "finding": "..."},
        {"tool": "get_metrics", "finding": "..."},
    ],
    "timeline": [],
    "next_steps": ["Roll back payments to v2.3.0 now", "Page the payments team"],
    "runbook": "deploy_regression",
}


def report(**changes):
    return IncidentReport.model_validate({**GOOD, **changes})


def failed(checks):
    return [c.name for c in checks if not c.passed]


def test_correct_report_passes_everything():
    assert failed(score(report(), TRUTH)) == []


def test_blaming_the_gateway_fails():
    rc = {**GOOD["root_cause"], "service": "api-gateway", "hypothesis": "gateway overloaded"}
    assert failed(score(report(root_cause=rc), TRUTH)) == [
        "root_cause_service",
        "root_cause_explained",
    ]


def test_inventory_marked_impacted_fails_two_checks():
    checks = score(report(impacted_services=[*GOOD["impacted_services"], "inventory"]), TRUTH)
    assert failed(checks) == ["impacted_services", "healthy_ruled_out"]


def test_mitigation_must_come_first():
    steps = ["Page the payments team", "Roll back payments"]
    assert failed(score(report(next_steps=steps), TRUTH)) == ["mitigation_first"]
    assert failed(score(report(next_steps=["Rollback payments to v2.3.0"]), TRUTH)) == []


def test_rollback_phrasings_count():
    # Phrasings from real eval runs that an earlier grader wrongly failed.
    for step in [
        "Roll payments back from v2.4.0 to v2.3.0 now (deploy_regression runbook step 3).",
        "Revert payments to v2.3.0",
        "Roll back payments to v2.3.0",
    ]:
        assert failed(score(report(next_steps=[step]), TRUTH)) == [], step
    assert failed(score(report(next_steps=["Roll out a payments fix"]), TRUTH)) == [
        "mitigation_first"
    ]


def test_thin_evidence_fails():
    evidence = [{"tool": "search_logs", "finding": "..."}]
    assert failed(score(report(evidence=evidence), TRUTH)) == ["evidence_backed"]


def test_markdown_summary_lists_failures():
    checks = [c.__dict__ for c in score(report(next_steps=["Page someone"]), TRUTH)]
    run = {"checks": checks, "turns": 5, "tool_calls": 12, "seconds": 80.0}
    md = to_markdown({"scenario": "x", "date": "d", "model": "m", "score": 5 / 6, "runs": [run]})
    assert "83%" in md
    assert "| `mitigation_first` | ❌ |" in md
    assert "Run 1, `mitigation_first`" in md


def test_run_once_seeds_and_scores(monkeypatch):
    """One eval run end to end with a fake agent (needs OpenSearch, like test_tools)."""
    import os

    import pytest

    from app.agent import Investigation
    from app.clients.opensearch import get_client
    from evals import run as eval_run

    if not get_client().ping():
        if os.environ.get("REQUIRE_OPENSEARCH") == "1":
            pytest.fail("OpenSearch is required but not reachable")
        pytest.skip("OpenSearch not reachable")

    seen = {}

    def fake_investigate(alert):
        seen["alert"] = alert
        return Investigation(report=report(), trace=[], turns=3, usage={})

    monkeypatch.setattr(eval_run, "investigate", fake_investigate)
    scenario = load_scenario("scenarios/5xx_after_deploy.yaml")
    result = eval_run.run_once(scenario, {"id": "1", "title": "t", "tags": "service:api-gateway"})
    assert result["passed"] == result["total"] == 6
    assert seen["alert"].service == "api-gateway"
