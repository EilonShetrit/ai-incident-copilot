from typing import Any

from app.catalog import status_codes
from app.clients.opensearch import LOGS_INDEX, get_client
from app.tools._time import time_range


def get_error_codes(start: str, end: str, service: str | None = None) -> dict[str, Any]:
    """Failed requests per service broken down by HTTP status code (4xx and 5xx).

    Codes the monitors watch (460, 500-504) come with their label, meaning and common causes.
    """
    filters: list[dict] = [time_range(start, end)]
    if service:
        filters.append({"term": {"service": service}})
    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "services": {
                "terms": {"field": "service", "size": 50},
                "aggs": {
                    "failed": {
                        "filter": {"range": {"status_code": {"gte": 400}}},
                        "aggs": {"codes": {"terms": {"field": "status_code", "size": 20}}},
                    }
                },
            }
        },
    }
    aggs = get_client().search(index=LOGS_INDEX, body=body)["aggregations"]
    catalog = status_codes()

    services, seen = {}, set()
    for bucket in aggs["services"]["buckets"]:
        requests = bucket["doc_count"]
        codes = []
        for code_bucket in bucket["failed"]["codes"]["buckets"]:
            code = int(code_bucket["key"])
            seen.add(code)
            info = catalog.get(code, {})
            codes.append(
                {
                    "code": code,
                    "label": f"{info['emoji']} {info['label']}" if info else "unmonitored",
                    "count": code_bucket["doc_count"],
                    "share_of_requests": round(code_bucket["doc_count"] / requests, 4),
                }
            )
        services[bucket["key"]] = {
            "requests": requests,
            "failed": bucket["failed"]["doc_count"],
            "codes": sorted(codes, key=lambda c: -c["count"]),
        }

    reference = {
        code: {"meaning": catalog[code]["meaning"], "common_causes": catalog[code]["causes"]}
        for code in sorted(seen)
        if code in catalog
    }
    return {"services": services, "code_reference": reference}
