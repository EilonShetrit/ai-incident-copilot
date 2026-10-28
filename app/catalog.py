"""Reference data shared by the tools, the report and the UI."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"


@lru_cache
def status_codes() -> dict[int, dict[str, Any]]:
    """Monitored HTTP status codes: emoji, label, meaning, common causes."""
    return yaml.safe_load((CATALOG_DIR / "status_codes.yaml").read_text())["status_codes"]


@lru_cache
def failure_modes() -> dict[str, dict[str, Any]]:
    """Real-world failure modes: signals, triggers, first response."""
    return yaml.safe_load((CATALOG_DIR / "failure_modes.yaml").read_text())["failure_modes"]


def code_label(code: int) -> str:
    """'502 - 🌐 Bad Gateway', the format the monitor message uses."""
    info = status_codes().get(code)
    return f"{code} - {info['emoji']} {info['label']}" if info else str(code)
