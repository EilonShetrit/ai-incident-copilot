from typing import Any

from app.clients.opensearch import DEPLOYS_INDEX, get_client
from app.tools._time import time_range


def get_deploy_events(start: str, end: str, service: str | None = None) -> dict[str, Any]:
    """Deploys in a time window, newest first."""
    filters: list[dict] = [time_range(start, end)]
    if service:
        filters.append({"term": {"service": service}})
    body = {"size": 50, "sort": [{"@timestamp": "desc"}], "query": {"bool": {"filter": filters}}}
    hits = get_client().search(index=DEPLOYS_INDEX, body=body)["hits"]["hits"]
    return {"count": len(hits), "deploys": [hit["_source"] for hit in hits]}
