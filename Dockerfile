# One image for the API, the UI and the seed job; docker-compose.yml picks the command.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.32 \
    && useradd --create-home --uid 1000 app
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY app ./app
COPY ui ./ui
COPY generator ./generator
COPY catalog ./catalog
COPY runbooks ./runbooks
COPY scenarios ./scenarios
COPY samples ./samples

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
