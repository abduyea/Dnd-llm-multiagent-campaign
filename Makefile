.PHONY: install run-backend test lint check migrate docker-up docker-down

install:
	uv sync --extra dev

run-backend:
	uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -v --tb=short

lint:
	uv run ruff check backend/ frontend/ tests/

check: lint test

docker-up:
	docker compose up --build

docker-down:
	docker compose down

migrate:
	uv run alembic upgrade head

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
