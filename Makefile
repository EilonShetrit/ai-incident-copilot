.PHONY: help install up down debug status api test lint format

help:  ## Show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	uv sync

up:  ## Start OpenSearch and wait until it is healthy
	docker compose up -d --wait opensearch
	@curl -s http://localhost:9200 | head -20

down:  ## Stop all containers
	docker compose --profile debug down

debug:  ## Start OpenSearch Dashboards on :5601
	docker compose --profile debug up -d --wait

status:  ## Show OpenSearch cluster health
	@curl -s "http://localhost:9200/_cluster/health?pretty"

api:  ## Run the FastAPI server on :8000
	uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

test:  ## Run tests
	uv run pytest -q

lint:  ## Check code style
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-format code
	uv run ruff check --fix .
	uv run ruff format .
