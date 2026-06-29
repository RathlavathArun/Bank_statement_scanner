"""Task 20 — CRUD API for client narration rules (FR-4.6).

Endpoints:
    POST   /v1/rules                   — create a rule
    GET    /v1/rules                   — list rules for the authenticated client
    GET    /v1/rules/{rule_id}         — get a single rule
    PUT    /v1/rules/{rule_id}         — update a rule
    DELETE /v1/rules/{rule_id}         — delete a rule
    POST   /v1/rules/test              — test a rule pattern against a narration
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Client, FirmMember, NarrationRule, User
from statements.rules_engine import _rule_matches, serialize_rule

rules_router = APIRouter(prefix="/v1/rules", tags=["rules"])

# ─── Allowed match types ─────────────────────────────────────────────────────
VALID_MATCH_TYPES = {"contains", "startswith", "endswith", "exact", "regex"}


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    match_type: str = Field(default="contains", description="contains | startswith | endswith | exact | regex")
    pattern: str = Field(..., min_length=1, description="Text or regex to match against raw narration")
    ledger_name: str = Field(..., min_length=1, description="Ledger name to assign on match")
    priority: int = Field(default=100, ge=1, le=9999, description="Lower = higher priority")
    is_active: bool = Field(default=True)


class RuleUpdate(BaseModel):
    match_type: str | None = None
    pattern: str | None = None
    ledger_name: str | None = None
    priority: int | None = Field(default=None, ge=1, le=9999)
    is_active: bool | None = None


class RuleTestRequest(BaseModel):
    match_type: str = Field(default="contains")
    pattern: str = Field(..., min_length=1)
    narration: str = Field(..., description="Sample narration to test the rule against")


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_client_id(db: AsyncSession, user: User) -> str:
    """Resolve client_id from the authenticated user's firm."""
    result = await db.execute(
        select(FirmMember.firm_id).where(FirmMember.user_id == user.id)
    )
    firm_id = result.scalar_one_or_none()
    if not firm_id:
        raise HTTPException(status_code=404, detail="No firm found for user")

    client_result = await db.execute(
        select(Client.id).where(Client.firm_id == firm_id)
    )
    client_id = client_result.scalar_one_or_none()
    if not client_id:
        raise HTTPException(status_code=404, detail="No client found for firm")
    return client_id


async def _get_rule(
    db: AsyncSession, rule_id: str, client_id: str
) -> NarrationRule:
    """Load rule or raise 404; enforce client ownership."""
    rule = await db.get(NarrationRule, rule_id)
    if not rule or rule.client_id != client_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


# ─── Endpoints ───────────────────────────────────────────────────────────────

@rules_router.post("", status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new narration rule for the authenticated user's client."""
    if body.match_type not in VALID_MATCH_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}",
        )
    client_id = await _get_client_id(db, current_user)

    rule = NarrationRule(
        client_id=client_id,
        match_type=body.match_type,
        pattern=body.pattern,
        ledger_name=body.ledger_name,
        priority=body.priority,
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return {"success": True, "data": serialize_rule(rule)}


@rules_router.get("")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all rules for the authenticated user's client, ordered by priority."""
    client_id = await _get_client_id(db, current_user)

    rows = await db.execute(
        select(NarrationRule)
        .where(NarrationRule.client_id == client_id)
        .order_by(NarrationRule.priority, NarrationRule.created_at)
    )
    rules = rows.scalars().all()
    return {
        "success": True,
        "data": {
            "rules": [serialize_rule(r) for r in rules],
            "total": len(rules),
        },
    }


@rules_router.get("/{rule_id}")
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single rule by ID."""
    client_id = await _get_client_id(db, current_user)
    rule = await _get_rule(db, rule_id, client_id)
    return {"success": True, "data": serialize_rule(rule)}


@rules_router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update an existing rule (partial update — only provided fields change)."""
    client_id = await _get_client_id(db, current_user)
    rule = await _get_rule(db, rule_id, client_id)

    updates = body.model_dump(exclude_unset=True)
    if "match_type" in updates and updates["match_type"] not in VALID_MATCH_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}",
        )
    for field, value in updates.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)
    return {"success": True, "data": serialize_rule(rule)}


@rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Permanently delete a rule."""
    client_id = await _get_client_id(db, current_user)
    rule = await _get_rule(db, rule_id, client_id)
    await db.delete(rule)


@rules_router.post("/test")
async def test_rule(
    body: RuleTestRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Dry-run: test whether a pattern matches a narration without saving.

    Useful for the UI to give instant feedback before the CA creates the rule.
    """
    if body.match_type not in VALID_MATCH_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}",
        )
    # Build a temporary unsaved rule object for evaluation
    dummy_rule = NarrationRule(
        client_id="__test__",
        match_type=body.match_type,
        pattern=body.pattern,
        ledger_name="",
        priority=1,
    )
    matches = _rule_matches(dummy_rule, body.narration)
    return {
        "success": True,
        "data": {
            "matches": matches,
            "match_type": body.match_type,
            "pattern": body.pattern,
            "narration": body.narration,
        },
    }
