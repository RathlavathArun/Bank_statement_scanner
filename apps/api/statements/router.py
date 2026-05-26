import os
import shutil
import time
from fastapi import APIRouter, UploadFile, File, Form

router = APIRouter(prefix="/v1/statements", tags=["statements"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

statement_status = {}

@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank: str | None = Form(default=None),
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    statement_status[file.filename] = {
        "status": "UPLOADED",
        "uploaded_at": time.time(),
        "bank": bank,
    }

    return {
        "success": True,
        "message": "Statement uploaded successfully",
        "data": {
            "filename": file.filename,
            "bank": bank,
            "status": "UPLOADED",
            "path": file_path,
        },
    }

@router.get("/{filename}/status")
async def get_statement_status(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        return {
            "success": False,
            "message": "Statement not found",
            "data": None,
        }

    record = statement_status.get(filename)

    if not record:
        status = "UPLOADED"
        bank = None
    else:
        elapsed = time.time() - record["uploaded_at"]

        if elapsed < 3:
            status = "UPLOADED"
        elif elapsed < 8:
            status = "PARSING"
        else:
            status = "READY_FOR_REVIEW"

        record["status"] = status
        bank = record["bank"]

    return {
        "success": True,
        "message": "Statement status fetched successfully",
        "data": {
            "filename": filename,
            "status": status,
            "bank": bank,
        },
    }
@router.get("/{filename}/result")
async def get_statement_result(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        return {
            "success": False,
            "message": "Statement not found",
            "data": None,
        }

    return {
        "success": True,
        "message": "Statement parsed successfully",
        "data": {
            "filename": filename,
            "transactions": [
                {
                    "date": "2026-05-01",
                    "description": "UPI Payment to Vendor",
                    "debit": 1200,
                    "credit": 0,
                    "balance": 48800,
                },
                {
                    "date": "2026-05-03",
                    "description": "NEFT Received",
                    "debit": 0,
                    "credit": 10000,
                    "balance": 58800,
                },
            ],
        },
    }