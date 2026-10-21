"""Grade an incident report against a scenario's ground truth.

Each check is pass/fail and explains itself, so a failing run says what the agent got wrong.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.agent import IncidentReport


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _norm(text: str) -> str:
    # "Roll back" and "roll-back" both count as "rollback".
    return re.sub(r"roll[\s-]+back", "rollback", text.lower())


def score(report: IncidentReport, truth: dict[str, Any]) -> list[Check]:
    rc = report.root_cause
    impacted, healthy = set(report.impacted_services), set(report.healthy_services)
    expected_impacted, expected_healthy = (
        set(truth["impacted_services"]),
        set(truth["healthy_services"]),
    )
    rc_text = _norm(f"{rc.hypothesis} {rc.trigger}")
    missing_keywords = [k for k in truth["root_cause_keywords"] if k.lower() not in rc_text]
    first_step = _norm(report.next_steps[0]) if report.next_steps else ""
    missing_step = [k for k in truth["first_step_keywords"] if k.lower() not in first_step]
    tools_cited = {e.tool for e in report.evidence}

    return [
        Check(
            "root_cause_service",
            rc.service == truth["root_cause_service"],
            f"said {rc.service!r}, expected {truth['root_cause_service']!r}",
        ),
        Check(
            "root_cause_explained",
            not missing_keywords,
            "mentions " + ", ".join(truth["root_cause_keywords"])
            if not missing_keywords
            else f"missing {missing_keywords} in hypothesis/trigger",
        ),
        Check(
            "impacted_services",
            impacted == expected_impacted,
            f"said {sorted(impacted)}, expected {sorted(expected_impacted)}",
        ),
        Check(
            "healthy_ruled_out",
            expected_healthy <= healthy and not (expected_healthy & impacted),
            f"ruled out {sorted(healthy)}, expected {sorted(expected_healthy)}",
        ),
        Check(
            "mitigation_first",
            not missing_step,
            f"first step: {report.next_steps[0] if report.next_steps else '(none)'!r}",
        ),
        Check(
            "evidence_backed",
            len(tools_cited) >= 3,
            f"evidence from {len(tools_cited)} tools: {sorted(tools_cited)}",
        ),
    ]
