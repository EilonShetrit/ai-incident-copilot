from typing import Any

from app.clients.opensearch import METRICS_INDEX, get_client
from app.tools._time import time_range

METRICS = [
    "error_rate",
    "latency_p95_ms",
    "requests",
    "db_pool_max",
    "db_pool_active",
    "memory_mb",
    "memory_limit_mb",
    "restarts",
]


def get_metrics(start: str, end: str, service: str) -> dict[str, Any]:
    """Per-minute metrics for one service, plus min/avg/max per metric."""
    body = {
        "size": 500,
        "sort": [{"@timestamp": "asc"}],
        "_source": ["@timestamp", "version", *METRICS],
        "query": {"bool": {"filter": [time_range(start, end), {"term": {"service": service}}]}},
    }
    rows = [
        hit["_source"]
        for hit in get_client().search(index=METRICS_INDEX, body=body)["hits"]["hits"]
    ]

    summary = {}
    for metric in METRICS:
        values = [row[metric] for row in rows if metric in row]
        if values:
            summary[metric] = {
                "min": min(values),
                "avg": round(sum(values) / len(values), 4),
                "max": max(values),
            }

    return {
        "service": service,
        "points": len(rows),
        "versions_seen": sorted({row["version"] for row in rows}),
        "summary": summary,
        "series": rows,
    }
