from functools import lru_cache

from opensearchpy import OpenSearch

from app.config import settings

LOGS_INDEX = "logs-synthetic"
METRICS_INDEX = "metrics-synthetic"
DEPLOYS_INDEX = "deploys-synthetic"


@lru_cache
def get_client() -> OpenSearch:
    return OpenSearch(settings.opensearch_url, timeout=10)
