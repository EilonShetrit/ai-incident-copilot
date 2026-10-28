"""Demo scenarios: load one into OpenSearch and build the alert that goes with it."""

import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.clients.opensearch import get_client
from app.models import DatadogAlert
from generator.generate import generate, load_scenario
from generator.seed import install_templates, load

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = ROOT / "scenarios"


@lru_cache
def scenarios() -> dict[str, dict[str, Any]]:
    """All scenarios by name."""
    found = (load_scenario(path) for path in sorted(SCENARIOS_DIR.glob("*.yaml")))
    return {s["name"]: s for s in found}


def seed(scenario: dict[str, Any]) -> dict[str, int]:
    """Replace the indices with this scenario's data, anchored so it ends now."""
    client = get_client()
    install_templates(client)
    return load(client, generate(scenario))


def alert_for(scenario: dict[str, Any]) -> DatadogAlert:
    """The scenario's alert, timed to fire when the scenario says it does."""
    payload = json.loads((ROOT / scenario["alert"]).read_text())
    minutes_ago = scenario["window"]["end"] - scenario["window"]["alert_at"]
    return DatadogAlert.model_validate(
        {**payload, "date": datetime.now(UTC) - timedelta(minutes=minutes_ago)}
    )
