"""Pydantic schemas for statements and transactions API."""
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class TransactionItem(BaseModel):
    """Single transaction in response."""
    id: str
    statement_id: str
    row_number: Optional[int] = None
    txn_date: Optional[date] = None
    value_date: Optional[date] = None
    narration: Optional[str] = None
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
    is_ignored: bool = False
    ocr_confidence: Optional[Decimal] = None
    page_number: Optional[int] = None
    bbox: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionUpdate(BaseModel):
    """Partial update for a transaction (all fields optional)."""
    narration: Optional[str] = None
    narration_clean: Optional[str] = None
    reference_no: Optional[str] = None
    payment_mode: Optional[str] = None
    counterparty: Optional[str] = None
    suggested_ledger: Optional[str] = None
    confirmed_ledger: Optional[str] = None
    is_ignored: Optional[bool] = None


class BulkUpdateItem(BaseModel):
    """Single item in bulk update request."""
    id: str
    narration: Optional[str] = None
    narration_clean: Optional[str] = None
    reference_no: Optional[str] = None
    payment_mode: Optional[str] = None
    counterparty: Optional[str] = None
    suggested_ledger: Optional[str] = None
    confirmed_ledger: Optional[str] = None
    is_ignored: Optional[bool] = None


class BulkUpdateRequest(BaseModel):
    """Bulk update request body."""
    updates: List[BulkUpdateItem]


class BulkUpdateResponse(BaseModel):
    """Response to bulk update."""
    updated: int
    failed: List[dict] = []


class StatementListItem(BaseModel):
    """Single statement in list response."""
    id: str
    filename: str = "statement"
    client_id: str
    file_type: str
    bank_id: Optional[str] = None
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    transaction_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactions(BaseModel):
    """Paginated list of transactions."""
    items: List[TransactionItem]
    total: int
    page: int
    size: int
    pages: int


class PaginatedStatements(BaseModel):
    """Paginated list of statements."""
    items: List[StatementListItem]
    total: int
    page: int
    size: int
    pages: int


class StatementStatusUpdate(BaseModel):
    """Request to update statement status."""
    status: str


class EnrichTransactionsRequest(BaseModel):
    """Request to enrich parsed transaction narrations."""
    transaction_ids: Optional[List[str]] = None
    only_missing: bool = True
    limit: int = 50
    force: bool = False  # When True, clears stale cache and re-runs scoring from scratch


class ExportRequest(BaseModel):
    format: str
    company_name: Optional[str] = "My Company"
    bank_ledger_name: Optional[str] = "Bank Account"
    strict_reviewed_only: bool = False

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        allowed = {"tally_xml", "csv", "json", "excel"}
        if value not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return value


class ExportJobResponse(BaseModel):
    export_id: str
    job_id: Optional[str] = None
    statement_id: str
    format: str
    status: str
    download_url: Optional[str] = None
    filename: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    transaction_count: int = 0
    idempotent: bool = False
    progress: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
