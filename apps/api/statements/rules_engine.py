"""Task 20 — Custom narration rules engine (FR-4.6).

CA firms define deterministic rules:
    "if narration <match_type> <pattern> → assign ledger <ledger_name>"

Rules are evaluated in priority order (lowest number = highest priority)
BEFORE recurring-detection and LLM enrichment, so CA-defined rules always
win over automated suggestions. Matched transactions are never sent to the
LLM, saving API cost and eliminating hallucination risk for known
counterparties.

Supported match_type values:
    contains    — case-insensitive substring match  (default)
    startswith  — case-insensitive prefix match
    endswith    — case-insensitive suffix match
    exact       — case-insensitive full-string equality
    regex       — compiled Python regex (case-insensitive)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import NarrationRule, Transaction
from statements.llm_enrichment import EnrichmentResult, clean_narration, detect_counterparty, detect_payment_mode

logger = logging.getLogger(__name__)

# Cache compiled regexes in-process to avoid recompilation on every call.
_regex_cache: dict[str, re.Pattern[str]] = {}


def _compile_regex(pattern: str) -> re.Pattern[str]:
    if pattern not in _regex_cache:
        _regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
    return _regex_cache[pattern]


def _rule_matches(rule: NarrationRule, narration: str) -> bool:
    """Return True if `narration` satisfies `rule`."""
    narration_lower = narration.lower()
    match_type = (rule.match_type or "contains").lower()
    pattern = rule.pattern or ""

    try:
        if match_type == "contains":
            return pattern.lower() in narration_lower
        if match_type == "startswith":
            return narration_lower.startswith(pattern.lower())
        if match_type == "endswith":
            return narration_lower.endswith(pattern.lower())
        if match_type == "exact":
            return narration_lower == pattern.lower()
        if match_type == "regex":
            return bool(_compile_regex(pattern).search(narration))
    except re.error as exc:
        logger.warning("Invalid regex in NarrationRule %s: %s", rule.id, exc)
    return False


@dataclass
class RuleMatch:
    rule_id: str
    ledger_name: str
    pattern: str
    match_type: str
    priority: int


async def apply_rules(
    db: AsyncSession,
    transactions: list[Transaction],
    client_id: str,
) -> dict[str, EnrichmentResult]:
    """Task 20 — Apply client-defined narration rules to `transactions`.

    Loads all active rules for `client_id` ordered by priority and evaluates
    each transaction's narration. The first matching rule wins (lowest
    priority number = highest precedence).

    Returns a dict {transaction_id: EnrichmentResult} for every transaction
    that was matched by at least one rule. The caller should exclude these
    from subsequent LLM / recurring detection steps.
    """
    if not transactions or not client_id:
        return {}

    # Load active rules for this client, ordered by priority then created_at
    rows = await db.execute(
        select(NarrationRule)
        .where(
            NarrationRule.client_id == client_id,
            NarrationRule.is_active.is_(True),
        )
        .order_by(NarrationRule.priority, NarrationRule.created_at)
    )
    rules: list[NarrationRule] = list(rows.scalars().all())

    if not rules:
        return {}

    matched: dict[str, EnrichmentResult] = {}
    for tx in transactions:
        narration = tx.narration or ""
        for rule in rules:
            if _rule_matches(rule, narration):
                narration_clean = clean_narration(narration)
                payment_mode = detect_payment_mode(narration)
                counterparty = detect_counterparty(narration, narration_clean)
                matched[tx.id] = EnrichmentResult(
                    transaction_id=tx.id,
                    narration_clean=narration_clean,
                    payment_mode=payment_mode,
                    counterparty=counterparty,
                    suggested_ledger=rule.ledger_name,
                    confidence=Decimal("1.000"),  # deterministic — always confident
                    source="rule",
                    cache_status="MISS",
                )
                break  # first matching rule wins

    logger.debug(
        "rules_engine: client=%s rules=%d transactions=%d matched=%d",
        client_id,
        len(rules),
        len(transactions),
        len(matched),
    )
    return matched


# ─── Schema helpers ──────────────────────────────────────────────────────────

def serialize_rule(rule: NarrationRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "client_id": rule.client_id,
        "match_type": rule.match_type,
        "pattern": rule.pattern,
        "ledger_name": rule.ledger_name,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }
