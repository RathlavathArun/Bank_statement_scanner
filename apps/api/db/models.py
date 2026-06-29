"""
SQLAlchemy ORM models — all 9 tables from PRD section 8.
Uses UUIDv7 (sortable) for primary keys, NUMERIC(18,2) for money fields.
"""
import uuid
from datetime import datetime, timezone, date
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Text, Integer,
    ForeignKey, UniqueConstraint, Numeric, Index, JSON,
)
from sqlalchemy.orm import relationship
from db.database import Base


def generate_uuid() -> str:
    """Generate a UUIDv7-like sortable UUID (falls back to v4 if uuid6 unavailable)."""
    try:
        from uuid6 import uuid7
        return str(uuid7())
    except ImportError:
        return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── 8.2 Table: firms ───────────────────────────────────────
class Firm(Base):
    __tablename__ = "firms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    gstin = Column(String(15), nullable=True)
    subscription = Column(String(50), nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    members = relationship("FirmMember", back_populates="firm", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="firm", cascade="all, delete-orphan")


# ─── 8.3 Table: users ───────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(15), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    # Task 8: TOTP MFA — secret stored Fernet-encrypted at rest
    totp_secret_enc = Column(Text, nullable=True)  # base64-encoded Fernet ciphertext
    totp_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    memberships = relationship("FirmMember", back_populates="user", cascade="all, delete-orphan")


# ─── 8.4 Table: firm_members ────────────────────────────────
class FirmMember(Base):
    __tablename__ = "firm_members"
    __table_args__ = (
        UniqueConstraint("firm_id", "user_id", name="uq_firm_user"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False, default="member")  # owner | admin | member | viewer

    # Relationships
    firm = relationship("Firm", back_populates="members")
    user = relationship("User", back_populates="memberships")


# ─── 8.5 Table: clients ─────────────────────────────────────
class Client(Base):
    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    firm_id = Column(String(36), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    gstin = Column(String(15), nullable=True)
    pan = Column(String(10), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    firm = relationship("Firm", back_populates="clients")
    statements = relationship("Statement", back_populates="client", cascade="all, delete-orphan")
    ledger_mappings = relationship("LedgerMapping", back_populates="client", cascade="all, delete-orphan")
    ledgers = relationship("Ledger", back_populates="client", cascade="all, delete-orphan")
    narration_rules = relationship("NarrationRule", back_populates="client", cascade="all, delete-orphan")


# ─── 8.6 Table: statements ──────────────────────────────────
class Statement(Base):
    __tablename__ = "statements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf | xlsx | xls | csv | image
    bank_code = Column(String(50), nullable=True)  # HDFC, ICICI, SBI, etc.
    account_number = Column(String(50), nullable=True)
    account_holder = Column(String(255), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    opening_balance = Column(Numeric(18, 2), nullable=True)
    closing_balance = Column(Numeric(18, 2), nullable=True)
    status = Column(String(30), nullable=False, default="UPLOADED")
    # UPLOADED | PARSING | OCR | READY_FOR_REVIEW | EXPORTED | FAILED
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    client = relationship("Client", back_populates="statements")
    uploader = relationship("User")
    transactions = relationship("Transaction", back_populates="statement", cascade="all, delete-orphan")
    export_jobs = relationship("ExportJob", back_populates="statement", cascade="all, delete-orphan")


# ─── 8.7 Table: transactions ────────────────────────────────
class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("statement_id", "row_number", name="uq_statement_row_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    statement_id = Column(String(36), ForeignKey("statements.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    txn_date = Column(Date, nullable=False)
    value_date = Column(Date, nullable=True)
    narration = Column(Text, nullable=False)
    narration_clean = Column(Text, nullable=True)  # LLM-cleaned version
    reference_no = Column(String(100), nullable=True)
    debit = Column(Numeric(18, 2), nullable=True)
    credit = Column(Numeric(18, 2), nullable=True)
    balance = Column(Numeric(18, 2), nullable=True)
    payment_mode = Column(String(20), nullable=True)  # UPI | NEFT | RTGS | IMPS | CHEQUE | CASH
    counterparty = Column(String(255), nullable=True)
    suggested_ledger = Column(String(255), nullable=True)
    confirmed_ledger = Column(String(255), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)  # 0.000 to 1.000
    is_ignored = Column(Boolean, nullable=False, default=False)
    ocr_confidence = Column(Numeric(4, 3), nullable=True)
    page_number = Column(Integer, nullable=True)
    bbox = Column(JSON, nullable=True)  # Bounding box for PDF preview
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    statement = relationship("Statement", back_populates="transactions")


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    statement_id = Column(String(36), ForeignKey("statements.id", ondelete="CASCADE"), nullable=False, index=True)
    format = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    file_path = Column(Text, nullable=True)
    s3_key = Column(String(255), nullable=True)
    download_url = Column(Text, nullable=True)
    company_name = Column(String(255), nullable=True)
    bank_ledger = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    statement = relationship("Statement", back_populates="export_jobs")


# ─── 8.8 Table: ledger_mappings ──────────────────────────────
class LedgerMapping(Base):
    __tablename__ = "ledger_mappings"
    __table_args__ = (
        UniqueConstraint("client_id", "pattern", name="uq_client_pattern"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    pattern = Column(Text, nullable=False)
    ledger_name = Column(String(255), nullable=False)
    hit_count = Column(Integer, nullable=False, default=1)
    last_used_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Relationships
    client = relationship("Client", back_populates="ledger_mappings")
    creator = relationship("User")


# ─── 8.9 Table: ledgers ─────────────────────────────────────
class Ledger(Base):
    __tablename__ = "ledgers"
    __table_args__ = (
        UniqueConstraint("client_id", "name", name="uq_client_ledger"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    group_name = Column(String(255), nullable=False)  # Tally group
    tally_id = Column(String(100), nullable=True)  # External Tally GUID

    # Relationships
    client = relationship("Client", back_populates="ledgers")


# ─── Task 20: Custom Rules Engine (FR-4.6) ────────────────────────
# Deterministic "if narration X → assign ledger Y" rules defined by CA firms.
# These run BEFORE recurring detection and LLM enrichment, giving the CA
# full control to override automated suggestions for known counterparties.
class NarrationRule(Base):
    __tablename__ = "narration_rules"
    __table_args__ = (
        UniqueConstraint("client_id", "match_type", "pattern", name="uq_client_rule"),
        Index("ix_narration_rules_client_active", "client_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    # match_type: contains | startswith | endswith | regex | exact
    match_type = Column(String(20), nullable=False, default="contains")
    pattern = Column(Text, nullable=False)      # the text or regex to match against narration
    ledger_name = Column(String(255), nullable=False)  # ledger to assign on match
    priority = Column(Integer, nullable=False, default=100)  # lower = higher priority
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    client = relationship("Client", back_populates="narration_rules")
    creator = relationship("User")


# ─── Audit Log (additional for security compliance) ──────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)  # CREATE | READ | UPDATE | DELETE
    resource_type = Column(String(100), nullable=False)  # statement | transaction | client
    resource_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    user = relationship("User")


class LLMCache(Base):
    __tablename__ = "llm_cache"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    content_hash = Column(String(64), unique=True, nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    response_json = Column(JSON, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    statement_id = Column(String(36), ForeignKey("statements.id", ondelete="CASCADE"), nullable=True, index=True)
    transaction_id = Column(String(36), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    operation = Column(String(100), nullable=False)
    cache_status = Column(String(20), nullable=False)  # HIT | MISS | FALLBACK
    content_hash = Column(String(64), nullable=True, index=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


# ─── 8.10 Table: bank_templates ─────────────────────────────
class BankTemplate(Base):
    __tablename__ = "bank_templates"
    __table_args__ = (
        UniqueConstraint("bank_code", name="uq_bank_code"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    bank_code = Column(String(50), nullable=False, unique=True, index=True)
    bank_name = Column(String(255), nullable=False)
    template_path = Column(Text, nullable=False)  # Path to YAML file or S3 key
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    template_format = Column(String(20), nullable=False, default="yaml")  # yaml | json
    extraction_type = Column(String(50), nullable=False, default="pdf_text")  # pdf_text | excel | csv
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    uploader = relationship("User")


# ─── OTP Table ──────────────────────────────────────────────
class OTP(Base):
    __tablename__ = "otps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    identifier = Column(String(255), nullable=False, index=True) # Email or phone
    otp_code = Column(String(10), nullable=False)
    purpose = Column(String(50), nullable=False) # "login", "reset"
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

# ─── OTP Codes (email verification & password reset) ────────
class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    purpose = Column(String(20), nullable=False)  # verify_email | reset_password
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    user = relationship("User")


# ─── Password Reset Tokens ──────────────────────────────────
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    user = relationship("User")
