import os
import json
import uuid
import base64
from pathlib import Path
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from auth.dependencies import get_current_user
from db.models import User, Statement
from core.security import get_or_create_firm_client
from core.telemetry import tracer
from core.config import settings
from .router import (
    UPLOAD_DIR,
    scan_bytes,
    file_type_for,
    notify_status_change,
    process_statement_job,
    update_job_progress,
)

# Late imports to avoid circular dependency if celery tasks are imported
from .tasks import process_statement_task

tus_router = APIRouter()

def _decode_metadata(meta_str: str) -> dict:
    meta = {}
    if not meta_str:
        return meta
    for kv in meta_str.split(","):
        parts = kv.split(" ", 1)
        key = parts[0]
        if len(parts) > 1:
            val = base64.b64decode(parts[1]).decode("utf-8")
        else:
            val = ""
        meta[key] = val
    return meta

@tus_router.options("/{path:path}")
async def tus_options(request: Request, response: Response):
    response.headers["Tus-Resumable"] = "1.0.0"
    response.headers["Tus-Version"] = "1.0.0"
    response.headers["Tus-Extension"] = "creation,termination"
    response.headers["Tus-Max-Size"] = "104857600"  # 100MB
    response.headers["Access-Control-Expose-Headers"] = "Tus-Resumable, Tus-Version, Tus-Extension, Tus-Max-Size, Upload-Length, Upload-Offset, Location, Upload-Metadata, X-Statement-Id"
    return Response(status_code=204)

@tus_router.post("/")
async def tus_create(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    upload_length = request.headers.get("Upload-Length")
    if not upload_length:
        raise HTTPException(status_code=400, detail="Missing Upload-Length header")
    
    upload_metadata = request.headers.get("Upload-Metadata", "")
    
    uid = str(uuid.uuid4())
    info_path = UPLOAD_DIR / f"tus_{uid}.info"
    bin_path = UPLOAD_DIR / f"tus_{uid}.bin"
    
    meta = _decode_metadata(upload_metadata)
    
    info = {
        "id": uid,
        "length": int(upload_length),
        "offset": 0,
        "metadata": meta,
        "user_id": str(current_user.id)
    }
    
    info_path.write_text(json.dumps(info))
    bin_path.touch()
    
    response.headers["Tus-Resumable"] = "1.0.0"
    response.headers["Location"] = f"{request.url.path}/{uid}"
    response.headers["Access-Control-Expose-Headers"] = "Location, Tus-Resumable"
    response.status_code = status.HTTP_201_CREATED
    return ""

@tus_router.head("/{uid}")
async def tus_head(
    uid: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    info_path = UPLOAD_DIR / f"tus_{uid}.info"
    if not info_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found")
        
    info = json.loads(info_path.read_text())
    
    if info["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    response.headers["Tus-Resumable"] = "1.0.0"
    response.headers["Upload-Offset"] = str(info["offset"])
    response.headers["Upload-Length"] = str(info["length"])
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=200)

@tus_router.patch("/{uid}")
async def tus_patch(
    uid: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    info_path = UPLOAD_DIR / f"tus_{uid}.info"
    bin_path = UPLOAD_DIR / f"tus_{uid}.bin"
    
    if not info_path.exists():
        raise HTTPException(status_code=404, detail="Upload not found")
        
    info = json.loads(info_path.read_text())
    
    if info["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    upload_offset = request.headers.get("Upload-Offset")
    if not upload_offset or int(upload_offset) != info["offset"]:
        raise HTTPException(status_code=409, detail="Conflict in Upload-Offset")
        
    content_type = request.headers.get("Content-Type")
    if content_type != "application/offset+octet-stream":
        raise HTTPException(status_code=415, detail="Unsupported Media Type")
        
    # Read chunk and append
    chunk = await request.body()
    with open(bin_path, "ab") as f:
        f.write(chunk)
        
    new_offset = info["offset"] + len(chunk)
    info["offset"] = new_offset
    info_path.write_text(json.dumps(info))
    
    response.headers["Tus-Resumable"] = "1.0.0"
    response.headers["Upload-Offset"] = str(new_offset)
    response.headers["Access-Control-Expose-Headers"] = "Upload-Offset, Tus-Resumable, X-Statement-Id"
    
    # If complete, process it like /upload
    if new_offset == info["length"]:
        statement_id = await _finalize_tus_upload(uid, info, bin_path, db, current_user)
        response.headers["X-Statement-Id"] = statement_id
        
        # Cleanup tus files
        try:
            info_path.unlink()
        except:
            pass
            
    return Response(status_code=204)

@tus_router.delete("/{uid}")
async def tus_delete(
    uid: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    info_path = UPLOAD_DIR / f"tus_{uid}.info"
    bin_path = UPLOAD_DIR / f"tus_{uid}.bin"
    
    if info_path.exists():
        info = json.loads(info_path.read_text())
        if info["user_id"] != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not authorized")
        info_path.unlink()
        
    if bin_path.exists():
        bin_path.unlink()
        
    response.headers["Tus-Resumable"] = "1.0.0"
    return Response(status_code=204)

async def _finalize_tus_upload(uid: str, info: dict, bin_path: Path, db: AsyncSession, current_user: User) -> str:
    """Run ClamAV, create DB record, check PDF password, and spawn celery task (same as standard upload)"""
    meta = info["metadata"]
    original_filename = meta.get("filename", "statement")
    bank = meta.get("bank", None)
    password = meta.get("password", None)
    
    client = await get_or_create_firm_client(db, current_user)
    
    with tracer.start_as_current_span("upload_file_tus") as span:
        span.set_attribute("filename", original_filename)
        file_bytes = bin_path.read_bytes()
        
        await scan_bytes(file_bytes, filename=original_filename)
        
        statement = Statement(
            client_id=client.id,
            uploaded_by=current_user.id,
            file_url="",
            file_type=file_type_for(original_filename),
            bank_code=bank,
            status="UPLOADED",
            metadata_={"original_filename": original_filename, "tus_id": uid},
        )
        db.add(statement)
        await db.flush()
        
        safe_filename = Path(original_filename).name
        file_path = UPLOAD_DIR / f"{statement.id}-{safe_filename}"
        statement.file_url = str(file_path)
        
        # Move the temporary bin file to the permanent file_path
        bin_path.rename(file_path)
        span.set_attribute("statement_id", statement.id)
        
    statement.status = "PARSING"
    await db.flush()
    await notify_status_change(statement.id, statement.status)
    
    if statement.file_type == "pdf":
        import pdfplumber
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        try:
            with pdfplumber.open(str(file_path), password=password) as pdf:
                pass
        except PDFPasswordIncorrect:
            exc_msg = "Incorrect password. Please provide the correct PDF password." if password else "This PDF is password-protected. Please re-upload with the document password."
            await db.delete(statement)
            await db.commit()
            try:
                file_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "INVALID_PASSWORD" if password else "PASSWORD_REQUIRED",
                    "message": exc_msg,
                },
            )
        except Exception:
            pass

    await db.commit()
    
    if settings.CELERY_TASK_ALWAYS_EAGER:
        job_id = f"eager-{uuid.uuid4()}"
        await process_statement_job(
            db,
            job_id=job_id,
            statement_id=statement.id,
            file_path=str(file_path),
            bank=bank,
            password=password,
            firm_id=client.firm_id,
        )
    else:
        async_result = process_statement_task.delay(
            statement.id,
            str(file_path),
            bank,
            password,
            client.firm_id,
        )
        update_job_progress(
            async_result.id,
            job_type="parse",
            status="PENDING",
            stage="queued",
            progress=0,
            statement_id=statement.id,
            firm_id=client.firm_id
        )
        
    return statement.id
