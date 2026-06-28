# ADR-001: Migrate from SQLite to PostgreSQL 16

**Date:** 2026-06-28  
**Status:** Accepted  
**Deciders:** Engineering Team

## Context

The initial prototype used `sqlite+aiosqlite` as the database backend for
developer convenience. SQLite has well-known limitations that block production
use of this system:

1. No Row-Level Security (RLS) — required by PRD §11.1 for multi-tenant data
   isolation
2. No `SKIP LOCKED` for queue-style patterns
3. No `NUMERIC` precision enforcement (stores as REAL, silently losing centavo)
4. Cannot enforce `GENERATED ALWAYS AS` columns or table partitioning
5. Concurrent writes are serialised at the file level — unsuitable for multiple
   workers

## Decision

Replace all `sqlite+aiosqlite` references with `postgresql+asyncpg`.  
Engine version pinned to **PostgreSQL 16** (matching `engine_version = "16.14"`
in `infra/terraform/databases.tf`) for consistency between local dev and AWS RDS.

Local development uses the `postgres:16` Docker image via `docker-compose.yml`.

## Consequences

- **Positive:** Unlocks Row-Level Security (ADR-002), proper NUMERIC types,
  concurrent worker writes, and native JSON/JSONB operators.
- **Positive:** `asyncpg` is ~3-5× faster than `aiosqlite` for the same queries.
- **Negative:** Developers must run Docker (or install Postgres locally) instead
  of zero-setup SQLite. Mitigated by the pre-configured `docker-compose.yml`.
- **Migration path:** No data migration needed — project is pre-production.
  `Base.metadata.create_all()` handles schema creation on first boot.
