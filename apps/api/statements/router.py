import shutil
import asyncio
import csv
import json
from io import BytesIO, StringIO
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile, status,
    BackgroundTasks, WebSocket, WebSocketDisconnect
)
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db, async_session
from db.models import Client, Firm, Statement, Transaction, LedgerMapping, utcnow
from statements.parser import StatementParserError, parse_statement

router = APIRouter(prefix="/v1/statements", tags=["statements"])

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FIRM_NAME = "Default Firm"
DEFAULT_CLIENT_NAME = "Default Client"


# ─── Pydantic schemas ────────────────────────────────────────
class TransactionUpdate(BaseModel):
    confirmed_ledger: str | None = None
    narration_clean: str | None = None
    is_ignored: bool | None = None
    txn_date: str | None = None
    narration: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None
    reference_no: str | None = None


class TransactionBulkUpdate(BaseModel):
    ids: List[str]
    updates: TransactionUpdate


# ─── WebSocket Connection Manager ─────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, statement_id: str, websocket: WebSocket):
        await websocket.accept()
        if statement_id not in self.active_connections:
            self.active_connections[statement_id] = []
        self.active_connections[statement_id].append(websocket)

    def disconnect(self, statement_id: str, websocket: WebSocket):
        if statement_id in self.active_connections:
            self.active_connections[statement_id].remove(websocket)
            if not self.active_connections[statement_id]:
                del self.active_connections[statement_id]

    async def broadcast_status(self, statement_id: str, status: str, progress_percent: int = 100):
        if statement_id in self.active_connections:
            message = {
                "event": "status_changed",
                "status": status,
                "progress_percent": progress_percent,
                "statement_id": statement_id
            }
            for connection in self.active_connections[statement_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


# ─── Helper Functions ────────────────────────────────────────
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
        "file_type": statement.file_type,
        "account_number": statement.account_number,
        "account_holder": statement.account_holder,
        "period_start": statement.period_start.isoformat() if statement.period_start else None,
        "period_end": statement.period_end.isoformat() if statement.period_end else None,
        "opening_balance": money(statement.opening_balance),
        "closing_balance": money(statement.closing_balance),
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
        "confirmed_ledger": transaction.confirmed_ledger,
        "suggested_ledger": transaction.suggested_ledger,
        "confidence": float(transaction.confidence) if transaction.confidence is not None else None,
        "is_ignored": transaction.is_ignored,
        "page_number": transaction.page_number,
    }


def build_excel_html(transactions: list[Transaction]) -> bytes:
    rows = [
        "<tr>"
        "<th>Date</th><th>Description</th><th>Debit</th><th>Credit</th>"
        "<th>Balance</th><th>Suggested Ledger</th><th>Confirmed Ledger</th><th>Confidence</th>"
        "</tr>"
    ]
    for txn in transactions:
        rows.append(
            "<tr>"
            f"<td>{txn.txn_date.isoformat()}</td>"
            f"<td>{txn.narration}</td>"
            f"<td>{money(txn.debit) or ''}</td>"
            f"<td>{money(txn.credit) or ''}</td>"
            f"<td>{money(txn.balance) or ''}</td>"
            f"<td>{txn.suggested_ledger or ''}</td>"
            f"<td>{txn.confirmed_ledger or ''}</td>"
            f"<td>{float(txn.confidence) if txn.confidence is not None else ''}</td>"
            "</tr>"
        )
    html = (
        "<html><head><meta charset=\"UTF-8\"/></head><body>"
        "<table border=\"1\">"
        + "".join(rows)
        + "</table></body></html>"
    )
    return html.encode("utf-8")


