"""Run an investigation tool from the terminal and print its JSON result.

Examples:
    uv run python -m app.tools get_deploy_events --start now-30m --end now
    uv run python -m app.tools search_logs --service payments --level ERROR \
        --start now-15m --end now
    uv run python -m app.tools get_metrics --service api-gateway --start now-20m --end now
    uv run python -m app.tools get_runbook --name high_5xx_rate
"""

import json
import sys

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from app.config import settings
from app.tools import TOOLS


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in TOOLS:
        print(__doc__)
        print("Tools:", ", ".join(TOOLS))
        sys.exit(1)

    name, rest = argv[0], argv[1:]
    if len(rest) % 2:
        sys.exit("Arguments must be --name value pairs")
    kwargs = {}
    for flag, value in zip(rest[::2], rest[1::2], strict=True):
        key = flag.removeprefix("--").replace("-", "_")
        kwargs[key] = int(value) if value.isdigit() else value

    try:
        result = TOOLS[name](**kwargs)
    except OpenSearchConnectionError:
        url = settings.opensearch_url
        sys.exit(f"OpenSearch is not reachable at {url}. Run `make up`, then `make seed`.")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
