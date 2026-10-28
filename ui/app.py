"""Streamlit UI: fire an alert, watch the agent investigate, read the report.

make api   # terminal 1
make ui    # terminal 2, then open :8501
"""

import html
import json

import altair as alt
import httpx
import pandas as pd
import streamlit as st

from ui import api_client

st.set_page_config(page_title="AI Incident Copilot", page_icon="🛟", layout="wide")

# Soft colors: red is reserved for what is actually broken.
COLORS = {
    "accent": "#4F46E5",
    "muted": "#6B7280",
    "bad": "#E5484D",
    "bad_bg": "#FDECEC",
    "warn": "#D97706",
    "warn_bg": "#FEF3E2",
    "ok": "#16A34A",
    "ok_bg": "#E8F7EE",
    "info_bg": "#EEF0FD",
}
STATUS = {
    "investigating": ("Investigating", COLORS["accent"], COLORS["info_bg"]),
    "resolved": ("Report ready", COLORS["ok"], COLORS["ok_bg"]),
    "failed": ("Failed", COLORS["bad"], COLORS["bad_bg"]),
}
SEVERITY = {
    "SEV1": (COLORS["bad"], COLORS["bad_bg"]),
    "SEV2": (COLORS["warn"], COLORS["warn_bg"]),
    "SEV3": (COLORS["accent"], COLORS["info_bg"]),
}
TOOL_ICON = {
    "get_deploy_events": "🚀",
    "search_logs": "📜",
    "get_metrics": "📈",
    "get_service_map": "🗺️",
    "get_runbook": "📘",
    "get_error_codes": "🚦",
    "get_failure_modes": "🧭",
}
SCENARIO_LABELS = {
    "5xx_after_deploy": "5xx spike after a deploy",
    "oom_memory_leak": "Memory leak → OOM kills",
}
IMPACTED_LINE_COLORS = ["#E5484D", "#F08C3A", "#A855F7", "#0EA5E9", "#EC4899"]
HEALTHY_LINE_COLOR = "#B8BEC9"

st.html(
    """
<style>
  .block-container { padding-top: 2.2rem; max-width: 1280px; }
  h1, h2, h3 { letter-spacing: -0.01em; }
  .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem;
          font-weight: 600; line-height: 1.6; margin-right: 6px; }
  .eyebrow { color: #6B7280; font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
             letter-spacing: 0.06em; margin-bottom: 2px; }
  .alert-title { font-size: 1.6rem; font-weight: 700; margin: 0 0 6px 0; line-height: 1.25; }
  .meta { color: #6B7280; font-size: 0.85rem; }
  .tag { display: inline-block; background: #EEF0F6; color: #4B5263; border-radius: 6px;
         padding: 1px 8px; font-size: 0.75rem; margin: 0 4px 4px 0; }
  .step-now { background: #EEF0FD; border-left: 3px solid #4F46E5; padding: 10px 14px;
              border-radius: 8px; margin-bottom: 8px; }
  .step { padding: 6px 14px; color: #374151; }
  .kpi-label { color: #6B7280; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
               letter-spacing: 0.04em; white-space: nowrap; }
  .kpi-value { font-size: 1.1rem; font-weight: 700; margin-top: 2px; line-height: 1.5;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  table.codes { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  table.codes th { color: #6B7280; font-weight: 600; font-size: 0.75rem; text-align: right;
                   padding: 4px 6px; border: none; white-space: nowrap; }
  table.codes td { padding: 5px 6px; border: none; border-top: 1px solid #EEF0F6; }
  table.codes td.code { white-space: nowrap; }
  table.codes td.n { text-align: right; font-weight: 600; color: #E5484D; }
  table.codes td.zero { text-align: right; color: #C4C8D2; }
  table.codes tr.dim td.code { color: #9CA3AF; }
  [data-testid="stExpander"] details summary p { font-size: 0.9rem; }
</style>
"""
)


def pill(text: str, fg: str, bg: str) -> str:
    return f'<span class="pill" style="color:{fg};background:{bg}">{html.escape(text)}</span>'


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
    return f"{icon} {call['tool']}({args}){window} · {call['duration_ms']} ms"


