import secrets

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.agent import InvestigationError, investigate
from app.catalog import status_codes
from app.config import settings
from app.incidents import Incident, IncidentStatus, store
from app.models import DatadogAlert
from app.tools import get_metrics, get_service_map

app = FastAPI(
    title="AI Incident Copilot",
    description="Receives Datadog-style alerts and returns an AI-written incident summary.",
    version="0.1.0",
)


def run_investigation(incident_id: str) -> None:
    incident = store.get(incident_id)
    try:
        result = investigate(
            incident.alert, on_tool_call=lambda call: store.add_tool_call(incident_id, call)
        )
    except InvestigationError as exc:
        store.finish(incident_id, status=IncidentStatus.FAILED, error=str(exc))
    except Exception as exc:  # API errors, network errors: record them, don't lose the incident
        store.finish(
            incident_id, status=IncidentStatus.FAILED, error=f"{type(exc).__name__}: {exc}"
        )
    else:
        store.finish(
            incident_id, status=IncidentStatus.RESOLVED, report=result.report, usage=result.usage
        )


def check_token(token: str | None) -> None:
    if settings.webhook_token and not secrets.compare_digest(token or "", settings.webhook_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-Webhook-Token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/webhooks/datadog",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Not a trigger, or already being investigated"}},
)
def datadog_webhook(
    alert: DatadogAlert,
    background: BackgroundTasks,
    response: Response,
    x_webhook_token: str | None = Header(None),
) -> dict:
    """Receive a Datadog monitor notification and start an investigation in the background.

    Returns at once with the incident id; poll `GET /incidents/{id}` for the trace and report.
    """
    check_token(x_webhook_token)
    if not settings.anthropic_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ANTHROPIC_API_KEY is not set")
    if alert.alert_transition.lower() not in {"triggered", "re-triggered"}:
        response.status_code = status.HTTP_200_OK
        return {"status": "ignored", "reason": f"alert_transition is {alert.alert_transition!r}"}

    incident, created = store.create(alert)
    if created:
        background.add_task(run_investigation, incident.id)
    else:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = f"/incidents/{incident.id}"
    return {"incident_id": incident.id, "status": incident.status, "duplicate": not created}


@app.get("/incidents")
def list_incidents() -> list[dict]:
    return [
        {
            "id": i.id,
            "status": i.status,
            "title": i.alert.title,
            "service": i.alert.service,
            "created_at": i.created_at,
            "tool_calls": len(i.trace),
        }
        for i in store.list()
    ]


def get_or_404(incident_id: str) -> Incident:
    incident = store.get(incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No incident {incident_id!r}")
    return incident


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Incident:
    return get_or_404(incident_id)


@app.get("/incidents/{incident_id}/report.md", response_class=PlainTextResponse)
def get_report_markdown(incident_id: str) -> str:
    incident = get_or_404(incident_id)
    if incident.report is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Incident is {incident.status}, no report")
    return incident.report.to_markdown()


@app.get("/services")
def list_services() -> dict:
    """The service catalog: owners and dependencies."""
    return get_service_map()


@app.get("/services/{service}/metrics")
def service_metrics(service: str, minutes: int = Query(30, ge=1, le=240)) -> dict:
    """Per-minute metrics for one service over the last N minutes (for dashboards)."""
    try:
        return get_metrics(start=f"now-{minutes}m", end="now", service=service)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Metrics unavailable: {type(exc).__name__}"
        ) from exc


@app.get("/catalog/status-codes")
def monitored_status_codes() -> dict:
    """The HTTP status codes the monitors watch, with emoji and label."""
    return {
        str(code): {"emoji": info["emoji"], "label": info["label"], "meaning": info["meaning"]}
        for code, info in status_codes().items()
    }
