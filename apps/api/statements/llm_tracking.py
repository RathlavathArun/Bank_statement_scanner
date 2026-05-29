"""Cost tracking and cache helpers for LLM enrichment."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import LLMCache, LLMUsage, Transaction


@dataclass
class UsageTotals:
    calls: int
    cache_hits: int
    cache_misses: int
    fallback_calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


def content_hash_for_transaction(transaction: Transaction) -> str:
    payload = {
        "narration": transaction.narration,
        "debit": str(transaction.debit) if transaction.debit is not None else None,
        "credit": str(transaction.credit) if transaction.credit is not None else None,
        "balance": str(transaction.balance) if transaction.balance is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> Decimal:
    input_cost = Decimal(prompt_tokens) * Decimal(str(settings.ANTHROPIC_INPUT_USD_PER_1M)) / Decimal("1000000")
    output_cost = Decimal(completion_tokens) * Decimal(str(settings.ANTHROPIC_OUTPUT_USD_PER_1M)) / Decimal("1000000")
    return (input_cost + output_cost).quantize(Decimal("0.000001"))


async def get_cache(db: AsyncSession, content_hash: str) -> LLMCache | None:
    result = await db.execute(select(LLMCache).where(LLMCache.content_hash == content_hash))
    return result.scalar_one_or_none()


async def mark_cache_hit(
    db: AsyncSession,
    cache: LLMCache,
    statement_id: str | None,
    transaction_id: str | None,
) -> None:
    cache.hit_count += 1
    cache.last_used_at = datetime.now(timezone.utc)
    db.add(
        LLMUsage(
            statement_id=statement_id,
            transaction_id=transaction_id,
            provider=cache.provider,
            model=cache.model,
            operation="transaction_enrichment",
            cache_status="HIT",
            content_hash=cache.content_hash,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
        )
    )


async def store_cache(
    db: AsyncSession,
    content_hash: str,
    provider: str,
    model: str,
    response_json: dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    existing = await get_cache(db, content_hash)
    if existing:
        existing.response_json = response_json
        existing.prompt_tokens = prompt_tokens
        existing.completion_tokens = completion_tokens
        existing.cost_usd = cost_usd
        existing.last_used_at = datetime.now(timezone.utc)
        return

    db.add(
        LLMCache(
            content_hash=content_hash,
            provider=provider,
            model=model,
            response_json=response_json,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    )


async def record_usage(
    db: AsyncSession,
    statement_id: str | None,
    transaction_id: str | None,
    provider: str,
    model: str,
    cache_status: str,
    content_hash: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    db.add(
        LLMUsage(
            statement_id=statement_id,
            transaction_id=transaction_id,
            provider=provider,
            model=model,
            operation="transaction_enrichment",
            cache_status=cache_status,
            content_hash=content_hash,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    )


async def summarize_usage(db: AsyncSession, statement_id: str) -> UsageTotals:
    result = await db.execute(
        select(
            func.count(LLMUsage.id),
            func.sum(LLMUsage.prompt_tokens),
            func.sum(LLMUsage.completion_tokens),
            func.sum(LLMUsage.cost_usd),
        ).where(LLMUsage.statement_id == statement_id)
    )
    calls, prompt_tokens, completion_tokens, cost_usd = result.one()

    hit_result = await db.execute(
        select(func.count(LLMUsage.id)).where(
            LLMUsage.statement_id == statement_id,
            LLMUsage.cache_status == "HIT",
        )
    )
    miss_result = await db.execute(
        select(func.count(LLMUsage.id)).where(
            LLMUsage.statement_id == statement_id,
            LLMUsage.cache_status == "MISS",
        )
    )
    fallback_result = await db.execute(
        select(func.count(LLMUsage.id)).where(
            LLMUsage.statement_id == statement_id,
            LLMUsage.cache_status == "FALLBACK",
        )
    )

    return UsageTotals(
        calls=int(calls or 0),
        cache_hits=int(hit_result.scalar_one() or 0),
        cache_misses=int(miss_result.scalar_one() or 0),
        fallback_calls=int(fallback_result.scalar_one() or 0),
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        cost_usd=Decimal(str(cost_usd or 0)).quantize(Decimal("0.000001")),
    )


def serialize_usage(totals: UsageTotals) -> dict[str, Any]:
    return {
        "calls": totals.calls,
        "cache_hits": totals.cache_hits,
        "cache_misses": totals.cache_misses,
        "fallback_calls": totals.fallback_calls,
        "prompt_tokens": totals.prompt_tokens,
        "completion_tokens": totals.completion_tokens,
        "cost_usd": str(totals.cost_usd),
    }
