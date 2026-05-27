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
        assert statement["status"] == "UPLOADED"

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
                "confirmed_ledger": None,
                "suggested_ledger": None,
                "confidence": None,
                "is_ignored": False,
                "page_number": None,
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
                "confirmed_ledger": None,
                "suggested_ledger": None,
                "confidence": None,
                "is_ignored": False,
                "page_number": None,
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
        assert statement["status"] == "UPLOADED"
        
        status_res = client.get(f"/v1/statements/{statement['id']}/status")
        assert status_res.status_code == 200
        assert "Unsupported statement format" in status_res.json()["data"]["error"]

        result_response = client.get(f"/v1/statements/{statement['id']}/result")
        assert result_response.status_code == 200
        assert result_response.json()["data"]["transactions"] == []


def test_axis_and_kotak_templates():
    from statements.parser import parse_statement
    
    # Test Axis csv parsing
    axis_csv = (
        "Tran Date,Particulars,Chq No,Amount (Debit),Amount (Credit),Balance\n"
        "2026-05-01,AXIS BANK CHARGES,,100,,49900\n"
        "2026-05-02,SALARY CR,,50000,50000,99900\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(axis_csv.encode("utf-8"))
        f_path = Path(f.name)
        
    try:
        parsed = parse_statement(f_path, "AXIS")
        assert parsed.metadata["template_bank"] == "AXIS"
        assert len(parsed.transactions) == 2
        assert parsed.transactions[0].narration == "AXIS BANK CHARGES"
        assert parsed.transactions[0].debit == 100
        assert parsed.transactions[1].credit == 50000
    finally:
        try:
            f_path.unlink()
        except OSError:
            pass

    # Test Kotak csv parsing
    kotak_csv = (
        "Date,Description,Chq/Ref No.,Amount (Dr),Amount (Cr),Balance\n"
        "2026-05-01,KOTAK INTEREST CR,,,250,50150\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(kotak_csv.encode("utf-8"))
        f_path = Path(f.name)

    try:
        parsed = parse_statement(f_path, "KOTAK")
        assert parsed.metadata["template_bank"] == "KOTAK"
        assert len(parsed.transactions) == 1
        assert parsed.transactions[0].narration == "KOTAK INTEREST CR"
        assert parsed.transactions[0].credit == 250
    finally:
        try:
            f_path.unlink()
        except OSError:
            pass


def test_multiline_narration_merging():
    from statements.parser import parse_statement
    
    # HDFC style multi-line narration
    hdfc_csv = (
        "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "01/05/26,UPI-PAYMENT-TO-MERCHANT,12345,01/05/26,500,,1000\n"
        ",MORE-NARRATION-DETAILS,,,,\n"
        "02/05/26,INTEREST,67890,02/05/26,,50,1050\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(hdfc_csv.encode("utf-8"))
        f_path = Path(f.name)
        
    try:
        parsed = parse_statement(f_path, "HDFC")
        assert len(parsed.transactions) == 2
        assert parsed.transactions[0].narration == "UPI-PAYMENT-TO-MERCHANT MORE-NARRATION-DETAILS"
        assert parsed.transactions[0].debit == 500
        assert parsed.transactions[1].narration == "INTEREST"
    finally:
        try:
            f_path.unlink()
        except OSError:
            pass


def test_transactions_crud_and_bulk_endpoints():
    csv_content = (
        "Date,Description,Debit,Credit,Balance\n"
        "2026-05-01,UPI Swiggy,1200,,48800\n"
        "2026-05-03,Office Rent,25000,,23800\n"
    )

    with TestClient(app) as client:
        # 1. Upload statement
        upload_response = client.post(
            "/v1/statements/upload",
            files={"file": ("sample.csv", csv_content, "text/csv")},
        )
        assert upload_response.status_code == 200
        statement = upload_response.json()["data"]
        statement_id = statement["id"]

        # Wait briefly for background task to complete (since background tasks are executed on response in FastAPI TestClient)
        # Check result
        result_response = client.get(f"/v1/statements/{statement_id}/result")
        assert result_response.status_code == 200
        txns = result_response.json()["data"]["transactions"]
        assert len(txns) == 2
        
        txn_1_id = txns[0]["id"]
        txn_2_id = txns[1]["id"]

        # 2. Get paginated/filtered transactions
        txns_list_response = client.get(f"/v1/statements/{statement_id}/transactions?search=Swiggy")
        assert txns_list_response.status_code == 200
        assert txns_list_response.json()["data"]["total"] == 1
        assert txns_list_response.json()["data"]["transactions"][0]["id"] == txn_1_id

        # 3. Patch single transaction
        patch_response = client.patch(
            f"/v1/statements/{statement_id}/transactions/{txn_1_id}",
            json={"confirmed_ledger": "Staff Welfare"},
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["data"]["confirmed_ledger"] == "Staff Welfare"

        # 4. Bulk update
        bulk_response = client.post(
            f"/v1/statements/{statement_id}/transactions/bulk-update",
            json={
                "ids": [txn_1_id, txn_2_id],
                "updates": {"confirmed_ledger": "Office Expenses"}
            }
        )
        assert bulk_response.status_code == 200
        
        # Verify both updated
        updated_result = client.get(f"/v1/statements/{statement_id}/result")
        assert updated_result.json()["data"]["transactions"][0]["confirmed_ledger"] == "Office Expenses"
        assert updated_result.json()["data"]["transactions"][1]["confirmed_ledger"] == "Office Expenses"


def test_statement_export_and_metadata_endpoints():
    csv_content = (
        "Date,Description,Debit,Credit,Balance\n"
        "2026-05-01,UPI Swiggy,1200,,48800\n"
        "2026-05-03,Office Rent,25000,,23800\n"
    )

    with TestClient(app) as client:
        upload_response = client.post(
            "/v1/statements/upload",
            files={"file": ("export-sample.csv", csv_content, "text/csv")},
        )
        assert upload_response.status_code == 200
        statement_id = upload_response.json()["data"]["id"]

        status_response = client.get(f"/v1/statements/{statement_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["data"]["file_type"] == "csv"

        csv_export = client.get(f"/v1/statements/{statement_id}/export?format=csv")
        assert csv_export.status_code == 200
        assert "attachment; filename=" in csv_export.headers["content-disposition"]
        assert "Description" in csv_export.text

        json_export = client.get(f"/v1/statements/{statement_id}/export?format=json")
        assert json_export.status_code == 200
        assert isinstance(json_export.json(), list)
        assert json_export.json()[0]["description"] == "UPI Swiggy"

        xml_export = client.get(f"/v1/statements/{statement_id}/export?format=tally_xml")
        assert xml_export.status_code == 200
        assert xml_export.text.strip().startswith("<ENVELOPE>")

