import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.service import decode_token
from core.config import settings
from db.database import get_db
from db.models import ExportJob, Statement, Transaction, User
from auth.dependencies import get_current_user
from statements.exporters import generate_csv, generate_excel, generate_json, generate_tally_xml
from statements.schemas import ExportJobResponse, ExportRequest
from statements.router import verify_statement_access


export_router = APIRouter(tags=["exports"])
optional_security = HTTPBearer(auto_error=False)

EXPORTS_DIR = Path(__file__).resolve().parents[1] / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_TTL_HOURS = 24
DOWNLOAD_TOKEN_TTL_MINUTES = 15
READY_STATUSES = {"READY_FOR_REVIEW", "REVIEWED", "EXPORTED"}
FORMAT_EXT = {"tally_xml": "xml", "csv": "csv", "excel": "xlsx", "json": "json"}
FORMAT_CONTENT_TYPE = {
    "tally_xml": "application/xml",
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_filename(stmt: Statement | None, fmt: str) -> str:
    ext = FORMAT_EXT.get(fmt, "bin")
    bank = getattr(stmt, "bank_code", None) or "bank"
    stamp = utcnow().strftime("%Y-%m-%d")
    return f"{bank}_{stamp}_{fmt}.{ext}"


def _create_download_token(job: ExportJob, user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=DOWNLOAD_TOKEN_TTL_MINUTES)
    payload = {
        "sub": user.id,
        "type": "export_download",
        "export_id": job.id,
        "statement_id": job.statement_id,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _signed_download_url(job: ExportJob, user: User) -> str:
    return f"/v1/exports/{job.id}/download?download_token={_create_download_token(job, user)}"


def _statement_meta(stmt: Statement) -> dict[str, Any]:
    return {
        "id": stmt.id,
        "filename": stmt.metadata_.get("original_filename") or Path(stmt.file_url).name or "statement",
        "bank_id": stmt.bank_code or "Unknown",
        "file_type": stmt.file_type,
        "status": stmt.status,
    }


def _serialize_transaction(tx: Transaction) -> dict[str, Any]:
    amount = tx.debit if tx.debit is not None else tx.credit
    tx_type = "DEBIT" if tx.debit is not None else "CREDIT"
    return {
        "id": tx.id,
        "statement_id": tx.statement_id,
        "date": tx.txn_date.isoformat() if tx.txn_date else None,
        "value_date": tx.value_date.isoformat() if tx.value_date else None,
        "narration": tx.narration,
        "reference_no": tx.reference_no,
        "amount": amount,
        "tx_type": tx_type,
        "balance": tx.balance,
        "payment_mode": tx.payment_mode,
        "counterparty": tx.counterparty,
        "ledger_name": tx.confirmed_ledger or tx.suggested_ledger,
        "ocr_confidence": tx.ocr_confidence,
        "page_number": tx.page_number,
        "is_reviewed": bool(tx.confirmed_ledger) and not tx.is_ignored,
        "is_ignored": tx.is_ignored,
        "created_at": tx.created_at,
    }


async def _load_transactions(db: AsyncSession, statement_id: str) -> list[Transaction]:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.statement_id == statement_id)
        .order_by(Transaction.row_number)
    )
    return list(result.scalars().all())


async def _authorize_download(
    db: AsyncSession,
    job: ExportJob,
    credentials: HTTPAuthorizationCredentials | None,
    download_token: str | None,
) -> None:
    if download_token:
        try:
            payload = decode_token(download_token)
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Export download link has expired") from None
        except pyjwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid export download link") from None

        if (
            payload.get("type") != "export_download"
            or payload.get("export_id") != job.id
            or payload.get("statement_id") != job.statement_id
        ):
            raise HTTPException(status_code=401, detail="Invalid export download link")
        return

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired") from None
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from None

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type - expected access token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please verify your email address before accessing this resource.",
        )

    await verify_statement_access(db, job.statement_id, user)


async def _build_export_content(
    db: AsyncSession,
    stmt: Statement,
    fmt: str,
    company_name: str | None = None,
    bank_ledger_name: str | None = None,
    strict_reviewed_only: bool = False,
) -> tuple[bytes, int]:
    transactions = [_serialize_transaction(tx) for tx in await _load_transactions(db, stmt.id)]
    statement_meta = _statement_meta(stmt)

    if fmt == "tally_xml":
        content: bytes | str = generate_tally_xml(
            transactions,
            company_name=company_name or "My Company",
            bank_ledger_name=bank_ledger_name or "Bank Account",
            strict_reviewed_only=strict_reviewed_only,
        )
    elif fmt == "csv":
        content = generate_csv(transactions)
    elif fmt == "excel":
        content = generate_excel(transactions, statement_meta)
    elif fmt == "json":
        content = generate_json(transactions, statement_meta)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")

    payload = content if isinstance(content, bytes) else content.encode("utf-8")
    return payload, len(transactions)


def _write_export_file(statement_id: str, job_id: str, fmt: str, payload: bytes) -> Path:
    export_dir = EXPORTS_DIR / statement_id
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{job_id}.{FORMAT_EXT[fmt]}"
    file_path.write_bytes(payload)
    return file_path


