from typing import Any

from app.clients.opensearch import LOGS_INDEX, get_client
from app.tools._time import time_range

SAMPLE_FIELDS = ["@timestamp", "service", "version", "level", "status_code", "host", "message"]


def search_logs(
    start: str,
    end: str,
    service: str | None = None,
    level: str | None = None,
    query: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Summarize logs in a time window instead of returning raw lines.

    Returns total count, counts by level / status code / version, the most frequent
    messages, and a few sample lines (newest first).
    """
    filters: list[dict] = [time_range(start, end)]
    if service:
        filters.append({"term": {"service": service}})
    if level:
        filters.append({"term": {"level": level.upper()}})
    must = [{"match": {"message": {"query": query, "operator": "and"}}}] if query else []

    body = {
        "size": min(limit, 50),
        "track_total_hits": True,
        "sort": [{"@timestamp": "desc"}],
        "_source": SAMPLE_FIELDS,
        "query": {"bool": {"filter": filters, "must": must}},
        "aggs": {
            "by_level": {"terms": {"field": "level"}},
            "by_status": {"terms": {"field": "status_code", "size": 10}},
            "by_version": {"terms": {"field": "version", "size": 10}},
            "top_messages": {"terms": {"field": "message.raw", "size": 5}},
        },
    }
    result = get_client().search(index=LOGS_INDEX, body=body)
    aggs = result["aggregations"]

    def buckets(name: str) -> dict:
        return {str(b["key"]): b["doc_count"] for b in aggs[name]["buckets"]}

    return {
        "total": result["hits"]["total"]["value"],
        "by_level": buckets("by_level"),
        "by_status_code": buckets("by_status"),
        "by_version": buckets("by_version"),
        "top_messages": [
            {"message": b["key"], "count": b["doc_count"]} for b in aggs["top_messages"]["buckets"]
        ],
        "samples": [hit["_source"] for hit in result["hits"]["hits"]],
    }
