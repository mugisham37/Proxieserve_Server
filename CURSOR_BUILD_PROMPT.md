# ProxiServe Backend — Architecture and Build Rules

## Five-Layer Module Pattern

Each domain module under `app/modules/<name>/` follows:

1. **models.py** — SQLAlchemy ORM models
2. **schemas.py** — Pydantic request/response DTOs
3. **repository.py** — Database queries only (no business logic)
4. **service.py** — Business logic, transactions, side effects
5. **router.py** — FastAPI routes, dependency injection, envelope responses

Optional: **jobs.py** for ARQ background tasks.

## ApiResponse Envelope

All routes return `ApiResponse[T]` via `success_response(message=..., data=...)` from `app/core/api.py`:

```json
{ "success": true, "errorType": null, "message": "...", "data": { ... } }
```

Errors raise `AppError` subclasses from `app/core/exceptions.py`; middleware maps them to the same envelope.

## Dependencies

- `get_db_session` — async SQLAlchemy session (commit in service layer)
- `get_job_queue` — ARQ `JobQueueManager`
- `REQUIRE_CLIENT`, `REQUIRE_AGENT`, `REQUIRE_ADMIN` — role guards
- `rate_limit(name, max_requests, window_seconds)` — Redis-backed

## ARQ Jobs

Register in `app/worker.py` `WorkerSettings.functions`. Enqueue via `job_queue.enqueue("job_name", **kwargs)`.

Jobs open a fresh session with `db_manager.session_factory()`.

## Async SQLAlchemy

Use `async with db_manager.session_factory() as session` in jobs. In request handlers, use injected session; call `await session.commit()` in service after mutations.

## Non-Negotiable Rules

- No N+1 queries — batch fetches and JOINs
- No stubs or TODO in production code paths
- Audit entries in same transaction as the operation they record
- Inject payment gateway into service constructor
- camelCase on new frontend-facing response fields where types in `web/src/lib/types/` use camelCase