@export_router.post("/v1/statements/{statement_id}/export", response_model=ExportJobResponse)
async def create_export(
    statement_id: str,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = await verify_statement_access(db, statement_id, current_user)
    if stmt.status not in READY_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Statement is not ready for export. Current status: {stmt.status}",
        )

    now = utcnow()
    existing_result = await db.execute(
        select(ExportJob).where(
            ExportJob.statement_id == statement_id,
            ExportJob.format == body.format,
            ExportJob.status == "READY",
            ExportJob.expires_at.is_not(None),
            ExportJob.expires_at > now,
        )
    )
    existing_job = existing_result.scalar_one_or_none()
    if existing_job:
        if not existing_job.file_path or not os.path.exists(existing_job.file_path):
            existing_job.status = "FAILED"
            existing_job.error_message = "Export file was missing on disk; regenerating."
            await db.flush()
        else:
            tx_count = (await db.execute(select(Transaction).where(Transaction.statement_id == statement_id))).scalars().all()
            return ExportJobResponse(
                export_id=existing_job.id,
                statement_id=statement_id,
                format=existing_job.format,
                status=existing_job.status,
                download_url=_signed_download_url(existing_job, current_user),
                filename=_make_filename(stmt, existing_job.format),
                expires_at=existing_job.expires_at,
                created_at=existing_job.created_at,
                transaction_count=len(tx_count),
                idempotent=True,
            )

    job = ExportJob(
        statement_id=statement_id,
        format=body.format,
        status="PENDING",
        company_name=body.company_name if body.format == "tally_xml" else None,
        bank_ledger=body.bank_ledger_name if body.format == "tally_xml" else None,
    )
    db.add(job)
    await db.flush()

    try:
        payload, transaction_count = await _build_export_content(
            db=db,
            stmt=stmt,
            fmt=body.format,
            company_name=body.company_name,
            bank_ledger_name=body.bank_ledger_name,
            strict_reviewed_only=body.strict_reviewed_only,
        )
    except HTTPException:
        raise
    except Exception as exc:
        job.status = "FAILED"
        job.error_message = str(exc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Export generation failed: {exc}") from exc

    file_path = _write_export_file(statement_id, job.id, body.format, payload)

    expires_at = utcnow() + timedelta(hours=EXPORT_TTL_HOURS)
    job.status = "READY"
    job.file_path = str(file_path)
    job.download_url = f"/v1/exports/{job.id}/download"
    job.expires_at = expires_at
    stmt.status = "EXPORTED"

    await db.commit()
    await db.refresh(job)

    return ExportJobResponse(
        export_id=job.id,
        statement_id=statement_id,
        format=job.format,
        status=job.status,
        download_url=_signed_download_url(job, current_user),
        filename=_make_filename(stmt, job.format),
        expires_at=job.expires_at,
        created_at=job.created_at,
        transaction_count=transaction_count,
        idempotent=False,
    )


@export_router.get("/v1/statements/{statement_id}/exports")
async def list_exports(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await verify_statement_access(db, statement_id, current_user)
    result = await db.execute(
        select(ExportJob)
        .where(ExportJob.statement_id == statement_id)
        .order_by(ExportJob.created_at.desc())
    )
    jobs = result.scalars().all()
    return [
        {
            "export_id": job.id,
            "statement_id": job.statement_id,
            "format": job.format,
            "status": job.status,
            "download_url": _signed_download_url(job, current_user) if job.status == "READY" else job.download_url,
            "filename": f"{statement_id[:8]}_{job.format}.{FORMAT_EXT.get(job.format, 'bin')}",
            "created_at": job.created_at,
            "expires_at": job.expires_at,
        }
        for job in jobs
    ]


@export_router.get("/v1/exports/{export_id}/download")
async def download_export(
    export_id: str,
    download_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExportJob).where(ExportJob.id == export_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Export not found")

    await _authorize_download(db, job, credentials, download_token)

    if job.status != "READY":
        raise HTTPException(status_code=409, detail=f"Export not ready. Status: {job.status}")
    if job.expires_at and job.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Export link has expired")

    stmt = await db.get(Statement, job.statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")

    if not job.file_path or not os.path.exists(job.file_path):
        try:
            payload, _ = await _build_export_content(
                db=db,
                stmt=stmt,
                fmt=job.format,
                company_name=job.company_name,
                bank_ledger_name=job.bank_ledger,
            )
            file_path = _write_export_file(job.statement_id, job.id, job.format, payload)
            job.file_path = str(file_path)
            job.expires_at = utcnow() + timedelta(hours=EXPORT_TTL_HOURS)
            await db.commit()
            await db.refresh(job)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Export file regeneration failed: {exc}") from exc

    filename = _make_filename(stmt, job.format)
    return FileResponse(
        path=job.file_path,
        media_type=FORMAT_CONTENT_TYPE.get(job.format, "application/octet-stream"),
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.delete("/v1/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ExportJob).where(ExportJob.id == export_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Export not found")

    # Verify access to the associated statement
    await verify_statement_access(db, job.statement_id, current_user)

    if job.file_path and os.path.exists(job.file_path):
        os.remove(job.file_path)

    await db.delete(job)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
