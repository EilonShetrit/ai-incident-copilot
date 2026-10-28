.PHONY: help install up down debug status seed investigate api ui alert eval demo demo-down test lint format

help:  ## Show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	uv sync

up:  ## Start OpenSearch and wait until it is healthy
	docker compose up -d --wait opensearch
	@curl -s http://localhost:9200 | head -20

down:  ## Stop all containers
	docker compose --profile debug --profile app down

debug:  ## Start OpenSearch Dashboards on :5601
	docker compose --profile debug up -d --wait

status:  ## Show OpenSearch cluster health
	@curl -s "http://localhost:9200/_cluster/health?pretty"

SCENARIO ?= 5xx_after_deploy

seed:  ## Load a scenario's data into OpenSearch (SCENARIO=oom_memory_leak for the other one)
	uv run python -m generator.seed --scenario scenarios/$(SCENARIO).yaml

investigate:  ## Run the agent on the seeded scenario's alert (needs ANTHROPIC_API_KEY)
	uv run python -m app.agent --alert $$(uv run python -c "import yaml;print(yaml.safe_load(open('scenarios/$(SCENARIO).yaml'))['alert'])")

api:  ## Run the FastAPI server on :8000
	uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

ui:  ## Run the Streamlit UI on :8501 (needs `make api` running)
	uv run python -m streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true

alert:  ## Load a scenario and send its alert to the running API (SCENARIO=...)
	@curl -s -X POST http://localhost:8000/demo/scenarios/$(SCENARIO)/fire; echo

eval:  ## Grade the agent on every scenario against ground truth (3 runs each, uses the API key)
	uv run python -m evals.run --runs 3

demo:  ## Build and run the whole stack in Docker: OpenSearch, seed, API (:8000), UI (:8501)
	docker compose --profile app up -d --build --wait

demo-down:  ## Stop the Docker stack
	docker compose --profile app down

test:  ## Run tests
	uv run pytest -q

lint:  ## Check code style
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-format code
	uv run ruff check --fix .
	uv run ruff format .