def build_tally_xml(statement: Statement, transactions: list[Transaction]) -> str:
    xml_rows = []
    for txn in transactions:
        amount = txn.debit if txn.debit is not None else txn.credit or Decimal("0.00")
        is_debit = txn.debit is not None
        ledger_name = txn.confirmed_ledger or txn.suggested_ledger or "Unmapped"
        amt_str = f"{abs(amount):.2f}"
        dr_cr = "Payment" if is_debit else "Receipt"
        xml_rows.append(
            f"<TALLYMESSAGE xmlns=\"UDF\">"
            f"<VOUCHER VCHTYPE=\"{dr_cr}\" ACTION=\"Create\">"
            f"<DATE>{txn.txn_date.strftime('%Y%m%d')}</DATE>"
            f"<NARRATION>{txn.narration}</NARRATION>"
            f"<VOUCHERTYPENAME>{dr_cr}</VOUCHERTYPENAME>"
            f"<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{ledger_name}</LEDGERNAME>"
            f"<AMOUNT>{'-' if is_debit else ''}{amt_str}</AMOUNT>"
            f"</ALLLEDGERENTRIES.LIST>"
            "<ALLLEDGERENTRIES.LIST>"
            "<LEDGERNAME>Bank Account</LEDGERNAME>"
            f"<AMOUNT>{amt_str if is_debit else '-' + amt_str}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
            "</VOUCHER>"
            "</TALLYMESSAGE>"
        )
    body = "".join(xml_rows)
    return (
        "<ENVELOPE>"
        "<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        "<BODY><IMPORTDATA>"
        "<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC>"
        "<REQUESTDATA>"
        + body +
        "</REQUESTDATA></IMPORTDATA></BODY>"
        "</ENVELOPE>"
    )


# ─── Background processing task ──────────────────────────────
async def process_statement_task(statement_id: str, file_path: Path, bank_code: str | None):
    # Set status to PARSING
    async with async_session() as db:
        statement = await db.get(Statement, statement_id)
        if not statement:
            return
        statement.status = "PARSING"
        await db.commit()
        await manager.broadcast_status(statement_id, "PARSING", 30)

    try:
        # Run cpu-bound parsing in default threadpool executor
        loop = asyncio.get_event_loop()
        parsed = await loop.run_in_executor(None, parse_statement, file_path, bank_code)
    except Exception as exc:
        async with async_session() as db:
            statement = await db.get(Statement, statement_id)
            if statement:
                statement.status = "FAILED"
                statement.error_message = str(exc)
                await db.commit()
                await manager.broadcast_status(statement_id, "FAILED", 100)
        return

    async with async_session() as db:
        statement = await db.get(Statement, statement_id)
        if not statement:
            return

        detected_bank = parsed.metadata.get("template_bank")
        if detected_bank:
            statement.bank_code = detected_bank

        statement.metadata_ = {
            **statement.metadata_,
            **parsed.metadata,
        }
        statement.status = "READY_FOR_REVIEW"

        # Load client mapping memory to auto-suggest ledgers
        mapping_result = await db.execute(
            select(LedgerMapping).where(LedgerMapping.client_id == statement.client_id)
        )
        mappings = mapping_result.scalars().all()

        transactions_to_add = []
        for txn in parsed.transactions:
            suggested_ledger = None
            confidence = None

            for mapping in mappings:
                if mapping.pattern.lower() in txn.narration.lower():
                    suggested_ledger = mapping.ledger_name
                    confidence = Decimal("1.000")
                    break

            transactions_to_add.append(
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
                    suggested_ledger=suggested_ledger,
                    confidence=confidence,
                )
            )

        db.add_all(transactions_to_add)
        await db.commit()
        await manager.broadcast_status(statement_id, "READY_FOR_REVIEW", 100)


# ─── Routes ──────────────────────────────────────────────────
@router.post("/upload")
async def upload_statement(
    background_tasks: BackgroundTasks,
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

    await db.commit()

    # Dispatch to background task
    background_tasks.add_task(process_statement_task, statement.id, file_path, bank)

    return {
        "success": True,
        "message": "Statement uploaded successfully. Processing started.",
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
            "transactions": [
                {
                    **serialize_transaction(txn),
                    "confirmed_ledger": txn.confirmed_ledger,
                    "suggested_ledger": txn.suggested_ledger,
                    "confidence": float(txn.confidence) if txn.confidence is not None else None,
                    "is_ignored": txn.is_ignored,
                }
                for txn in transactions
            ],
        },
    }


# Serve file endpoint (required for PDF preview)
@router.get("/{statement_id}/file")
async def get_statement_file(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    file_path = Path(statement.file_url)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement file does not exist on server.",
        )

    media_type = "application/pdf"
    if statement.file_type == "csv":
        media_type = "text/csv"
    elif statement.file_type in {"xlsx", "xls"}:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif statement.file_type == "image":
        media_type = "image/png"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=file_path.name,
    )


