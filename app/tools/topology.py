from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path(__file__).resolve().parents[2] / "catalog" / "services.yaml"


@lru_cache
def _catalog() -> dict[str, Any]:
    return yaml.safe_load(CATALOG_PATH.read_text())["services"]


def get_service_map() -> dict[str, Any]:
    """Every service with its owner, dependencies (downstream) and dependents (upstream)."""
    catalog = _catalog()
    services = {}
    for name, info in catalog.items():
        services[name] = {
            "description": info["description"],
            "team": info["team"],
            "depends_on": info["depends_on"],
            "called_by": [other for other, o in catalog.items() if name in o["depends_on"]],
        }
    return {"services": services}
