.PHONY: dev server worker test lint fmt migrate

dev:
	@echo "Starting API server + ARQ worker..."
	@trap 'kill 0' INT; \
	  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload & \
	  .venv/bin/python -m app.worker & \
	  wait

server:
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	.venv/bin/python -m app.worker

migrate:
	.venv/bin/alembic upgrade head

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app

fmt:
	.venv/bin/ruff format app
