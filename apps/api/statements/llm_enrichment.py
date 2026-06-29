"""Narration enrichment and confidence scoring for extracted transactions."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.observability import get_tracer
from core.pii_masker import mask_for_llm

tracer = get_tracer("bank-statement-scanner")
from db.models import Ledger, Transaction
from statements.llm_tracking import (
    content_hash_for_transaction,
    estimate_cost_usd,
    estimate_tokens,
    get_cache,
    mark_cache_hit,
    record_usage,
    store_cache,
)


MODE_PATTERNS = {
    # UPI: match standalone 'UPI' AND Indian bank ref prefixes UPIAR/UPIAB/UPILR/UPIIB etc.
    "UPI": re.compile(r"(^|[/|\s])upi[a-z]*(\b|[/|\s]|$)|\b(phonepe|gpay|google pay|paytm|bhim)\b", re.I),
    "NEFT": re.compile(r"(^|[/|\s])neft(\b|[/|\s]|$)", re.I),
    "RTGS": re.compile(r"(^|[/|\s])rtgs(\b|[/|\s]|$)", re.I),
    "IMPS": re.compile(r"(^|[/|\s])imps(\b|[/|\s]|$)", re.I),
    "CHEQUE": re.compile(r"\b(chq|cheque|check)\b", re.I),
    "CASH": re.compile(r"\b(cash|atm|withdrawal)\b", re.I),
    "CARD": re.compile(r"\b(pos|debit card|credit card|card)\b", re.I),
}

LEDGER_HINTS = [
    (re.compile(r"\b(swiggy|zomato|restaurant|food)\b", re.I), "Food Expenses"),
    (re.compile(r"\b(amazon|flipkart|myntra)\b", re.I), "Online Purchases"),
    (re.compile(r"\b(salary|payroll|wages)\b", re.I), "Salary"),
    (re.compile(r"\b(rent)\b", re.I), "Rent"),
    (re.compile(r"\b(fuel|petrol|diesel)\b", re.I), "Fuel Expenses"),
    (re.compile(r"\b(electricity|water|broadband|mobile|recharge)\b", re.I), "Utilities"),
    (re.compile(r"\b(atm|cash withdrawal)\b", re.I), "Cash"),
]

NOISE_TOKENS = {
    "upi",
    "neft",
    "rtgs",
    "imps",
    "pos",
    "chq",
    "cheque",
    "ref",
    "txn",
    "payment",
    "transfer",
}


@dataclass
class EnrichmentResult:
    transaction_id: str
    narration_clean: str
    payment_mode: str | None
    counterparty: str | None
    suggested_ledger: str | None
    confidence: Decimal
    source: str
    cache_status: str = "MISS"


def clean_narration(narration: str) -> str:
    cleaned = narration.replace("/", " ")
    cleaned = re.sub(r"\b(ref|txn|utr|rrn)[:\-\s]*[a-z0-9\-]+\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b\d{6,}\b", " ", cleaned)
    cleaned = re.sub(r"[^a-zA-Z0-9&.\-\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else narration.strip()


def detect_payment_mode(narration: str) -> str | None:
    for mode, pattern in MODE_PATTERNS.items():
        if pattern.search(narration):
            return mode
    return None


def detect_counterparty(narration: str, cleaned: str) -> str | None:
    tokens = [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9&.\-]+", cleaned)
        if token.lower() not in NOISE_TOKENS and len(token) > 2
    ]
    if not tokens:
        return None

    joined = " ".join(tokens[:4]).strip()
    return joined.title() if joined else None


def suggest_ledger(narration: str, debit: Decimal | None, credit: Decimal | None) -> str | None:
    for pattern, ledger in LEDGER_HINTS:
        if pattern.search(narration):
            return ledger
    if credit is not None and debit is None:
        return "Receipts"
    if debit is not None and credit is None:
        return "Expenses"
    return None


def score_confidence(
    narration_clean: str | None,
    payment_mode: str | None,
    counterparty: str | None,
    suggested_ledger: str | None,
    transaction: Transaction,
) -> Decimal:
    """
    Score how confident the heuristic enrichment is.

    Criteria (quality-based, not just presence-based):
    - payment_mode detected via explicit keyword  → high boost
    - suggested_ledger is a SPECIFIC match        → high boost
    - suggested_ledger is just generic fallback   → small boost
    - narration_clean meaningfully shorter        → small boost (noise removed)
    - counterparty resolved to a real name        → small boost
    - Very short / single-word narration          → penalty (ambiguous)
    - No payment mode detected                    → penalty
    """
    narration = transaction.narration or ""
    score = Decimal("0.40")  # base

    # ── Payment mode ──────────────────────────────────────────────────────────
    if payment_mode:
        score += Decimal("0.20")   # explicit keyword match is a strong signal
    else:
        score -= Decimal("0.10")   # unknown mode = uncertain

    # ── Ledger specificity ────────────────────────────────────────────────────
    generic_ledgers = {"Expenses", "Receipts"}
    if suggested_ledger and suggested_ledger not in generic_ledgers:
        score += Decimal("0.20")   # matched a real category (Salary, Food, etc.)
    elif suggested_ledger in generic_ledgers:
        score += Decimal("0.05")   # only a catch-all, low signal
    else:
        score -= Decimal("0.05")   # no ledger suggestion at all

    # ── Narration quality ─────────────────────────────────────────────────────
    if narration_clean and len(narration_clean.strip()) > 5:
        # Reward if cleaning actually removed noise (string got shorter)
        ratio = len(narration_clean) / max(len(narration), 1)
        if ratio < 0.85:
            score += Decimal("0.10")   # significant noise removed
        else:
            score += Decimal("0.05")   # minor clean-up

    # ── Counterparty ──────────────────────────────────────────────────────────
    if counterparty and len(counterparty.strip()) > 2:
        score += Decimal("0.05")

    # ── Short / ambiguous narration penalty ───────────────────────────────────
    # Split on spaces AND slashes/pipes so "UPIAR/123/DR/NAME" counts as 4 tokens
    words = len(re.split(r"[\s/|]+", narration.strip()))
    if words <= 2:
        score -= Decimal("0.10")   # e.g. "TFR" or "ATM" alone is very ambiguous

    return max(Decimal("0.10"), min(score, Decimal("0.950"))).quantize(Decimal("0.001"))


def heuristic_enrich(transaction: Transaction) -> EnrichmentResult:
    narration = transaction.narration or ""
    narration_clean = clean_narration(narration)
    payment_mode = detect_payment_mode(narration)
    counterparty = detect_counterparty(narration, narration_clean)
    ledger = suggest_ledger(narration, transaction.debit, transaction.credit)
    confidence = score_confidence(
        narration_clean,
        payment_mode,
        counterparty,
        ledger,
        transaction,
    )
    return EnrichmentResult(
        transaction_id=transaction.id,
        narration_clean=narration_clean,
        payment_mode=payment_mode,
        counterparty=counterparty,
        suggested_ledger=ledger,
        confidence=confidence,
        source="heuristic",
        cache_status="FALLBACK",
    )


def transactions_payload(transactions: list[Transaction]) -> list[dict[str, Any]]:
    """Build the JSON list sent to the LLM — narrations are PII-masked (Task 4)."""
    return [
        {
            "id": tx.id,
            "date": tx.txn_date.isoformat() if tx.txn_date else None,
            # mask_for_llm replaces account numbers, PAN, Aadhaar, phone, card
            # before the text leaves our infrastructure (PRD ss11.4).
            "narration": mask_for_llm(
                tx.narration,
                account_number=getattr(tx, "_stmt_account_number", None),
            ),
            "debit": str(tx.debit) if tx.debit is not None else None,
            "credit": str(tx.credit) if tx.credit is not None else None,
            "balance": str(tx.balance) if tx.balance is not None else None,
        }
        for tx in transactions
    ]


def _chunk(lst: list, size: int) -> list[list]:
    """Split `lst` into consecutive sub-lists of at most `size` items.

    Task 16 — used to split cache-miss transactions into LLM_BATCH_SIZE (50)
    chunks before dispatching concurrent API calls.
    """
    return [lst[i : i + size] for i in range(0, len(lst), size)]


async def claude_enrich_batch(
    transactions: list[Transaction],
    model: str | None = None,
    allowed_ledgers: list[str] | None = None,
) -> list[EnrichmentResult]:
    """Call the Anthropic API to enrich a batch of transactions.

    Args:
        transactions: Batch of Transaction ORM objects to enrich.
        model: Override the model to use. Defaults to settings.ANTHROPIC_MODEL
               (Sonnet 4.5). Pass settings.ANTHROPIC_FALLBACK_MODEL (Haiku)
               when called as part of the Task-15 fallback chain.
        allowed_ledgers: Task 17 — if provided, the tool schema constrains
               `suggested_ledger` to this enum and any name outside the list
               is nulled out after the response is parsed.
    """
    if not settings.ANTHROPIC_API_KEY:
        return []

    # Task 15 — use the caller-supplied model or the primary (Sonnet 4.5).
    effective_model = model or settings.ANTHROPIC_MODEL

    # ── Task 17: constrain suggested_ledger to the client's ledger list ──
    # When allowed_ledgers is provided, inject it into the tool schema enum so
    # the model can ONLY return names from the client's chart of accounts.
    # Null is always permitted — the model can abstain.
    ledger_enum: list[str | None]
    if allowed_ledgers:
        ledger_enum = [*allowed_ledgers, None]
    else:
        ledger_enum = [None]   # no constraint; any string is accepted below

    suggested_ledger_schema: dict[str, Any]
    if allowed_ledgers:
        suggested_ledger_schema = {
            "type": ["string", "null"],
            "enum": ledger_enum,
            "description": "One of the client's existing Tally ledger names, or null.",
        }
    else:
        suggested_ledger_schema = {
            "type": ["string", "null"],
            "description": "Practical accounting ledger category, or null if unsure.",
        }

    tool_schema = {
        "name": "parse_bank_narrations",
        "description": "Return structured enrichment for bank statement transactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string"},
                            "narration_clean": {"type": "string"},
                            "payment_mode": {
                                "type": ["string", "null"],
                                "enum": ["UPI", "NEFT", "RTGS", "IMPS", "CHEQUE", "CASH", "CARD", None],
                            },
                            "counterparty": {"type": ["string", "null"]},
                            "suggested_ledger": suggested_ledger_schema,
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": [
                            "transaction_id",
                            "narration_clean",
                            "payment_mode",
                            "counterparty",
                            "suggested_ledger",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["items"],
        },
    }
    prompt = (
        "Parse these Indian bank transaction narrations. Clean noisy narration, "
        "detect payment mode, counterparty, a practical accounting ledger, and confidence. "
        "Use null when unsure."
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        # ── Build request headers ──────────────────────────────────────────
        headers: dict[str, str] = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Task 14 — ZDR: attach the zero-data-retention beta header so
        # Anthropic does NOT log or retain prompt/response data.
        # Only active after the ZDR agreement has been signed in the
        # Anthropic console (https://console.anthropic.com/settings/privacy).
        if settings.ANTHROPIC_ZDR_ENABLED:
            headers["anthropic-beta"] = "zero-data-retention-2024-02-23"

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json={
                "model": effective_model,
                "max_tokens": 2048,
                "tools": [tool_schema],
                "tool_choice": {"type": "tool", "name": "parse_bank_narrations"},
                "messages": [
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nTransactions:\n{json.dumps(transactions_payload(transactions))}",
                    }
                ],
            },
        )
        response.raise_for_status()

    content = response.json().get("content", [])
    tool_input = next(
        (item.get("input") for item in content if item.get("type") == "tool_use"),
        None,
    )
    if not tool_input:
        return []

    # Tag source so tracking layer knows which model actually ran.
    is_fallback = effective_model != settings.ANTHROPIC_MODEL
    source_tag = "claude-fallback" if is_fallback else "claude"

    allowed_set = set(allowed_ledgers) if allowed_ledgers else None

    by_id = {tx.id: tx for tx in transactions}
    results: list[EnrichmentResult] = []
    for item in tool_input.get("items", []):
        tx = by_id.get(item.get("transaction_id"))
        if not tx:
            continue
        confidence = Decimal(str(item.get("confidence") or 0)).quantize(Decimal("0.001"))

        # Task 17: reject any ledger name the model hallucinated outside the
        # allowed set. Null it out rather than silently accepting it.
        raw_ledger = item.get("suggested_ledger")
        if allowed_set and raw_ledger and raw_ledger not in allowed_set:
            raw_ledger = None

        results.append(
            EnrichmentResult(
                transaction_id=tx.id,
                narration_clean=item.get("narration_clean") or clean_narration(tx.narration or ""),
                payment_mode=item.get("payment_mode"),
                counterparty=item.get("counterparty"),
                suggested_ledger=raw_ledger,
                confidence=max(Decimal("0.000"), min(confidence, Decimal("1.000"))),
                source=source_tag,
                cache_status="MISS",
            )
        )
    return results


async def enrich_transactions(
    transactions: list[Transaction],
    allowed_ledgers: list[str] | None = None,
) -> list[EnrichmentResult]:
    """Enrich transactions using the Sonnet → Haiku → heuristic fallback chain.

    Task 15 fallback order:
      1. Claude Sonnet 4.5 (primary — highest accuracy)
      2. Claude 3.5 Haiku  (fallback — if Sonnet is rate-limited / unavailable)
      3. Heuristic engine  (local — no external API call, always available)

    Task 17:
      allowed_ledgers constrains the LLM's suggested_ledger to the client's
      existing chart of accounts, preventing hallucinated ledger names.
    """
    if not transactions:
        return []

    llm_results: list[EnrichmentResult] = []

    # ── Step 1: Try primary model (Sonnet 4.5) ────────────────────────────
    try:
        llm_results = await claude_enrich_batch(
            transactions, allowed_ledgers=allowed_ledgers
        )
    except (httpx.HTTPError, ValueError, KeyError):
        # ── Step 2: Sonnet failed — retry with Haiku fallback ─────────────
        if settings.ANTHROPIC_FALLBACK_MODEL:
            try:
                llm_results = await claude_enrich_batch(
                    transactions,
                    model=settings.ANTHROPIC_FALLBACK_MODEL,
                    allowed_ledgers=allowed_ledgers,
                )
            except (httpx.HTTPError, ValueError, KeyError):
                llm_results = []
        else:
            llm_results = []

    results_by_id = {result.transaction_id: result for result in llm_results}
    for transaction in transactions:
        results_by_id.setdefault(transaction.id, heuristic_enrich(transaction))

    return [results_by_id[transaction.id] for transaction in transactions]


def enrichment_from_cache(transaction_id: str, payload: dict[str, Any]) -> EnrichmentResult:
    return EnrichmentResult(
        transaction_id=transaction_id,
        narration_clean=payload.get("narration_clean") or "",
        payment_mode=payload.get("payment_mode"),
        counterparty=payload.get("counterparty"),
        suggested_ledger=payload.get("suggested_ledger"),
        confidence=Decimal(str(payload.get("confidence") or "0")).quantize(Decimal("0.001")),
        source=payload.get("source") or "cache",
        cache_status="HIT",
    )


def enrichment_cache_payload(result: EnrichmentResult) -> dict[str, Any]:
    return {
        "narration_clean": result.narration_clean,
        "payment_mode": result.payment_mode,
        "counterparty": result.counterparty,
        "suggested_ledger": result.suggested_ledger,
        "confidence": str(result.confidence),
        "source": result.source,
    }


async def enrich_transactions_with_tracking(
    db: AsyncSession,
    transactions: list[Transaction],
    statement_id: str,
    client_id: str | None = None,
) -> list[EnrichmentResult]:
    if not transactions:
        return []

    # Task 17 — fetch the client's existing ledger names so the LLM is
    # constrained to only suggest names from their chart of accounts.
    allowed_ledgers: list[str] | None = None
    if client_id:
        ledger_rows = await db.execute(
            select(Ledger.name).where(Ledger.client_id == client_id).order_by(Ledger.name)
        )
        names = [row[0] for row in ledger_rows.all()]
        if names:
            allowed_ledgers = names

    with tracer.start_as_current_span("llm_enrichment") as span:
        span.set_attribute("statement_id", statement_id)
        span.set_attribute("transaction_count", len(transactions))
        span.set_attribute("ledger_count", len(allowed_ledgers) if allowed_ledgers else 0)
        cached_results: dict[str, EnrichmentResult] = {}
        cache_misses: list[Transaction] = []
        hashes_by_id: dict[str, str] = {}

        for transaction in transactions:
            content_hash = content_hash_for_transaction(transaction)
            hashes_by_id[transaction.id] = content_hash
            cache = await get_cache(db, content_hash)
            if cache:
                cached_results[transaction.id] = enrichment_from_cache(
                    transaction.id,
                    cache.response_json,
                )
                await mark_cache_hit(db, cache, statement_id, transaction.id)
            else:
                cache_misses.append(transaction)

        # ── Task 16: batch + concurrency-limited enrichment ───────────────────
        # Split cache-misses into chunks of LLM_BATCH_SIZE (50) and run at most
        # LLM_MAX_CONCURRENT_BATCHES (4) chunks in parallel.
        batch_size = settings.LLM_BATCH_SIZE
        max_concurrent = settings.LLM_MAX_CONCURRENT_BATCHES
        batches = _chunk(cache_misses, batch_size)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _enrich_batch(batch: list[Transaction]) -> list[EnrichmentResult]:
            async with semaphore:
                return await enrich_transactions(batch, allowed_ledgers=allowed_ledgers)

        batch_results_nested = await asyncio.gather(
            *[_enrich_batch(batch) for batch in batches]
        )
        # Flatten [[result, ...], ...] -> [result, ...]
        fresh_results: list[EnrichmentResult] = [
            r for batch in batch_results_nested for r in batch
        ]
        # ─────────────────────────────────────────────────────────────────────

        for transaction, result in zip(cache_misses, fresh_results):
            content_hash = hashes_by_id[transaction.id]
            prompt_tokens = estimate_tokens(json.dumps(transactions_payload([transaction])))
            completion_tokens = estimate_tokens(json.dumps(enrichment_cache_payload(result)))
            is_claude = result.source in {"claude", "claude-fallback"}
            cost = (
                estimate_cost_usd(prompt_tokens, completion_tokens)
                if is_claude
                else Decimal("0.000000")
            )
            provider = "anthropic" if is_claude else "local"
            if result.source == "claude-fallback":
                model = settings.ANTHROPIC_FALLBACK_MODEL
            elif result.source == "claude":
                model = settings.ANTHROPIC_MODEL
            else:
                model = "heuristic-v1"
            await store_cache(
                db=db,
                content_hash=content_hash,
                provider=provider,
                model=model,
                response_json=enrichment_cache_payload(result),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
            await record_usage(
                db=db,
                statement_id=statement_id,
                transaction_id=transaction.id,
                provider=provider,
                model=model,
                cache_status=result.cache_status,
                content_hash=content_hash,
                prompt_tokens=prompt_tokens if is_claude else 0,
                completion_tokens=completion_tokens if is_claude else 0,
                cost_usd=cost,
            )
            cached_results[transaction.id] = result

        return [cached_results[transaction.id] for transaction in transactions]


def apply_enrichment(transaction: Transaction, result: EnrichmentResult) -> None:
    transaction.narration_clean = result.narration_clean
    transaction.payment_mode = result.payment_mode
    transaction.counterparty = result.counterparty
    transaction.suggested_ledger = result.suggested_ledger
    transaction.confidence = result.confidence


def serialize_enrichment(result: EnrichmentResult) -> dict[str, Any]:
    return {
        "transaction_id": result.transaction_id,
        "narration_clean": result.narration_clean,
        "payment_mode": result.payment_mode,
        "counterparty": result.counterparty,
        "suggested_ledger": result.suggested_ledger,
        "confidence": str(result.confidence),
        "source": result.source,
        "cache_status": result.cache_status,
    }
