"""One-time script to backfill existing ledger_mappings into Qdrant.

Usage:
    python -m statements.backfill_qdrant
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import select

from core.config import settings
from db.database import async_session, engine
from db.models import LedgerMapping
from statements.ledger_memory import embedding_for_text, qdrant_memory

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def _point_for_mapping(mapping: LedgerMapping) -> dict[str, Any]:
    return {
        "id": mapping.id,
        "vector": embedding_for_text(mapping.pattern, settings.QDRANT_VECTOR_SIZE),
        "payload": {
            "client_id": mapping.client_id,
            "ledger_name": mapping.ledger_name,
            "pattern": mapping.pattern,
            "hit_count": mapping.hit_count,
            "mapping_id": mapping.id,
        },
    }


async def backfill_qdrant() -> int:
    """Backfill all PostgreSQL ledger mappings into the configured Qdrant collection."""
    if not qdrant_memory.enabled:
        logger.warning("QDRANT_ENABLED=false; skipping backfill")
        return 0

    await qdrant_memory.ensure_collection()

    async with async_session() as db:
        rows = await db.execute(select(LedgerMapping).order_by(LedgerMapping.client_id, LedgerMapping.id))
        mappings = rows.scalars().all()

    total = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for offset in range(0, len(mappings), BATCH_SIZE):
            batch = mappings[offset : offset + BATCH_SIZE]
            if not batch:
                continue

            response = await client.put(
                f"{qdrant_memory.url}/collections/{qdrant_memory.collection}/points",
                headers=qdrant_memory.headers,
                json={"points": [_point_for_mapping(mapping) for mapping in batch]},
            )
            response.raise_for_status()
            total += len(batch)
            logger.info("qdrant_backfill: upserted=%d total=%d", len(batch), total)

    return total


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        total = await backfill_qdrant()
        logger.info("qdrant_backfill_complete: total=%d", total)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
