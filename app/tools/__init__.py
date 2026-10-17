from app.tools.deploys import get_deploy_events
from app.tools.logs import search_logs
from app.tools.metrics import get_metrics
from app.tools.runbooks import get_runbook
from app.tools.topology import get_service_map

TOOLS = {
    "search_logs": search_logs,
    "get_metrics": get_metrics,
    "get_deploy_events": get_deploy_events,
    "get_service_map": get_service_map,
    "get_runbook": get_runbook,
}

__all__ = ["TOOLS", *TOOLS]
