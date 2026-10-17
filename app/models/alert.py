from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class DatadogAlert(BaseModel):
    """The subset of a Datadog monitor webhook payload the agent needs.

    Field names follow Datadog's webhook template variables ($ID, $EVENT_TITLE, $TAGS, ...).
    """

    id: str
    title: str
    body: str = ""
    alert_transition: str = "Triggered"
    priority: str | None = None
    alert_query: str | None = None
    tags: list[str] = Field(default_factory=list)
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("tags", mode="before")
    @classmethod
    def split_tags(cls, value):
        # Datadog sends $TAGS as one comma-separated string.
        if isinstance(value, str):
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return value

    def tag(self, key: str) -> str | None:
        prefix = f"{key}:"
        return next((t.removeprefix(prefix) for t in self.tags if t.startswith(prefix)), None)

    @property
    def service(self) -> str | None:
        return self.tag("service")
