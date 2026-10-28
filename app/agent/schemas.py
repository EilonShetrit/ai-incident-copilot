from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.catalog import code_label


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(description="The tool call this finding came from, e.g. search_logs")
    finding: str = Field(description="What the tool result showed, with concrete numbers")


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str = Field(description="ISO-8601 UTC timestamp")
    event: str


class RootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(description="The service where the failure originates")
    hypothesis: str = Field(description="What went wrong and why, in one or two sentences")
    trigger: str = Field(description="The change that set it off, e.g. a deploy, or 'unknown'")
    confidence: Literal["low", "medium", "high"]


class ErrorCodeStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    code: int = Field(description="HTTP status code, e.g. 502")
    count: int = Field(description="Failed requests with this code in the incident window")


class FailureMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Id from get_failure_modes, or 'other' if none fits")
    name: str
    why: str = Field(description="Which of its signals the evidence shows")


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="One-line incident title")
    severity: Literal["SEV1", "SEV2", "SEV3"]
    summary: str = Field(description="Two or three sentences an on-call engineer reads first")
    impact: str = Field(description="Who or what is affected, how badly, since when")
    impacted_services: list[str]
    healthy_services: list[str] = Field(description="Services checked and ruled out")
    root_cause: RootCause
    failure_mode: FailureMode = Field(description="The real-world failure mode this incident is")
    error_codes: list[ErrorCodeStat] = Field(
        description="Status code breakdown per affected service, from get_error_codes"
    )
    evidence: list[Evidence]
    timeline: list[TimelineEvent]
    next_steps: list[str] = Field(description="Ordered actions, most urgent first")
    runbook: str | None = Field(description="Name of the runbook followed, if any")

    def to_markdown(self) -> str:
        rc = self.root_cause
        lines = [
            f"# {self.severity}: {self.title}",
            "",
            self.summary,
            "",
            f"**Impact:** {self.impact}",
            f"**Impacted:** {', '.join(self.impacted_services) or '-'}",
            f"**Ruled out:** {', '.join(self.healthy_services) or '-'}",
            "",
            f"## Root cause ({rc.confidence} confidence)",
            f"`{rc.service}`: {rc.hypothesis}",
            f"Trigger: {rc.trigger}",
            "",
            f"## Failure mode: {self.failure_mode.name}",
            self.failure_mode.why,
            "",
            "## Error codes",
            *self._error_code_lines(),
            "",
            "## Evidence",
            *[f"- `{e.tool}`: {e.finding}" for e in self.evidence],
            "",
            "## Timeline",
            *[f"- {t.time}  {t.event}" for t in self.timeline],
            "",
            "## Next steps",
            *[f"{i}. {step}" for i, step in enumerate(self.next_steps, 1)],
        ]
        if self.runbook:
            lines += ["", f"Runbook: `{self.runbook}`"]
        return "\n".join(lines)

    def _error_code_lines(self) -> list[str]:
        lines = []
        for service in dict.fromkeys(e.service for e in self.error_codes):
            lines.append(f"**{service}**")
            for e in sorted(
                (e for e in self.error_codes if e.service == service), key=lambda e: -e.count
            ):
                lines.append(f"* {code_label(e.code)}: {e.count}")
        return lines
