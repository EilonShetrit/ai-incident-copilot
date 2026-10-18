# AI Incident Copilot

> An AI on-call agent: it receives a Datadog-style alert, investigates logs, metrics and recent deploys on its own, and writes the incident summary — impact, root-cause hypothesis and runbook next steps.

[![CI](https://github.com/EilonShetrit/ai-incident-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/EilonShetrit/ai-incident-copilot/actions/workflows/ci.yml)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/EilonShetrit/ai-incident-copilot)

> **All data in this project is synthetic.** No real systems, customers or logs are used.

🚧 **Status:** early development. The first end-to-end scenario, *"5xx spike after a deploy"*, is in progress.

## Why

When an alert fires, the first 10–15 minutes of on-call go to the same routine: open the dashboard, pull logs for the window, check what was deployed, look at downstream services, find the runbook. This project hands that routine to an agent, so the engineer starts from a written hypothesis instead of a blank screen.

## How it works

```mermaid
flowchart LR
    A[Alert webhook<br/>Datadog format] --> B[FastAPI]
    B --> C[Agent<br/>Claude API + tool use]
    C <--> D[(OpenSearch<br/>logs · metrics · deploys)]
    C <--> E[Runbooks]
    C --> F[Incident report]
    F --> G[Streamlit UI]
```

The agent calls tools such as `search_logs`, `get_metrics`, `get_deploy_events` and `get_runbook`, and every claim in the final report is backed by evidence from a tool result.

## Quickstart

**Option A: GitHub Codespaces (nothing to install).** Click the badge above, add `ANTHROPIC_API_KEY` as a [Codespaces secret](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces), then:

```bash
make up     # start OpenSearch
make seed   # load the synthetic incident data
make investigate  # let the agent investigate the sample alert
make test   # run tests
make api    # start the API on :8000 (docs at /docs)
```

**Option B: locally.** Requires Docker, Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env   # add your ANTHROPIC_API_KEY
make install
make up
make seed
```

Run `make help` for all commands.

## Investigation tools

Each tool returns a compact summary (counts, top messages, min/avg/max), not thousands of raw
lines, so the agent's context stays small and focused. Every tool also runs from the terminal:

```bash
uv run python -m app.tools get_deploy_events --start now-30m --end now
uv run python -m app.tools search_logs --service payments --level ERROR --start now-15m --end now
uv run python -m app.tools get_metrics --service api-gateway --start now-20m --end now
uv run python -m app.tools get_service_map
uv run python -m app.tools get_runbook --name high_5xx_rate
```

| Tool | What it answers |
|---|---|
| `get_deploy_events` | What changed, and when? |
| `search_logs` | What are the errors, from which version and host? |
| `get_metrics` | How bad is it, and since when? |
| `get_service_map` | Who calls whom, and who owns it? |
| `get_runbook` | What does our process say to do next? |

## The agent

```bash
uv run python -m app.agent --alert samples/alert_5xx.json          # Markdown report
uv run python -m app.agent --alert samples/alert_5xx.json --json   # report + full trace
```

The agent gets the alert ([`samples/alert_5xx.json`](samples/alert_5xx.json), Datadog webhook
format) and runs a tool-use loop with Claude: it decides which tool to call, reads the result and
decides again, until it can write the report. Every tool call is printed as it happens and kept
in a trace.

- **Structured output.** The final answer is constrained to a JSON schema generated from the
  [`IncidentReport`](app/agent/schemas.py) Pydantic model: severity, impact, impacted and
  ruled-out services, root cause with confidence, evidence per tool, timeline and next steps.
- **Validated tool calls.** Each tool's input schema comes from a Pydantic model, and the same
  model validates Claude's arguments. Bad arguments or a failing tool go back to Claude as an
  error it can recover from, instead of crashing the run.
- **Guardrails.** A turn limit, explicit handling of refusals and `max_tokens`, and
  server-side model fallbacks if a request is declined.
- **Tested without the API.** [`tests/test_agent.py`](tests/test_agent.py) drives the loop with
  a scripted fake Claude client, so CI needs no API key.

## Alert webhook API

Point a Datadog webhook (or anything that speaks its payload format) at the API, and the agent
investigates in the background:

```bash
make api      # terminal 1: start the API on :8000
make alert    # terminal 2: send samples/alert_5xx.json
# {"incident_id":"inc-3f9a1c2e","status":"investigating","duplicate":false}

curl -s localhost:8000/incidents/inc-3f9a1c2e            # trace so far, then the report
curl -s localhost:8000/incidents/inc-3f9a1c2e/report.md  # report as Markdown
```

| Endpoint | What it does |
|---|---|
| `POST /webhooks/datadog` | Opens an incident and starts the investigation. Returns `202` at once. |
| `GET /incidents` | All incidents, newest first. |
| `GET /incidents/{id}` | Status (`investigating`, `resolved`, `failed`), the live tool-call trace and the report. |
| `GET /incidents/{id}/report.md` | The report as Markdown. |

The webhook behaves the way on-call tooling should:

- **Fast acknowledgement.** An investigation takes a minute or two, longer than a webhook
  sender waits, so it runs in the background and the response carries the incident id.
- **Idempotent.** Datadog retries failed deliveries and re-notifies while a monitor stays red.
  An alert that is already under investigation returns the existing incident.
- **Only triggers start work.** `Recovered` notifications are acknowledged and ignored.
- **Optional shared secret.** Set `WEBHOOK_TOKEN` and the endpoint requires a matching
  `X-Webhook-Token` header.

Interactive docs are at `/docs`. Ready-made requests are in [`api/requests.http`](api/requests.http)
(VS Code REST Client, preinstalled in the dev container) and a
[Postman collection](api/ai-incident-copilot.postman_collection.json) that chains the incident id
between requests.

## The scenario

A small shop: `api-gateway → checkout → payments → postgres`, plus `inventory`.
At T+0, `payments v2.4.0` ships with its DB connection pool cut from 50 to 5. Two minutes later
requests start timing out waiting for a connection: `payments` returns 503, `checkout` returns 502,
and the monitor fires on **`api-gateway`** at T+5 with ~18% 5xx. `inventory` stays healthy.

The alert points at the gateway; the root cause is two hops downstream. The full timeline and the
expected conclusion live in [`scenarios/5xx_after_deploy.yaml`](scenarios/5xx_after_deploy.yaml).

## Tech stack

Python 3.12 · FastAPI · Claude API (tool use) · OpenSearch · Streamlit · Docker Compose · GitHub Actions

## Roadmap

- [x] Project skeleton, dev container, CI
- [x] Synthetic microservice logs, metrics and deploy events
- [x] Investigation tools over OpenSearch
- [x] Agent loop with structured incident report
- [x] Alert webhook API
- [ ] Streamlit UI with live investigation timeline
- [ ] Scenario eval against ground truth
- [ ] Demo video

## License

[MIT](LICENSE)
