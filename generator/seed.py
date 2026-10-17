"""Load a scenario's synthetic data into OpenSearch.

Usage:
    uv run python -m generator.seed [--scenario scenarios/5xx_after_deploy.yaml]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from opensearchpy import OpenSearch, helpers

from app.config import settings
from generator.generate import Dataset, generate, load_scenario

TEMPLATES_DIR = Path(__file__).parent / "index_templates"
INDICES = {"logs": "logs-synthetic", "metrics": "metrics-synthetic", "deploys": "deploys-synthetic"}


def install_templates(client: OpenSearch) -> None:
    for name in INDICES:
        body = json.loads((TEMPLATES_DIR / f"{name}.json").read_text())
        client.indices.put_index_template(name=f"aic-{name}", body=body)


def load(client: OpenSearch, data: Dataset) -> dict[str, int]:
    counts = {}
    for name, index in INDICES.items():
        client.indices.delete(index=index, ignore_unavailable=True)
        docs = getattr(data, name)
        helpers.bulk(client, ({"_index": index, "_source": doc} for doc in docs))
        client.indices.refresh(index=index)
        counts[index] = client.count(index=index)["count"]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="scenarios/5xx_after_deploy.yaml")
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)
    data = generate(scenario)
    client = OpenSearch(settings.opensearch_url)

    install_templates(client)
    counts = load(client, data)

    alert_at = scenario["window"]["alert_at"]
    print(f"Scenario: {scenario['name']}")
    print(f"Deploy at (T):  {data.deploy_time:%Y-%m-%d %H:%M} UTC")
    print(f"Alert fires at: T+{alert_at}m")
    for index, count in counts.items():
        print(f"  {index:<20} {count:>6} docs")


if __name__ == "__main__":
    main()
