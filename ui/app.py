"""Streamlit UI: fire an alert, watch the agent investigate, read the report.

make api   # terminal 1
make ui    # terminal 2, then open :8501
"""

import json

import httpx
import pandas as pd
import streamlit as st

from ui import api_client

st.set_page_config(page_title="AI Incident Copilot", page_icon="🚨", layout="wide")

STATUS_ICON = {"investigating": "🔎", "resolved": "✅", "failed": "❌"}
SEVERITY_COLOR = {"SEV1": "red", "SEV2": "orange", "SEV3": "blue"}
TOOL_ICON = {
    "get_deploy_events": "🚀",
    "search_logs": "📜",
    "get_metrics": "📈",
    "get_service_map": "🗺️",
    "get_runbook": "📘",
}


def short_time(value: str | None) -> str:
    """HH:MM for ISO timestamps; date math such as now-15m is shown as is."""
    if value and len(value) >= 16 and value[10] == "T":
        return value[11:16]
    return value or ""


def describe_call(call: dict) -> str:
    args = ", ".join(f"{k}={v}" for k, v in call["input"].items() if k not in ("start", "end"))
    window = ""
    if "start" in call["input"]:
        window = f" · {short_time(call['input']['start'])}–{short_time(call['input'].get('end'))}"
    icon = "⚠️" if call["is_error"] else TOOL_ICON.get(call["tool"], "🔧")
    return f"{icon} **{call['tool']}**({args}){window} · {call['duration_ms']} ms"


# ---------- sidebar ----------

with st.sidebar:
    st.title("🚨 AI Incident Copilot")
    st.caption("An AI on-call agent. All data is synthetic.")

    api_up = api_client.is_up()
    if not api_up:
        st.error(f"API not reachable at {api_client.API_URL}. Start it with `make api`.")
        st.stop()

    if st.button("Fire sample alert", type="primary", use_container_width=True):
        try:
            st.session_state.selected = api_client.fire_sample_alert()["incident_id"]
        except httpx.HTTPStatusError as exc:
            st.error(exc.response.json().get("detail", str(exc)))
    st.caption("Sends `samples/alert_5xx.json` to `POST /webhooks/datadog`.")

    incidents = api_client.list_incidents()
    if incidents:
        st.subheader("Incidents")
        ids = [i["id"] for i in incidents]
        labels = {
            i["id"]: f"{STATUS_ICON[i['status']]} {i['service'] or '?'} · {i['created_at'][11:19]}"
            for i in incidents
        }
        if st.session_state.get("selected") not in ids:
            st.session_state.selected = ids[0]
        st.radio(
            "Incidents",
            ids,
            key="selected",
            format_func=labels.get,
            label_visibility="collapsed",
        )


# ---------- main ----------

if not incidents:
    st.header("No incidents yet")
    st.markdown(
        "Click **Fire sample alert** to send a Datadog-style alert. The agent will pull logs, "
        "metrics and deploys from OpenSearch, follow the service map, read the runbook and "
        "write an incident report. You can watch every step here as it happens."
    )
    st.stop()


def render_trace(trace: list[dict], investigating: bool) -> None:
    st.subheader(f"Investigation · {len(trace)} tool calls")
    if investigating:
        st.info("The agent is investigating…", icon="🔎")
    for n, call in enumerate(trace, 1):
        with st.expander(f"{n}. {describe_call(call)}"):
            st.caption("Input")
            st.json(call["input"])
            st.caption("Result")
            if isinstance(call["result"], str):
                st.code(call["result"])
            else:
                st.json(call["result"], expanded=False)


