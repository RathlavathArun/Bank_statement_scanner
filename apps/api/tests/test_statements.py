import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file.name}"
os.environ["DEBUG"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from auth.dependencies import get_current_user  # noqa: E402
from db.models import User  # noqa: E402
from main import app  # noqa: E402
from statements.parser import StatementParserError  # noqa: E402


async def override_get_current_user():
    return User(
        id="00000000-0000-0000-0000-000000000001",
        email="test@example.com",
        password_hash="test",
        full_name="Test User",
        email_verified=True,
    )


@contextmanager
def authenticated_client():
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_upload_status_and_result_use_statement_id():
    csv_content = (
        "Date,Description,Debit,Credit,Balance\n"
        "2026-05-01,UPI Payment to Vendor,1200,,48800\n"
        "2026-05-03,NEFT Received,,10000,58800\n"
    )

    with authenticated_client() as client:
        upload_response = client.post(
            "/v1/statements/upload",
            data={"bank": "HDFC"},
            files={"file": ("sample.csv", csv_content, "text/csv")},
        )

        assert upload_response.status_code == 200
        upload_body = upload_response.json()
        assert upload_body["success"] is True
        statement = upload_body["data"]
        assert statement["id"]
        assert statement["filename"] == "sample.csv"
        assert statement["file_type"] == "csv"
        assert statement["status"] == "PARSING"

        status_response = client.get(f"/v1/statements/{statement['id']}/status")
        assert status_response.status_code == 200
        assert status_response.json()["data"]["id"] == statement["id"]
        assert status_response.json()["data"]["file_type"] == "csv"
        assert status_response.json()["data"]["status"] == "READY_FOR_REVIEW"

        result_response = client.get(f"/v1/statements/{statement['id']}/result")
        assert result_response.status_code == 200
        result_body = result_response.json()
        assert result_body["success"] is True
        assert result_body["data"]["id"] == statement["id"]
        assert result_body["data"]["transactions"] == [
            {
                "id": result_body["data"]["transactions"][0]["id"],
                "date": "2026-05-01",
                "value_date": None,
                "description": "UPI Payment to Vendor",
                "reference_no": None,
                "debit": "1200.00",
                "credit": None,
                "balance": "48800.00",
            },
            {
                "id": result_body["data"]["transactions"][1]["id"],
                "date": "2026-05-03",
                "value_date": None,
                "description": "NEFT Received",
                "reference_no": None,
                "debit": None,
                "credit": "10000.00",
                "balance": "58800.00",
            },
        ]


def test_unknown_statement_returns_404():
    with authenticated_client() as client:
        response = client.get("/v1/statements/not-a-real-id/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Statement not found"


def test_unsupported_upload_is_saved_as_failed_statement():
    with authenticated_client() as client:
        upload_response = client.post(
            "/v1/statements/upload",
            files={"file": ("notes.txt", "not a statement", "text/plain")},
        )

        assert upload_response.status_code == 200
        statement = upload_response.json()["data"]

        result_response = client.get(f"/v1/statements/{statement['id']}/result")
        assert result_response.status_code == 200
        result = result_response.json()["data"]
        assert result["status"] == "FAILED"
        assert "Unsupported statement format" in result["error"]
        assert result["transactions"] == []


def test_invalid_pdf_upload_is_saved_as_failed_statement():
    with authenticated_client() as client:
        upload_response = client.post(
            "/v1/statements/upload",
            data={"bank": "HDFC"},
            files={"file": ("bad.pdf", b"not actually a pdf", "application/pdf")},
        )

        assert upload_response.status_code == 200
        statement = upload_response.json()["data"]
        assert statement["file_type"] == "pdf"
        status_response = client.get(f"/v1/statements/{statement['id']}/status")
        assert status_response.status_code == 200
        status = status_response.json()["data"]
        assert status["status"] == "FAILED"
        assert "Could not read this PDF" in status["error"]


def test_readable_pdf_parse_warning_still_allows_review(monkeypatch):
    def fake_parse_statement(file_path, bank, password=None):
        raise StatementParserError("PDF uploaded successfully, but no transaction rows matched the current bank template.")

    monkeypatch.setattr("statements.router.parse_statement", fake_parse_statement)

    with authenticated_client() as client:
        upload_response = client.post(
            "/v1/statements/upload",
            data={"bank": "SBI"},
            files={"file": ("statement.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )

        assert upload_response.status_code == 200
        statement = upload_response.json()["data"]
        assert statement["file_type"] == "pdf"
        status_response = client.get(f"/v1/statements/{statement['id']}/status")
        assert status_response.status_code == 200
        status = status_response.json()["data"]
        assert status["status"] == "READY_FOR_REVIEW"
        assert "no transaction rows" in status["error"]


def test_fuzzy_date_parsing_for_ocr():
    from statements.parser import parse_date
    from datetime import date

    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"]

    # Test clean directly parseable date
    assert parse_date("12/10/2026", formats) == date(2026, 10, 12)

    # Test space and letter substitutions in numeric format
    assert parse_date("l2 / O5 / 2O26", formats) == date(2026, 5, 12)
    assert parse_date("3l-O8-2O26", formats) == date(2026, 8, 31)
    assert parse_date("2O26.O5.i2", formats) == date(2026, 5, 12)

    # Test mixed cases and other character mappings
    assert parse_date("o1/o1/2o26", formats) == date(2026, 1, 1)
    assert parse_date("Z5-O5-2O26", formats) == date(2026, 5, 25)  # Z -> 2, O -> 0, o -> 0
    assert parse_date("l5 S 2O26", ["%d %m %Y"]) == date(2026, 5, 15)  # l -> 1, S -> 5, O -> 0

    # Test alphabet-based months (preserves the month word correctly while fixing numbers)
    assert parse_date("l2  oCt  2O26", formats) == date(2026, 10, 12)
    assert parse_date("O1  Jan  2O26", formats) == date(2026, 1, 1)

