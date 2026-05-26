import os
import sys
import tempfile
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file.name}"
os.environ["DEBUG"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


def test_upload_status_and_result_use_statement_id():
    csv_content = (
        "Date,Description,Debit,Credit,Balance\n"
        "2026-05-01,UPI Payment to Vendor,1200,,48800\n"
        "2026-05-03,NEFT Received,,10000,58800\n"
    )

    with TestClient(app) as client:
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
        assert statement["status"] == "READY_FOR_REVIEW"

        status_response = client.get(f"/v1/statements/{statement['id']}/status")
        assert status_response.status_code == 200
        assert status_response.json()["data"]["id"] == statement["id"]
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
    with TestClient(app) as client:
        response = client.get("/v1/statements/not-a-real-id/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Statement not found"


def test_unsupported_upload_is_saved_as_failed_statement():
    with TestClient(app) as client:
        upload_response = client.post(
            "/v1/statements/upload",
            files={"file": ("notes.txt", "not a statement", "text/plain")},
        )

        assert upload_response.status_code == 200
        statement = upload_response.json()["data"]
        assert statement["status"] == "FAILED"
        assert "Unsupported statement format" in statement["error"]

        result_response = client.get(f"/v1/statements/{statement['id']}/result")
        assert result_response.status_code == 200
        assert result_response.json()["data"]["transactions"] == []
