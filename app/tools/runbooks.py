from pathlib import Path
from typing import Any

RUNBOOKS_DIR = Path(__file__).resolve().parents[2] / "runbooks"


def get_runbook(name: str | None = None) -> dict[str, Any]:
    """Return a runbook by name, or the list of available runbooks when no name is given."""
    available = sorted(path.stem for path in RUNBOOKS_DIR.glob("*.md"))
    if name is None:
        return {"available": available}
    if name not in available:
        return {"error": f"unknown runbook {name!r}", "available": available}
    return {"name": name, "content": (RUNBOOKS_DIR / f"{name}.md").read_text()}
