from typing import Any

from app.catalog import failure_modes


def get_failure_modes() -> dict[str, Any]:
    """The catalog of real-world failure modes, with the signals that identify each one."""
    return {"failure_modes": failure_modes()}
