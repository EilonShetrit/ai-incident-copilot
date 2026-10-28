"""Generate synthetic logs, metrics and deploy events for a scenario.

All output is deterministic for a given scenario seed and anchor time, so tests and
demos always see the same incident.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

PATHS = {
    "api-gateway": ["/api/v1/checkout", "/api/v1/cart", "/api/v1/orders"],
    "checkout": ["/checkout/submit", "/checkout/quote"],
    "payments": ["/payments/authorize", "/payments/capture"],
    "inventory": ["/inventory/reserve", "/inventory/stock"],
}
HTTP_METHOD = {"api-gateway": "POST", "checkout": "POST", "payments": "POST", "inventory": "GET"}
# Optional per-service gauges, emitted when the scenario defines them.
GAUGES = ("db_pool_max", "db_pool_active", "memory_mb", "memory_limit_mb", "restarts")
REQUESTS_SCALE = 25  # each sampled log line stands for this many real requests


@dataclass
class Dataset:
    logs: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    deploys: list[dict[str, Any]] = field(default_factory=list)
    deploy_time: datetime | None = None


def load_scenario(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def default_anchor(scenario: dict[str, Any]) -> datetime:
    """Place the deploy so the last data point is the current minute."""
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    return now - timedelta(minutes=scenario["window"]["end"])


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _state_at(scenario: dict[str, Any], service: str, minute: int) -> dict[str, Any]:
    """Return the target metric values and active fault for a service at minute T+m."""
    state = dict(scenario["services"][service]["baseline"])
    active_fault = None
    for fault in scenario.get("faults", []):
        if fault["service"] != service or minute < fault["starts_at"]:
            continue
        progress = min(1.0, (minute - fault["starts_at"] + 1) / max(fault.get("ramp", 1), 1))
        for key, target in fault["effect"].items():
            base = state.get(key, target)
            state[key] = base + (target - base) * progress
        if "errors" in fault or "status_code" in fault:
            active_fault = fault
    return {"values": state, "fault": active_fault}


def _version_at(scenario: dict[str, Any], service: str, minute: float) -> str:
    version = scenario["services"][service]["version"]
    for deploy in sorted(scenario.get("deploys", []), key=lambda d: d["at"]):
        if deploy["service"] == service and minute >= deploy["at"]:
            version = deploy["to_version"]
    return version


def _pick_error(rng: random.Random, fault: dict[str, Any]) -> tuple[int, str, str]:
    """(status, level, message) for one failed request, from the fault's error mix."""
    if "errors" not in fault:
        return fault["status_code"], "ERROR", fault["error_message"]
    choice = rng.choices(fault["errors"], weights=[e["weight"] for e in fault["errors"]])[0]
    return choice["status_code"], choice.get("level", "ERROR"), choice["message"]


def _latency(rng: random.Random, p95: float) -> int:
    # Log-normal with sigma 0.5: p95 = median * e^(1.645 * 0.5)
    median = p95 / math.exp(1.645 * 0.5)
    return max(1, int(rng.lognormvariate(math.log(median), 0.5)))


def generate(scenario: dict[str, Any], anchor: datetime | None = None) -> Dataset:
    anchor = anchor or default_anchor(scenario)
    rng = random.Random(scenario.get("seed", 0))
    window = scenario["window"]
    rpm = scenario.get("requests_per_minute", 40)
    data = Dataset(deploy_time=anchor)

    for deploy in scenario.get("deploys", []):
        data.deploys.append(
            {
                "@timestamp": _iso(anchor + timedelta(minutes=deploy["at"])),
                "service": deploy["service"],
                "from_version": deploy["from_version"],
                "to_version": deploy["to_version"],
                "author": deploy["author"],
                "change": deploy["change"],
                "commit": deploy["commit"],
                "status": "succeeded",
            }
        )

    for minute in range(window["start"], window["end"]):
        minute_start = anchor + timedelta(minutes=minute)
        for service in scenario["services"]:
            state = _state_at(scenario, service, minute)
            values, fault = state["values"], state["fault"]
            version = _version_at(scenario, service, minute)
            errors = 0

            for _ in range(rpm):
                offset = rng.uniform(0, 60)
                ts = minute_start + timedelta(seconds=offset)
                is_error = rng.random() < values["error_rate"]
                if is_error and fault:
                    status, level, message = _pick_error(rng, fault)
                elif is_error:
                    status, level, message = 500, "ERROR", "Internal Server Error"
                else:
                    status, level, message = 200, "INFO", "request completed"
                errors += is_error
                path = rng.choice(PATHS[service])
                data.logs.append(
                    {
                        "@timestamp": _iso(ts),
                        "service": service,
                        "version": _version_at(scenario, service, minute + offset / 60),
                        "level": level,
                        "method": HTTP_METHOD[service],
                        "path": path,
                        "status_code": status,
                        "latency_ms": _latency(rng, values["latency_p95_ms"]),
                        "trace_id": f"{rng.getrandbits(64):016x}",
                        "host": f"{service}-{rng.randint(1, 3)}",
                        "message": message if status != 200 else f"{path} {status}",
                    }
                )

            metric = {
                "@timestamp": _iso(minute_start),
                "service": service,
                "version": version,
                "requests": rpm * REQUESTS_SCALE,
                "errors": errors * REQUESTS_SCALE,
                "error_rate": round(errors / rpm, 4),
                "latency_p95_ms": round(values["latency_p95_ms"] * rng.uniform(0.93, 1.07)),
            }
            for key in GAUGES:
                if key in values:
                    value = values[key]
                    if key == "memory_mb":  # real memory never sits perfectly still
                        value = min(
                            value * rng.uniform(0.98, 1.02), values.get("memory_limit_mb", value)
                        )
                    metric[key] = round(value)
            data.metrics.append(metric)

    # Startup log lines from the deploy itself: the evidence a good investigation finds.
    for deploy in scenario.get("deploys", []):
        ts = anchor + timedelta(minutes=deploy["at"], seconds=20)
        pool = _state_at(scenario, deploy["service"], deploy["at"])["values"]
        if "db_pool_max" in pool:
            data.logs.append(
                {
                    "@timestamp": _iso(ts),
                    "service": deploy["service"],
                    "version": deploy["to_version"],
                    "level": "INFO",
                    "host": f"{deploy['service']}-1",
                    "message": (
                        f"db client initialized: pool.max_size={round(pool['db_pool_max'])} "
                        "pool.timeout_ms=3000"
                    ),
                }
            )

    # Scripted log lines: Kubernetes events, GC warnings, startup config...
    for event in scenario.get("events", []):
        minute, n = event["at"], 1
        while minute <= event.get("until", event["at"]) and minute < window["end"]:
            service = event["service"]
            data.logs.append(
                {
                    "@timestamp": _iso(
                        anchor + timedelta(minutes=minute, seconds=event.get("second", 20))
                    ),
                    "service": service,
                    "version": _version_at(scenario, service, minute),
                    "level": event.get("level", "INFO"),
                    "host": event.get("host", f"{service}-{(n - 1) % 3 + 1}"),
                    "message": event["message"].format(n=n),
                }
            )
            minute += event.get("every", 1e9)
            n += 1

    data.logs.sort(key=lambda d: d["@timestamp"])
    return data
