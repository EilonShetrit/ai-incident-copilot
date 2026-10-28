"""Run the agent on a scenario several times and grade every report against ground truth.

    uv run python -m evals.run --runs 3                      # every scenario
    uv run python -m evals.run --scenario oom_memory_leak    # one scenario

Each run re-seeds OpenSearch, so the data is fresh relative to "now". Needs ANTHROPIC_API_KEY
and a running OpenSearch. Results go to evals/results/.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.agent import IncidentReport, investigate
from app.clients.opensearch import get_client
from app.config import settings
from app.scenarios import alert_for, scenarios, seed
from evals.scoring import score

RESULTS_DIR = Path(__file__).parent / "results"


def run_once(scenario: dict) -> dict:
    seed(scenario)
    alert = alert_for(scenario)

    started = time.perf_counter()
    result = investigate(alert)
    checks = score(result.report, scenario["ground_truth"])
    return {
        "passed": sum(c.passed for c in checks),
        "total": len(checks),
        "checks": [asdict(c) for c in checks],
        "seconds": round(time.perf_counter() - started, 1),
        "turns": result.turns,
        "tool_calls": len(result.trace),
        "usage": result.usage,
        "report": result.report.model_dump(),
    }


def to_markdown(summary: dict) -> str:
    runs = summary["runs"]
    names = [c["name"] for c in runs[0]["checks"]]
    lines = [
        f"# Eval: {summary['scenario']}",
        "",
        f"{summary['date']} · model `{summary['model']}` · {len(runs)} runs · "
        f"**{summary['score']:.0%}** of checks passed"
        + (f" (re-graded {summary['regraded']})" if summary.get("regraded") else ""),
        "",
        "| Check | " + " | ".join(f"Run {n}" for n in range(1, len(runs) + 1)) + " |",
        "|---|" + "---|" * len(runs),
    ]
    for i, name in enumerate(names):
        marks = ["✅" if run["checks"][i]["passed"] else "❌" for run in runs]
        lines.append(f"| `{name}` | " + " | ".join(marks) + " |")
    lines += [
        "| Turns | " + " | ".join(str(r["turns"]) for r in runs) + " |",
        "| Tool calls | " + " | ".join(str(r["tool_calls"]) for r in runs) + " |",
        "| Seconds | " + " | ".join(str(r["seconds"]) for r in runs) + " |",
    ]
    failures = [
        f"- Run {n}, `{c['name']}`: {c['detail']}"
        for n, run in enumerate(runs, 1)
        for c in run["checks"]
        if not c["passed"]
    ]
    if failures:
        lines += ["", "## Failures", *failures]
    return "\n".join(lines) + "\n"


def regrade(path: Path, scenario: dict) -> None:
    summary = json.loads(path.read_text())
    try:
        for run in summary["runs"]:
            IncidentReport.model_validate(run["report"])
    except ValidationError:
        sys.exit(f"{path} was saved with an older report schema; run a fresh eval instead.")
    for run in summary["runs"]:
        checks = score(IncidentReport.model_validate(run["report"]), scenario["ground_truth"])
        run["checks"] = [asdict(c) for c in checks]
        run["passed"], run["total"] = sum(c.passed for c in checks), len(checks)
    summary["score"] = sum(r["passed"] for r in summary["runs"]) / sum(
        r["total"] for r in summary["runs"]
    )
    summary["regraded"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    path.write_text(json.dumps(summary, indent=2))
    markdown = to_markdown(summary)
    (RESULTS_DIR / f"latest-{summary['scenario']}.md").write_text(markdown)
    print(markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade the agent against ground truth.")
    parser.add_argument(
        "--scenario", action="append", help="Scenario name (repeatable). Default: all scenarios"
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per scenario")
    parser.add_argument(
        "--regrade",
        metavar="RESULTS_JSON",
        help="Re-score the reports saved in a results file (no API calls), e.g. after a grader fix",
    )
    args = parser.parse_args()

    if args.regrade:
        summary = json.loads(Path(args.regrade).read_text())
        regrade(Path(args.regrade), scenarios()[summary["scenario"]])
        return

    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY is not set.")
    if not get_client().ping():
        sys.exit(f"OpenSearch is not reachable at {settings.opensearch_url}. Run `make up`.")

    names = args.scenario or list(scenarios())
    unknown = set(names) - set(scenarios())
    if unknown:
        sys.exit(f"Unknown scenario(s) {sorted(unknown)}. Available: {sorted(scenarios())}")
    for name in names:
        evaluate(scenarios()[name], args.runs)


def evaluate(scenario: dict, n_runs: int) -> None:
    runs = []
    for n in range(1, n_runs + 1):
        print(f"{scenario['name']}: run {n}/{n_runs}...", file=sys.stderr)
        runs.append(run_once(scenario))
        print(f"  {runs[-1]['passed']}/{runs[-1]['total']} checks passed", file=sys.stderr)

    summary = {
        "scenario": scenario["name"],
        "model": settings.claude_model,
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "score": sum(r["passed"] for r in runs) / sum(r["total"] for r in runs),
        "runs": runs,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS_DIR / f"{scenario['name']}-{stamp}.json").write_text(json.dumps(summary, indent=2))
    markdown = to_markdown(summary)
    (RESULTS_DIR / f"latest-{scenario['name']}.md").write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
