.PHONY: dev server worker test lint fmt migrate seed

dev:
	@echo "Starting API server + ARQ worker..."
	@trap 'kill 0' INT TERM; \
	  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 \
	    --reload --reload-dir app \
	    --reload-exclude '*.pyc' --reload-exclude '__pycache__' & \
	  (while true; do \
	    .venv/bin/python -m app.worker; \
	    echo "ARQ worker exited — restarting in 3s..."; \
	    sleep 3; \
	  done) & \
	  wait

server:
	.venv/bin/python scripts/run_server.py

worker:
	.venv/bin/python -m app.worker

migrate:
	.venv/bin/alembic upgrade head

seed:
	.venv/bin/python scripts/seed.py

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app

fmt:
	.venv/bin/ruff format app
