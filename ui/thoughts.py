"""Investigation steps as thinking lines: get_service_map() -> "Getting service map…"."""

TOOL_ICON = {
    "get_deploy_events": "🚀",
    "search_logs": "📜",
    "get_metrics": "📈",
    "get_service_map": "🗺️",
    "get_runbook": "📘",
    "get_error_codes": "🚦",
    "get_failure_modes": "🧭",
}


def thought(call: dict) -> str:
    """What the agent is doing in this step, in words: get_service_map() -> Getting service map…"""
    args = call["input"]
    service = args.get("service")
    match call["tool"]:
        case "get_metrics":
            line = f"Checking {service} metrics"
        case "get_service_map":
            line = "Getting service map"
        case "get_deploy_events":
            line = (
                f"Looking for recent {service} deploys" if service else "Looking for recent deploys"
            )
        case "search_logs":
            what = " ".join(x for x in (service, args.get("level")) if x)
            line = f"Searching {what} logs" if what else "Searching logs"
            if args.get("query"):
                line += f' for "{args["query"]}"'
        case "get_error_codes":
            line = "Breaking errors down by status code"
            if service:
                line += f" for {service}"
        case "get_failure_modes":
            line = "Matching against known failure modes"
        case "get_runbook":
            line = (
                f"Reading the {args['name']} runbook" if args.get("name") else "Looking up runbooks"
            )
        case _:
            line = f"Running {call['tool']}"
    if call["is_error"]:
        return f"⚠️ {line} failed"
    return f"{TOOL_ICON.get(call['tool'], '🔧')} {line}…"
