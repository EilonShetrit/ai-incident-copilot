"""In-memory incident store.

Enough for a single-process demo: incidents are lost on restart. A real deployment would
use a database, but the interface (create / get / list / update) would stay the same.
"""

import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.agent import IncidentReport, ToolCall
from app.models import DatadogAlert


class IncidentStatus(StrEnum):
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"  # the agent finished and wrote a report
    FAILED = "failed"


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: f"inc-{uuid.uuid4().hex[:8]}")
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    alert: DatadogAlert
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    report: IncidentReport | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class IncidentStore:
    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._lock = threading.Lock()

    def create(self, alert: DatadogAlert) -> tuple[Incident, bool]:
        """Open an incident for the alert. Returns (incident, created).

        Datadog retries webhooks, and a monitor can re-notify while it stays triggered, so an
        alert that already has an open investigation returns the existing incident.
        """
        with self._lock:
            for incident in self._incidents.values():
                if (
                    incident.alert.id == alert.id
                    and incident.status == IncidentStatus.INVESTIGATING
                ):
                    return incident, False
            incident = Incident(alert=alert)
            self._incidents[incident.id] = incident
            return incident, True

    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def list(self) -> list[Incident]:
        return sorted(self._incidents.values(), key=lambda i: i.created_at, reverse=True)

    def add_tool_call(self, incident_id: str, call: ToolCall) -> None:
        with self._lock:
            self._incidents[incident_id].trace.append(asdict(call))

    def finish(self, incident_id: str, **changes: Any) -> None:
        with self._lock:
            incident = self._incidents[incident_id]
            for name, value in changes.items():
                setattr(incident, name, value)
            incident.finished_at = datetime.now(UTC)

    def clear(self) -> None:
        with self._lock:
            self._incidents.clear()


store = IncidentStore()
