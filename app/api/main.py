from fastapi import FastAPI

app = FastAPI(
    title="AI Incident Copilot",
    description="Receives Datadog-style alerts and returns an AI-written incident summary.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