# Paginated, filterable transactions query
@router.get("/{statement_id}/transactions")
async def get_statement_transactions(
    statement_id: str,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    ledger: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    include_ignored: bool = False,
    sort_by: str | None = None,
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    query = select(Transaction).where(Transaction.statement_id == statement_id)

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Transaction.narration.ilike(search_filter) |
            Transaction.suggested_ledger.ilike(search_filter) |
            Transaction.confirmed_ledger.ilike(search_filter)
        )

    if ledger:
        ledger_filter = f"%{ledger}%"
        query = query.where(
            Transaction.suggested_ledger.ilike(ledger_filter) |
            Transaction.confirmed_ledger.ilike(ledger_filter)
        )

    if date_from:
        try:
            parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.where(Transaction.txn_date >= parsed_from)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be in YYYY-MM-DD format",
            )

    if date_to:
        try:
            parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            query = query.where(Transaction.txn_date <= parsed_to)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_to must be in YYYY-MM-DD format",
            )

    if min_amount is not None:
        query = query.where(
            (Transaction.debit >= min_amount) | (Transaction.credit >= min_amount)
        )
    if max_amount is not None:
        query = query.where(
            (Transaction.debit <= max_amount) | (Transaction.credit <= max_amount)
        )

    if not include_ignored:
        query = query.where(Transaction.is_ignored == False)

    if sort_by:
        col = getattr(Transaction, sort_by, None)
        if col:
            if sort_order == "desc":
                query = query.order_by(col.desc())
            else:
                query = query.order_by(col.asc())
    else:
        query = query.order_by(Transaction.row_number.asc())

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    transactions = result.scalars().all()

    return {
        "success": True,
        "message": "Transactions fetched successfully",
        "data": {
            "transactions": [serialize_transaction(txn) for txn in transactions],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


# Update transaction inline
@router.patch("/{statement_id}/transactions/{txn_id}")
async def update_transaction(
    statement_id: str,
    txn_id: str,
    payload: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    transaction = await db.get(Transaction, txn_id)
    if not transaction or transaction.statement_id != statement_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "txn_date" in update_data and update_data["txn_date"]:
        try:
            update_data["txn_date"] = datetime.strptime(update_data["txn_date"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="txn_date must be in YYYY-MM-DD format",
            )

    for key, val in update_data.items():
        setattr(transaction, key, val)

    if payload.confirmed_ledger:
        pattern = transaction.narration[:30].strip()
        map_result = await db.execute(
            select(LedgerMapping).where(
                LedgerMapping.client_id == statement.client_id,
                LedgerMapping.pattern == pattern
            )
        )
        mapping = map_result.scalar_one_or_none()
        if mapping:
            mapping.ledger_name = payload.confirmed_ledger
            mapping.hit_count += 1
            mapping.last_used_at = utcnow()
        else:
            new_mapping = LedgerMapping(
                client_id=statement.client_id,
                pattern=pattern,
                ledger_name=payload.confirmed_ledger,
                hit_count=1,
            )
            db.add(new_mapping)

    await db.commit()

    return {
        "success": True,
        "message": "Transaction updated successfully",
        "data": {
            **serialize_transaction(transaction),
            "confirmed_ledger": transaction.confirmed_ledger,
            "suggested_ledger": transaction.suggested_ledger,
            "confidence": float(transaction.confidence) if transaction.confidence is not None else None,
            "is_ignored": transaction.is_ignored,
        }
    }


# Bulk update transactions
@router.post("/{statement_id}/transactions/bulk-update")
async def bulk_update_transactions(
    statement_id: str,
    payload: TransactionBulkUpdate,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    result = await db.execute(
        select(Transaction).where(
            Transaction.statement_id == statement_id,
            Transaction.id.in_(payload.ids)
        )
    )
    transactions = result.scalars().all()

    update_data = payload.updates.model_dump(exclude_unset=True)
    if "txn_date" in update_data and update_data["txn_date"]:
        try:
            update_data["txn_date"] = datetime.strptime(update_data["txn_date"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="txn_date must be in YYYY-MM-DD format",
            )

    for transaction in transactions:
        for key, val in update_data.items():
            setattr(transaction, key, val)

        if payload.updates.confirmed_ledger:
            pattern = transaction.narration[:30].strip()
            map_result = await db.execute(
                select(LedgerMapping).where(
                    LedgerMapping.client_id == statement.client_id,
                    LedgerMapping.pattern == pattern
                )
            )
            mapping = map_result.scalar_one_or_none()
            if mapping:
                mapping.ledger_name = payload.updates.confirmed_ledger
                mapping.hit_count += 1
                mapping.last_used_at = utcnow()
            else:
                new_mapping = LedgerMapping(
                    client_id=statement.client_id,
                    pattern=pattern,
                    ledger_name=payload.updates.confirmed_ledger,
                    hit_count=1,
                )
                db.add(new_mapping)

    await db.commit()

    return {
        "success": True,
        "message": f"Successfully updated {len(transactions)} transactions",
    }


# List all statements
@router.get("/{statement_id}/export")
async def export_statement(
    statement_id: str,
    format: str = "csv",
    include_ignored: bool = False,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    result = await db.execute(
        select(Transaction).where(Transaction.statement_id == statement_id)
    )
    transactions = result.scalars().all()

    format_normalized = format.lower()
    filename_base = statement.metadata_.get("original_filename") or statement.id

    if format_normalized == "csv":
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "Date",
            "Value Date",
            "Description",
            "Reference No",
            "Debit",
            "Credit",
            "Balance",
            "Suggested Ledger",
            "Confirmed Ledger",
            "Confidence",
            "Ignored",
        ])
        for txn in transactions:
            if not include_ignored and txn.is_ignored:
                continue
            writer.writerow([
                txn.txn_date.isoformat(),
                txn.value_date.isoformat() if txn.value_date else "",
                txn.narration,
                txn.reference_no or "",
                money(txn.debit) or "",
                money(txn.credit) or "",
                money(txn.balance) or "",
                txn.suggested_ledger or "",
                txn.confirmed_ledger or "",
                float(txn.confidence) if txn.confidence is not None else "",
                "Yes" if txn.is_ignored else "No",
            ])
        payload = buffer.getvalue().encode("utf-8")
        return StreamingResponse(
            BytesIO(payload),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename_base}.csv\""
            },
        )

    if format_normalized == "json":
        payload = [
            {
                **serialize_transaction(txn),
                "value_date": txn.value_date.isoformat() if txn.value_date else None,
                "reference_no": txn.reference_no,
                "payment_mode": txn.payment_mode,
                "counterparty": txn.counterparty,
            }
            for txn in transactions
            if include_ignored or not txn.is_ignored
        ]
        return JSONResponse(
            content=payload,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename_base}.json\""
            },
        )

    if format_normalized == "excel":
        payload = build_excel_html(transactions if include_ignored else [t for t in transactions if not t.is_ignored])
        return StreamingResponse(
            BytesIO(payload),
            media_type="application/vnd.ms-excel",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename_base}.xls\""
            },
        )

    if format_normalized == "tally_xml":
        payload = build_tally_xml(statement, [t for t in transactions if include_ignored or not t.is_ignored])
        return StreamingResponse(
            BytesIO(payload.encode("utf-8")),
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename_base}.xml\""
            },
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported export format. Use csv, json, excel, or tally_xml.",
    )


@router.get("")
async def list_statements(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Statement).order_by(Statement.created_at.desc())
    )
    statements = result.scalars().all()
    return {
        "success": True,
        "message": "Statements fetched successfully",
        "data": [serialize_statement(stmt) for stmt in statements]
    }


# WebSocket Status Route
@router.websocket("/ws/statements/{statement_id}")
async def websocket_endpoint(websocket: WebSocket, statement_id: str):
    await manager.connect(statement_id, websocket)
    try:
        # Check and send current status on connect
        async with async_session() as db:
            statement = await db.get(Statement, statement_id)
            if statement:
                await websocket.send_json({
                    "event": "status_changed",
                    "status": statement.status,
                    "progress_percent": 100 if statement.status in {"READY_FOR_REVIEW", "FAILED", "EXPORTED"} else 30,
                    "statement_id": statement_id
                })

        while True:
            # Keep connection open
            await websocket.receive_text()
            await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(statement_id, websocket)
    except Exception:
        manager.disconnect(statement_id, websocket)
