# ADR 0001: Server Technology Stack

## Status
Accepted

## Context
`server/` is being built as a production-grade backend for the finalized `web/` authentication flows. The system must support strong validation, asynchronous I/O, durable relational data, ephemeral auth state, horizontal scale, and clean module boundaries.

## Decision
Adopt the following stack:

- FastAPI
- Python 3.12+
- Pydantic v2 and pydantic-settings
- SQLAlchemy 2.0 async
- Alembic
- PostgreSQL 16+
- asyncpg
- Redis 7+
- Argon2id
- PyJWT
- ARQ
- structlog
- OpenTelemetry
- Prometheus metrics
- pytest + pytest-asyncio + httpx + testcontainers
- Docker + docker-compose

## Prisma Override
The original brief referenced Prisma-like ergonomics, but the Python Prisma client is no longer a safe fit for a security-critical system. SQLAlchemy 2.0 async is the chosen replacement because it is mature, maintained, type-friendly, and operationally credible for long-lived production workloads.

## Rationale
- FastAPI gives an async-native HTTP layer with first-class Pydantic integration.
- Pydantic v2 mirrors the frontend's Zod contracts cleanly and keeps validation at the boundary.
- SQLAlchemy 2.0 async plus Alembic provides a stable, reviewable, migration-friendly persistence layer.
- PostgreSQL is the durable source of truth for identity and audit data.
- Redis is the right home for OTPs, lockouts, cooldowns, pending auth state, and token revocation metadata.
- Argon2id is the modern password hashing baseline for this auth domain.
- ARQ keeps delivery work off the request path without introducing unnecessary operational weight.
- structlog, Prometheus, and OpenTelemetry are included from day one to keep the system observable under load.

## Consequences
- The codebase will be structured around explicit DTOs, repository/service boundaries, and async data access.
- Ephemeral auth state will not be stored in process memory.
- Future modules can reuse the same core runtime patterns without revisiting the platform baseline.
