"""
Shared Pydantic schemas — mirrored from apps/api/statements/schemas.py so that
workers and external packages can import them without depending on the full API.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class TransactionSchema(BaseModel):
    """Canonical transaction representation shared across all services."""

    id: str
    statement_id: str
    row_number: int
    txn_date: date
    value_date: Optional[date] = None
    narration: str
    narration_clean: Optional[str] = None
    reference_no: Optional[str] = None
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    payment_mode: Optional[str] = None
    counterparty: Optional[str] = None
    suggested_ledger: Optional[str] = None
    confirmed_ledger: Optional[str] = None
    confidence: Optional[Decimal] = None

    class Config:
        from_attributes = True


class StatementSchema(BaseModel):
    """Canonical statement representation shared across all services."""

    id: str
    client_id: str
    file_url: str
    file_type: str
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    status: str
    created_at: datetime
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")

    class Config:
        from_attributes = True
        populate_by_name = True


class LLMCategorizationRequest(BaseModel):
    """Message sent from API → LLM worker queue."""

    statement_id: str
    firm_id: str
    transaction_ids: list[str]


class LLMCategorizationResult(BaseModel):
    """Result published by LLM worker back to the API."""

    transaction_id: str
    narration_clean: str
    suggested_ledger: Optional[str] = None
    confidence: Decimal = Decimal("0.000")
    payment_mode: Optional[str] = None
    counterparty: Optional[str] = None


class ExportJobMessage(BaseModel):
    """Message sent from API → exporter worker queue."""

    export_job_id: str
    statement_id: str
    format: str  # tally_xml | csv | excel
    firm_id: str
