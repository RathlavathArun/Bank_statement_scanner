# ADR-002: Row-Level Security for Multi-Tenant Data Isolation

**Date:** 2026-06-28  
**Status:** Accepted  
**Deciders:** Engineering Team

## Context

The system serves multiple accounting firms (tenants) from a single PostgreSQL
database. Without additional controls, a bug in any query (e.g., a missing
`WHERE firm_id = ?`) would expose one firm's financial data to another — a
critical PRD §11.4 violation.

## Decision

Implement PostgreSQL **Row-Level Security (RLS)** as a defence-in-depth layer
below the application:

1. Every request handler calls `SET LOCAL app.current_firm_id = '<id>'` at the
   start of the DB session (via `db/rls.py`).
2. RLS policies on `clients`, `statements`, `transactions`, `export_jobs` filter
   rows to the `current_firm_id` session variable automatically.
3. The application superuser (used for migrations only) bypasses RLS via
   `BYPASSRLS`. The `bse_app` role (used at runtime) does not.

## Consequences

- **Positive:** Even if application code forgets a `WHERE` clause, the database
  engine enforces isolation — zero cross-tenant data leakage.
- **Positive:** Automated tests (`tests/test_rls.py`) validate isolation at the
  DB level independently of application logic.
- **Negative:** Requires a PostgreSQL session variable to be set on every
  request — adds one round-trip. Mitigated by connection pooling (PgBouncer or
  asyncpg pool).
- **Negative:** Admin/migration queries must explicitly bypass RLS or use the
  superuser connection string.
