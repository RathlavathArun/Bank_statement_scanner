"""
Row-Level Security (RLS) helpers for PostgreSQL.

Two entry points:
  1. apply_rls_policies(conn)  — called once at startup to create/update
     all RLS policies on the tenant-scoped tables.  Idempotent.

  2. set_rls_context(db, firm_id)  — called per-request (in get_current_user)
     to bind the current firm_id to the database session local variable
     `app.current_firm_id`, which the RLS policies read via current_setting().

PRD reference: §11.1 (data isolation), ADR-002.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncConnection

logger = logging.getLogger(__name__)

# Tables that carry client/firm data and must be row-locked
_TENANT_TABLES = [
    ("clients",      "firm_id"),
    ("statements",   "client_id"),   # indirect — joined through clients
    ("transactions", "statement_id"), # indirect — two hops
    ("export_jobs",  "statement_id"), # indirect
]

# Direct-policy tables (firm_id column exists on the table itself)
_DIRECT_POLICY_TABLES = [
    ("clients", "firm_id"),
]

# Indirect-policy tables that join to `clients`
_INDIRECT_POLICY_TABLES = [
    ("statements",
     "client_id IN (SELECT id FROM clients WHERE firm_id = current_setting('app.current_firm_id', true))"),
    ("transactions",
     "statement_id IN (SELECT id FROM statements WHERE client_id IN "
     "(SELECT id FROM clients WHERE firm_id = current_setting('app.current_firm_id', true)))"),
    ("export_jobs",
     "statement_id IN (SELECT id FROM statements WHERE client_id IN "
     "(SELECT id FROM clients WHERE firm_id = current_setting('app.current_firm_id', true)))"),
]


async def apply_rls_policies(conn: AsyncConnection) -> None:
    """
    Create (or replace) RLS policies on all tenant-scoped tables.
    Safe to call on every startup — uses CREATE POLICY IF NOT EXISTS pattern
    (DROP + CREATE to handle definition changes).
    """
    # Enable RLS on each table and drop+recreate isolation policy
    for table, condition in _direct_policies() + _indirect_policies():
        policy_name = f"rls_{table}_firm_isolation"
        await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        # Drop old version if it exists (allows redefinition on upgrade)
        await conn.execute(text(
            f"DROP POLICY IF EXISTS {policy_name} ON {table}"
        ))
        await conn.execute(text(
            f"""
            CREATE POLICY {policy_name} ON {table}
            USING (
                current_setting('app.current_firm_id', true) = ''
                OR {condition}
            )
            """
        ))
        logger.info("RLS policy applied: %s on %s", policy_name, table)


def _direct_policies() -> list[tuple[str, str]]:
    return [
        ("clients", "firm_id::text = current_setting('app.current_firm_id', true)"),
    ]


def _indirect_policies() -> list[tuple[str, str]]:
    return _INDIRECT_POLICY_TABLES


async def set_rls_context(db: AsyncSession, firm_id: Optional[str]) -> None:
    """
    Set the PostgreSQL session-local variable used by RLS policies.
    Call this immediately after authenticating the user in every request.

    Uses SET LOCAL so the variable is cleared when the transaction ends —
    no risk of context leaking across pooled connections.
    """
    if firm_id:
        await db.execute(
            text("SELECT set_config('app.current_firm_id', :fid, true)"),
            {"fid": str(firm_id)},
        )
    else:
        # No firm — clear context so policies allow nothing
        await db.execute(
            text("SELECT set_config('app.current_firm_id', '', true)")
        )
