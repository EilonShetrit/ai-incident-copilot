"""The investigation loop: Claude decides which tool to call next until it can write the report.

The loop is written by hand (instead of an SDK tool runner) so every tool call can be recorded in
a trace and streamed to the UI as it happens.
"""

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import anthropic
from pydantic import ValidationError

from app.agent.prompts import SYSTEM_PROMPT, build_user_message
from app.agent.schemas import IncidentReport
from app.agent.tool_registry import TOOL_DEFINITIONS, TOOL_SPECS
from app.config import settings
from app.models import DatadogAlert
from app.tools import TOOLS

MAX_TOKENS = 16000
MAX_TURNS = 15
MAX_RESULT_CHARS = 20_000

# Server-side fallbacks: if the primary model declines a request, the API retries it on a
# fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

REPORT_FORMAT = {"type": "json_schema", "schema": anthropic.transform_schema(IncidentReport)}


class InvestigationError(RuntimeError):
    pass


@dataclass
class ToolCall:
    turn: int
    tool: str
    input: dict[str, Any]
    result: Any
    is_error: bool
    duration_ms: int


@dataclass
class Investigation:
    report: IncidentReport
    trace: list[ToolCall]
    turns: int
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.model_dump(),
            "trace": [asdict(call) for call in self.trace],
            "turns": self.turns,
            "usage": self.usage,
        }


def run_tool(name: str, raw_input: dict[str, Any]) -> tuple[Any, bool]:
    """Validate Claude's arguments and run the tool. Returns (result, is_error)."""
    if name not in TOOL_SPECS:
        return f"Unknown tool {name!r}. Available: {', '.join(TOOL_SPECS)}", True
    model, _ = TOOL_SPECS[name]
    try:
        args = model.model_validate(raw_input).model_dump(exclude_none=True)
    except ValidationError as exc:
        return f"Invalid arguments for {name}: {exc}", True
    try:
        return TOOLS[name](**args), False
    except Exception as exc:  # the error goes back to Claude, which can retry or move on
        return f"{name} failed: {type(exc).__name__}: {exc}", True


def _serialize(result: Any) -> str:
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " ...[truncated]"
    return text


def investigate(
    alert: DatadogAlert,
    *,
    client: anthropic.Anthropic | None = None,
    now: datetime | None = None,
    max_turns: int = MAX_TURNS,
    on_tool_call: Callable[[ToolCall], None] | None = None,
) -> Investigation:
    # The key comes from the environment or .env (via settings), never from code.
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    now = now or datetime.now(UTC)
    messages: list[dict[str, Any]] = [{"role": "user", "content": build_user_message(alert, now)}]
    trace: list[ToolCall] = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for turn in range(1, max_turns + 1):
        response = client.beta.messages.create(
            model=settings.claude_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
            output_config={"effort": "high", "format": REPORT_FORMAT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens

        if response.stop_reason == "refusal":
            raise InvestigationError("Claude declined to investigate this alert")
        if response.stop_reason == "max_tokens":
            raise InvestigationError(f"Response hit max_tokens ({MAX_TOKENS}) on turn {turn}")

        # Thinking and tool_use blocks go back unchanged, as the API requires.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "pause_turn":
            continue

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                started = time.perf_counter()
                result, is_error = run_tool(block.name, block.input)
                call = ToolCall(
                    turn=turn,
                    tool=block.name,
                    input=block.input,
                    result=result,
                    is_error=is_error,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                )
                trace.append(call)
                if on_tool_call:
                    on_tool_call(call)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _serialize(result),
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
            continue

        # end_turn: with output_config.format the final text block is the report as JSON.
        text = next((b.text for b in reversed(response.content) if b.type == "text"), None)
        if text is None:
            raise InvestigationError(f"No report in final response (stop: {response.stop_reason})")
        try:
            report = IncidentReport.model_validate_json(text)
        except ValidationError as exc:
            raise InvestigationError(f"Report did not match the schema: {exc}") from exc
        return Investigation(report=report, trace=trace, turns=turn, usage=usage)

    raise InvestigationError(f"No report after {max_turns} turns")
