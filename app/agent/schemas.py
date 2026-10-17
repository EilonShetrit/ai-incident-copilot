from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="One-line incident title")
    severity: Literal["SEV1", "SEV2", "SEV3"]
    summary: str = Field(description="Two or three sentences an on-call engineer reads first")
    impact: str = Field(description="Who or what is affected, how badly, since when")
    impacted_services: list[str]
    healthy_services: list[str] = Field(description="Services checked and ruled out")
    root_cause: RootCause
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
