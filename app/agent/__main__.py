"""Run the agent on an alert file from the terminal.

uv run python -m app.agent --alert samples/alert_5xx.json
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta

from app.agent import InvestigationError, ToolCall, investigate
from app.clients.opensearch import get_client
from app.config import settings
from app.models import DatadogAlert


def print_call(call: ToolCall) -> None:
    args = " ".join(f"{k}={v}" for k, v in call.input.items())
    status = "error" if call.is_error else "ok"
    print(f"  [{call.turn}] {call.tool} {args}  ({status}, {call.duration_ms} ms)", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate an alert with Claude.")
    parser.add_argument("--alert", required=True, help="Path to a Datadog webhook JSON payload")
    parser.add_argument(
        "--fired-minutes-ago",
        type=int,
        default=5,
        help="Alert time when the payload has no date (the seeded scenario fires at now-5m)",
    )
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    args = parser.parse_args()

    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY is not set. Add it as a Codespaces secret or in .env.")
    if not get_client().ping():
        sys.exit(
            f"OpenSearch is not reachable at {settings.opensearch_url}. Run `make up`, "
            "then `make seed`."
        )

    with open(args.alert) as f:
        payload = json.load(f)
    payload.setdefault("date", datetime.now(UTC) - timedelta(minutes=args.fired_minutes_ago))
    alert = DatadogAlert.model_validate(payload)

    print(f"Investigating: {alert.title}", file=sys.stderr)
    try:
        result = investigate(alert, on_tool_call=print_call)
    except InvestigationError as exc:
        sys.exit(f"Investigation failed: {exc}")
    u = result.usage
    cached = u["cache_read_input_tokens"]
    total_in = u["input_tokens"] + u["cache_creation_input_tokens"] + cached
    print(
        f"Done in {result.turns} turns, {len(result.trace)} tool calls, "
        f"{total_in} input tokens ({cached} from cache) / {u['output_tokens']} output tokens\n",
        file=sys.stderr,
    )

    print(
        json.dumps(result.to_dict(), indent=2, default=str)
        if args.json
        else result.report.to_markdown()
    )


if __name__ == "__main__":
    main()
