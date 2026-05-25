# ProxiServe Server

Production-grade FastAPI backend for ProxiServe. The initial scope is the authentication module and the shared runtime it depends on.

## Stack
- FastAPI
- Python 3.12+
- Pydantic v2
- SQLAlchemy 2.0 async
- Alembic
- PostgreSQL
- Redis
- ARQ

## Structure
- `app/core/` shared runtime and platform concerns
- `app/modules/auth/` authentication domain
- `app/modules/applications/` minimal stub seam used by auth
- `docs/` contracts and architecture decisions
- `tests/` unit and integration coverage

## Local development
1. Copy `.env.example` to `.env`
2. Start local services with Docker Compose
3. Install dependencies with your preferred Python environment manager
4. Run migrations
5. Start the API

## Common commands
- `uvicorn app.main:app --reload`
- `alembic upgrade head`
- `pytest`
- `ruff check .`
- `ruff format .`
- `mypy app tests`
- `lint-imports`

## Notes
- `web/` is intentionally untouched by this backend.
- The backend returns JSON session payloads for current frontend compatibility while also establishing secure cookie-based auth for server-side validation.