IMPACTED_COLORS = ["#d62728", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2"]
HEALTHY_COLOR = "#7f7f7f"


def render_error_rates(impacted: list[str], healthy: list[str]) -> None:
    frames, colors = {}, []
    for n, service in enumerate(impacted + healthy):
        metrics = api_client.service_metrics(service, minutes=30)
        if metrics and metrics["series"]:
            series = pd.DataFrame(metrics["series"])
            frames[service] = series.set_index(pd.to_datetime(series["@timestamp"]))["error_rate"]
            is_healthy = n >= len(impacted)
            colors.append(
                HEALTHY_COLOR if is_healthy else IMPACTED_COLORS[n % len(IMPACTED_COLORS)]
            )
    if frames:
        st.subheader("Error rate, last 30 minutes")
        st.caption("Impacted services in color, ruled-out services in gray.")
        st.line_chart(pd.DataFrame(frames) * 100, y_label="% of requests failing", color=colors)


def render_report(incident: dict) -> None:
    report = incident["report"]
    rc = report["root_cause"]
    color = SEVERITY_COLOR[report["severity"]]
    st.subheader(f":{color}-background[{report['severity']}] {report['title']}")
    st.markdown(report["summary"])

    cols = st.columns([2, 1, 1, 1])
    cols[0].metric("Root cause", rc["service"])
    cols[1].metric("Confidence", rc["confidence"].title())
    cols[2].metric("Impacted services", len(report["impacted_services"]))
    cols[3].metric("Tool calls", len(incident["trace"]))

    st.error(f"**Root cause:** {rc['hypothesis']}\n\n**Trigger:** {rc['trigger']}", icon="🎯")
    st.markdown(f"**Impact:** {report['impact']}")

    left, right = st.columns(2)
    left.markdown(
        "**Impacted:** " + " ".join(f":red-badge[{s}]" for s in report["impacted_services"])
    )
    right.markdown(
        "**Ruled out:** " + " ".join(f":green-badge[{s}]" for s in report["healthy_services"])
    )

    st.markdown("#### Next steps")
    st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(report["next_steps"], 1)))
    if report["runbook"]:
        st.caption(f"Runbook: `{report['runbook']}`")

    render_error_rates(report["impacted_services"], report["healthy_services"])

    with st.expander("Evidence", expanded=True):
        st.markdown("\n".join(f"- `{e['tool']}`: {e['finding']}" for e in report["evidence"]))
    with st.expander("Timeline"):
        st.markdown("\n".join(f"- **{t['time']}** {t['event']}" for t in report["timeline"]))

    st.download_button(
        "Download report (Markdown)",
        api_client.get_report_markdown(incident["id"]),
        file_name=f"{incident['id']}.md",
    )
    usage = incident.get("usage") or {}
    if usage:
        cached = usage.get("cache_read_input_tokens", 0)
        total_in = sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens"))
        st.caption(
            f"Tokens: {total_in + cached:,} in ({cached:,} from cache) · "
            f"{usage.get('output_tokens', 0):,} out"
        )


def incident_view(incident_id: str) -> None:
    incident = api_client.get_incident(incident_id)
    alert = incident["alert"]
    investigating = incident["status"] == "investigating"

    st.title(alert["title"])
    st.caption(
        f"{STATUS_ICON[incident['status']]} {incident['status']} · {incident['id']} · "
        f"fired {alert['date'][:19].replace('T', ' ')} UTC · " + " ".join(alert["tags"])
    )

    report_col, trace_col = st.columns([3, 2], gap="large")
    with trace_col:
        render_trace(incident["trace"], investigating)
        with st.expander("Alert payload"):
            st.code(json.dumps(alert, indent=2), language="json")
    with report_col:
        if incident["status"] == "resolved":
            render_report(incident)
        elif incident["status"] == "failed":
            st.error(f"Investigation failed: {incident['error']}")
        else:
            st.subheader("Report")
            st.caption("The report appears here when the investigation is done.")

    # Stop polling once the agent is done; a full rerun refreshes the sidebar too.
    if st.session_state.get("was_investigating") and not investigating:
        st.session_state.was_investigating = False
        st.rerun()
    st.session_state.was_investigating = investigating


selected = st.session_state.selected
if api_client.get_incident(selected)["status"] == "investigating":
    st.fragment(run_every=2)(incident_view)(selected)
else:
    incident_view(selected)
