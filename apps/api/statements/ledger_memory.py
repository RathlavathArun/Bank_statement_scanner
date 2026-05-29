"""Ledger mapping memory with optional Qdrant-backed similarity search."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import LedgerMapping, Transaction


TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class LedgerSuggestion:
    ledger_name: str
    pattern: str
    score: float
    source: str
    hit_count: int = 0


def normalize_narration(value: str | None) -> str:
    """Create a stable pattern key from noisy bank narration text."""
    tokens = TOKEN_RE.findall((value or "").lower())
    return " ".join(tokens)


def embedding_for_text(text: str, size: int | None = None) -> list[float]:
    """Small deterministic embedding for local/offline vector memory.

    This is intentionally dependency-free. It gives Qdrant a useful similarity
    signal now, and can later be swapped for OpenAI/Claude embedding output.
    """
    vector_size = size or settings.QDRANT_VECTOR_SIZE
    vector = [0.0] * vector_size
    tokens = TOKEN_RE.findall(text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % vector_size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


class QdrantLedgerMemory:
    def __init__(self) -> None:
        self.url = settings.QDRANT_URL.rstrip("/")
        self.collection = settings.QDRANT_COLLECTION
        self.vector_size = settings.QDRANT_VECTOR_SIZE

    @property
    def enabled(self) -> bool:
        return settings.QDRANT_ENABLED

    async def ensure_collection(self) -> None:
        if not self.enabled:
            return

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{self.url}/collections/{self.collection}")
            if response.status_code == 200:
                return
            response.raise_for_status() if response.status_code != 404 else None
            await client.put(
                f"{self.url}/collections/{self.collection}",
                json={
                    "vectors": {
                        "size": self.vector_size,
                        "distance": "Cosine",
                    }
                },
            )

    async def upsert(self, mapping: LedgerMapping) -> None:
        if not self.enabled:
            return

        await self.ensure_collection()
        payload = {
            "client_id": mapping.client_id,
            "ledger_name": mapping.ledger_name,
            "pattern": mapping.pattern,
            "hit_count": mapping.hit_count,
            "mapping_id": mapping.id,
        }
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.put(
                f"{self.url}/collections/{self.collection}/points",
                json={
                    "points": [
                        {
                            "id": mapping.id,
                            "vector": embedding_for_text(mapping.pattern, self.vector_size),
                            "payload": payload,
                        }
                    ]
                },
            )

    async def search(self, client_id: str, narration: str, limit: int) -> list[LedgerSuggestion]:
        if not self.enabled:
            return []

        await self.ensure_collection()
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json={
                    "vector": embedding_for_text(narration, self.vector_size),
                    "limit": limit,
                    "with_payload": True,
                    "filter": {
                        "must": [
                            {"key": "client_id", "match": {"value": client_id}},
                        ],
                    },
                },
            )
            response.raise_for_status()

        matches = response.json().get("result", [])
        return [
            LedgerSuggestion(
                ledger_name=match.get("payload", {}).get("ledger_name", ""),
                pattern=match.get("payload", {}).get("pattern", ""),
                score=float(match.get("score", 0)),
                source="qdrant",
                hit_count=int(match.get("payload", {}).get("hit_count") or 0),
            )
            for match in matches
            if match.get("payload", {}).get("ledger_name")
        ]


qdrant_memory = QdrantLedgerMemory()


async def remember_ledger_mapping(
    db: AsyncSession,
    transaction: Transaction,
    ledger_name: str,
    client_id: str,
    created_by: str | None = None,
) -> LedgerMapping | None:
    pattern = normalize_narration(transaction.narration_clean or transaction.narration)
    if not pattern or not ledger_name.strip():
        return None

    result = await db.execute(
        select(LedgerMapping).where(
            LedgerMapping.client_id == client_id,
            LedgerMapping.pattern == pattern,
        )
    )
    mapping = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if mapping:
        mapping.ledger_name = ledger_name.strip()
        mapping.hit_count += 1
        mapping.last_used_at = now
    else:
        mapping = LedgerMapping(
            client_id=client_id,
            pattern=pattern,
            ledger_name=ledger_name.strip(),
            created_by=created_by,
            last_used_at=now,
        )
        db.add(mapping)

    await db.flush()
    try:
        await qdrant_memory.upsert(mapping)
    except (httpx.HTTPError, OSError):
        pass
    return mapping


async def suggest_ledgers(
    db: AsyncSession,
    transaction: Transaction,
    client_id: str,
    limit: int = 5,
) -> list[LedgerSuggestion]:
    pattern = normalize_narration(transaction.narration_clean or transaction.narration)
    if not pattern:
        return []

    result = await db.execute(
        select(LedgerMapping)
        .where(LedgerMapping.client_id == client_id)
        .order_by(LedgerMapping.hit_count.desc(), LedgerMapping.last_used_at.desc())
    )

    suggestions: list[LedgerSuggestion] = []
    seen_ledgers: set[str] = set()
    query_tokens = set(pattern.split())
    for mapping in result.scalars().all():
        mapping_tokens = set(mapping.pattern.split())
        overlap = len(query_tokens & mapping_tokens)
        score = 1.0 if mapping.pattern == pattern else overlap / max(len(query_tokens | mapping_tokens), 1)
        if score <= 0:
            continue
        if mapping.ledger_name in seen_ledgers:
            continue
        seen_ledgers.add(mapping.ledger_name)
        suggestions.append(
            LedgerSuggestion(
                ledger_name=mapping.ledger_name,
                pattern=mapping.pattern,
                score=score,
                source="db",
                hit_count=mapping.hit_count,
            )
        )

    try:
        qdrant_suggestions = await qdrant_memory.search(client_id, pattern, limit)
    except (httpx.HTTPError, OSError):
        qdrant_suggestions = []

    for suggestion in qdrant_suggestions:
        if suggestion.ledger_name in seen_ledgers:
            continue
        seen_ledgers.add(suggestion.ledger_name)
        suggestions.append(suggestion)

    suggestions.sort(key=lambda item: (item.score, item.hit_count), reverse=True)
    return suggestions[:limit]


def serialize_suggestion(suggestion: LedgerSuggestion) -> dict[str, Any]:
    return {
        "ledger_name": suggestion.ledger_name,
        "pattern": suggestion.pattern,
        "score": round(suggestion.score, 4),
        "source": suggestion.source,
        "hit_count": suggestion.hit_count,
    }
