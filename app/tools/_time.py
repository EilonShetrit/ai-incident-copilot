def time_range(start: str, end: str) -> dict:
    """Range filter on @timestamp.

    Accepts ISO-8601 timestamps or OpenSearch date math such as "now-15m".
    """
    return {"range": {"@timestamp": {"gte": start, "lte": end}}}