def deploy_times(trace: list[dict]) -> list[tuple[str, str]]:
    """(timestamp, label) of deploys the agent found, to mark them on the chart."""
    found = {}
    for call in trace:
        if call["tool"] == "get_deploy_events" and isinstance(call["result"], dict):
            for d in call["result"].get("deploys", []):
                found[d["@timestamp"]] = f"{d['service']} {d.get('to_version', '')}".strip()
    return sorted(found.items())


# ---------- sidebar ----------

with st.sidebar:
    st.markdown("### 🛟 AI Incident Copilot")
    st.caption("An AI on-call agent that investigates alerts for you. All data is synthetic.")

    if not api_client.is_up():
        st.error(f"API not reachable at {api_client.API_URL}. Start it with `make api`.")
        st.stop()

    demo = {s["name"]: s for s in api_client.list_scenarios()}
    choice = st.selectbox(
        "Scenario",
        list(demo),
        format_func=lambda n: SCENARIO_LABELS.get(n, n),
    )
    if st.button("Fire alert", type="primary", icon="🔔", use_container_width=True):
        try:
            with st.spinner("Loading the scenario's data…"):
                st.session_state.selected = api_client.fire_scenario(choice)["incident_id"]
        except httpx.HTTPStatusError as exc:
            st.error(exc.response.json().get("detail", str(exc)))
    st.caption(f"Sends a Datadog-style webhook: *{demo[choice]['alert']}*")

    incidents = api_client.list_incidents()
    if incidents:
        st.divider()
        st.markdown('<div class="eyebrow">Incidents</div>', unsafe_allow_html=True)
        ids = [i["id"] for i in incidents]
        dot = {"investigating": "🔵", "resolved": "🟢", "failed": "🔴"}
        labels = {
            i["id"]: f"{dot[i['status']]} {i['service'] or '?'} · {i['created_at'][11:16]} UTC"
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
    st.markdown('<div class="eyebrow">AI Incident Copilot</div>', unsafe_allow_html=True)
    st.header("No incidents yet")
    st.markdown("When an alert fires, the copilot does the first 15 minutes of on-call for you.")
    cols = st.columns(3)
    steps = [
        ("🔔", "1. Alert arrives", "A Datadog-style webhook hits the API."),
        (
            "🔎",
            "2. Agent investigates",
            "Claude pulls logs, metrics and deploys, and follows "
            "the service map. Every step shows up here live.",
        ),
        ("📝", "3. Report", "Severity, root cause, impact, evidence and runbook next steps."),
    ]
    for col, (icon, title, text) in zip(cols, steps, strict=True):
        with col.container(border=True):
            st.markdown(f"### {icon}")
            st.markdown(f"**{title}**")
            st.caption(text)
    st.info("Pick a scenario and click **Fire alert** in the sidebar to start.", icon="👈")
    st.stop()


def render_trace(trace: list[dict], investigating: bool) -> None:
    st.markdown(
        f'<div class="eyebrow">Investigation · {len(trace)} steps</div>', unsafe_allow_html=True
    )
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


def render_error_rates(impacted: list[str], healthy: list[str], deploys) -> None:
    rows, colors, domain = [], [], []
    for n, service in enumerate(impacted + healthy):
        metrics = api_client.service_metrics(service, minutes=30)
        if not metrics or not metrics["series"]:
            continue
        for point in metrics["series"]:
            rows.append(
                {
                    "time": pd.to_datetime(point["@timestamp"]),
                    "service": service,
                    "error_rate": point["error_rate"] * 100,
                }
            )
        domain.append(service)
        is_healthy = n >= len(impacted)
        colors.append(
            HEALTHY_LINE_COLOR
            if is_healthy
            else IMPACTED_LINE_COLORS[n % len(IMPACTED_LINE_COLORS)]
        )
    if not rows:
        return

    lines = (
        alt.Chart(pd.DataFrame(rows))
        .mark_line(strokeWidth=2.2)
        .encode(
            x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M", grid=False)),
            y=alt.Y("error_rate:Q", title="% of requests failing"),
            color=alt.Color(
                "service:N",
                scale=alt.Scale(domain=domain, range=colors),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["service", alt.Tooltip("time:T", format="%H:%M"), "error_rate:Q"],
        )
    )
    chart = lines + deploy_marks(deploys) if deploys else lines

    with st.container(border=True):
        st.markdown("**Error rate, last 30 minutes**")
        st.caption("Impacted services in color, ruled-out services in gray, deploys dashed.")
        st.altair_chart(chart.properties(height=260), use_container_width=True)


def deploy_marks(deploys):
    marks = pd.DataFrame(
        [{"time": pd.to_datetime(t), "label": f"🚀 {label}"} for t, label in deploys]
    )
    rule = alt.Chart(marks).mark_rule(strokeDash=[4, 4], color="#4F46E5").encode(x="time:T")
    text = (
        alt.Chart(marks)
        .mark_text(align="left", dx=6, dy=-6, color="#4F46E5", fontWeight=600)
        .encode(x="time:T", y=alt.value(12), text="label:N")
    )
    return rule + text


def render_memory(services: list[str], deploys) -> None:
    """Memory used vs limit, for services that report memory (shown for leaks and OOMs)."""
    rows = []
    for service in services:
        metrics = api_client.service_metrics(service, minutes=75)
        for point in (metrics or {}).get("series", []):
            if "memory_mb" in point:
                time = pd.to_datetime(point["@timestamp"])
                rows.append({"time": time, "series": f"{service} used", "mb": point["memory_mb"]})
                rows.append(
                    {"time": time, "series": f"{service} limit", "mb": point["memory_limit_mb"]}
                )
    if not rows:
        return
    df = pd.DataFrame(rows)
    lines = (
        alt.Chart(df)
        .mark_line(strokeWidth=2.2)
        .encode(
            x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M", grid=False)),
            # headroom so deploy labels sit above the limit line
            y=alt.Y("mb:Q", title="MB", scale=alt.Scale(domain=[0, df["mb"].max() * 1.25])),
            color=alt.Color("series:N", legend=alt.Legend(orient="top", title=None)),
            strokeDash=alt.condition(
                "indexof(datum.series, 'limit') >= 0", alt.value([2, 3]), alt.value([1, 0])
            ),
        )
    )
    with st.container(border=True):
        st.markdown("**Memory, last 75 minutes**")
        st.caption("Memory used vs. container limit, deploys dashed.")
        chart = lines + deploy_marks(deploys) if deploys else lines
        st.altair_chart(chart.properties(height=220), use_container_width=True)


def render_failure_mode_and_codes(report: dict) -> None:
    fm = report["failure_mode"]
    with st.container(border=True):
        st.markdown(
            "**🧭 Failure mode** &nbsp;" + pill(fm["name"], COLORS["accent"], COLORS["info_bg"]),
            unsafe_allow_html=True,
        )
        st.caption(fm["why"])

    with st.container(border=True):
        st.markdown("**🚦 Error codes monitored**")
        legend = api_client.status_codes()
        services = list(dict.fromkeys(e["service"] for e in report["error_codes"]))
        counts = {(e["service"], e["code"]): e["count"] for e in report["error_codes"]}
        head = "".join(f"<th>{html.escape(s)}</th>" for s in services)
        rows = []
        for code, info in legend.items():
            cells = []
            for service in services:
                n = counts.get((service, int(code)), 0)
                cells.append(f'<td class="{"n" if n else "zero"}">{n or "·"}</td>')
            seen = any(counts.get((s, int(code))) for s in services)
            rows.append(
                f'<tr class="{"" if seen else "dim"}"><td class="code">{code} - '
                f"{info['emoji']} {html.escape(info['label'])}</td>{''.join(cells)}</tr>"
            )
        st.markdown(
            f'<table class="codes"><tr><th></th>{head}</tr>{"".join(rows)}</table>',
            unsafe_allow_html=True,
        )


def kpi(col, label: str, value: str) -> None:
    with col.container(border=True):
        st.markdown(
            f'<div class="kpi-label">{html.escape(label)}</div>'
            f'<div class="kpi-value">{html.escape(value)}</div>',
            unsafe_allow_html=True,
        )


def render_report(incident: dict) -> None:
    report = incident["report"]
    rc = report["root_cause"]

    with st.container(border=True):
        fg, bg = SEVERITY[report["severity"]]
        st.markdown(pill(report["severity"], fg, bg), unsafe_allow_html=True)
        st.subheader(report["title"])
        st.markdown(report["summary"])

    cols = st.columns(4)
    kpi(cols[0], "Root cause", rc["service"])
    kpi(cols[1], "Confidence", rc["confidence"].title())
    kpi(cols[2], "Impacted", str(len(report["impacted_services"])))
    kpi(cols[3], "Steps", str(len(incident["trace"])))

    left, right = st.columns([3, 2], gap="medium")
    with left.container(border=True):
        st.markdown("**🎯 Root cause**")
        st.markdown(rc["hypothesis"])
        st.caption(f"Trigger: {rc['trigger']}")
    with right.container(border=True):
        st.markdown("**💥 Blast radius**")
        st.markdown(
            "".join(pill(s, COLORS["bad"], COLORS["bad_bg"]) for s in report["impacted_services"])
            + "".join(
                pill(f"✓ {s}", COLORS["ok"], COLORS["ok_bg"]) for s in report["healthy_services"]
            ),
            unsafe_allow_html=True,
        )
        st.caption(report["impact"])

    render_failure_mode_and_codes(report)

    with st.container(border=True):
        st.markdown("**✅ Next steps**")
        steps = report["next_steps"]
        if steps:
            st.markdown(
                f'<div class="step-now"><b>Do now:</b> {html.escape(steps[0])}</div>'
                + "".join(
                    f'<div class="step">{n}. {html.escape(s)}</div>'
                    for n, s in enumerate(steps[1:], 2)
                ),
                unsafe_allow_html=True,
            )
        if report["runbook"]:
            st.caption(f"Runbook: {report['runbook']}")

    deploys = deploy_times(incident["trace"])
    render_error_rates(report["impacted_services"], report["healthy_services"], deploys)
    render_memory(report["impacted_services"], deploys)

    with st.expander("Evidence", expanded=True):
        st.markdown("\n".join(f"- `{e['tool']}`: {e['finding']}" for e in report["evidence"]))
    with st.expander("Timeline"):
        st.markdown("\n".join(f"- **{t['time']}** {t['event']}" for t in report["timeline"]))

    bottom = st.columns([1, 2])
    bottom[0].download_button(
        "Download report",
        api_client.get_report_markdown(incident["id"]),
        file_name=f"{incident['id']}.md",
        icon="⬇️",
    )
    usage = incident.get("usage") or {}
    if usage:
        cached = usage.get("cache_read_input_tokens", 0)
        total_in = sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens"))
        bottom[1].caption(
            f"Tokens: {total_in + cached:,} in ({cached:,} from cache) · "
            f"{usage.get('output_tokens', 0):,} out"
        )


def incident_view(incident_id: str) -> None:
    incident = api_client.get_incident(incident_id)
    alert = incident["alert"]
    investigating = incident["status"] == "investigating"
    label, fg, bg = STATUS[incident["status"]]

    st.markdown(
        f'<div class="eyebrow">Alert · {html.escape(incident["id"])}</div>'
        f'<div class="alert-title">{html.escape(alert["title"])}</div>'
        f'<div class="meta">{pill(label, fg, bg)}'
        f"fired {alert['date'][11:19]} UTC &nbsp; "
        + "".join(f'<span class="tag">{html.escape(t)}</span>' for t in alert["tags"])
        + "</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    report_col, trace_col = st.columns([5, 3], gap="large")
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
            with st.container(border=True):
                st.markdown("**📝 Report**")
                st.caption(
                    "The agent is following the evidence. The report appears here when it is done."
                )

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
