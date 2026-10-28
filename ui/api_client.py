"""Thin client for the copilot API. The UI only talks to the API, never to OpenSearch or Claude."""

import os
from typing import Any

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")

_client = httpx.Client(base_url=API_URL, timeout=10)


def is_up() -> bool:
    try:
        return _client.get("/health").status_code == 200
    except httpx.HTTPError:
        return False


def list_scenarios() -> list[dict[str, Any]]:
    return _client.get("/demo/scenarios").raise_for_status().json()


def fire_scenario(name: str) -> dict[str, Any]:
    """Load the scenario's data and send its alert (seeding takes a few seconds)."""
    response = _client.post(f"/demo/scenarios/{name}/fire", timeout=60)
    response.raise_for_status()
    return response.json()


def list_incidents() -> list[dict[str, Any]]:
    return _client.get("/incidents").raise_for_status().json()


def get_incident(incident_id: str) -> dict[str, Any]:
    return _client.get(f"/incidents/{incident_id}").raise_for_status().json()


def get_report_markdown(incident_id: str) -> str:
    return _client.get(f"/incidents/{incident_id}/report.md").raise_for_status().text


def service_metrics(service: str, minutes: int = 30) -> dict[str, Any] | None:
    response = _client.get(f"/services/{service}/metrics", params={"minutes": minutes})
    return response.json() if response.status_code == 200 else None


def status_codes() -> dict[str, Any]:
    return _client.get("/catalog/status-codes").raise_for_status().json()
