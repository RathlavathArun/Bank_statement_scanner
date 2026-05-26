import shutil
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Client, Firm, Statement, Transaction
from statements.parser import StatementParserError, parse_statement

router = APIRouter(prefix="/v1/statements", tags=["statements"])

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FIRM_NAME = "Default Firm"
DEFAULT_CLIENT_NAME = "Default Client"


def file_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"pdf", "csv", "xlsx", "xls"}:
        return suffix
    if suffix in {"jpg", "jpeg", "png", "webp"}:
        return "image"
    return suffix or "unknown"


def money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


async def get_or_create_default_client(db: AsyncSession) -> Client:
    result = await db.execute(select(Client).where(Client.name == DEFAULT_CLIENT_NAME))
    client = result.scalar_one_or_none()
    if client:
        return client

    firm = Firm(name=DEFAULT_FIRM_NAME)
    db.add(firm)
    await db.flush()

    client = Client(firm_id=firm.id, name=DEFAULT_CLIENT_NAME)
    db.add(client)
    await db.flush()

    return client


def serialize_statement(statement: Statement) -> dict:
    return {
        "id": statement.id,
        "filename": statement.metadata_.get("original_filename"),
        "bank": statement.bank_code,
        "status": statement.status,
        "path": statement.file_url,
        "error": statement.error_message,
    }


def serialize_transaction(transaction: Transaction) -> dict:
    return {
        "id": transaction.id,
        "date": transaction.txn_date.isoformat(),
        "value_date": transaction.value_date.isoformat() if transaction.value_date else None,
        "description": transaction.narration,
        "reference_no": transaction.reference_no,
        "debit": money(transaction.debit),
        "credit": money(transaction.credit),
        "balance": money(transaction.balance),
    }


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    original_filename = file.filename or "statement"
    client = await get_or_create_default_client(db)

    statement = Statement(
        client_id=client.id,
        file_url="",
        file_type=file_type_for(original_filename),
        bank_code=bank,
        status="UPLOADED",
        metadata_={"original_filename": original_filename},
    )
    db.add(statement)
    await db.flush()

    safe_filename = Path(original_filename).name
    file_path = UPLOAD_DIR / f"{statement.id}-{safe_filename}"
    statement.file_url = str(file_path)

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    statement.status = "PARSING"
    try:
        parsed = parse_statement(file_path, bank)
    except StatementParserError as exc:
        statement.status = "FAILED"
        statement.error_message = str(exc)
    else:
        statement.metadata_ = {
            **statement.metadata_,
            **parsed.metadata,
        }
        statement.status = "READY_FOR_REVIEW"
        db.add_all(
            [
                Transaction(
                    statement_id=statement.id,
                    row_number=txn.row_number,
                    txn_date=txn.txn_date,
                    value_date=txn.value_date,
                    narration=txn.narration,
                    reference_no=txn.reference_no,
                    debit=txn.debit,
                    credit=txn.credit,
                    balance=txn.balance,
                )
                for txn in parsed.transactions
            ]
        )
    await db.flush()

    return {
        "success": True,
        "message": "Statement uploaded successfully",
        "data": serialize_statement(statement),
    }


@router.get("/{statement_id}/status")
async def get_statement_status(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    return {
        "success": True,
        "message": "Statement status fetched successfully",
        "data": serialize_statement(statement),
    }


@router.get("/{statement_id}/result")
async def get_statement_result(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    result = await db.execute(
        select(Transaction)
        .where(Transaction.statement_id == statement_id)
        .order_by(Transaction.row_number)
    )
    transactions = result.scalars().all()

    return {
        "success": True,
        "message": "Statement parsed successfully",
        "data": {
            **serialize_statement(statement),
            "transactions": [serialize_transaction(txn) for txn in transactions],
        },
    }
