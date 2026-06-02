import csv
import io
import json
from decimal import Decimal

import openpyxl

from statements.exporters import generate_csv, generate_excel, generate_json


TRANSACTIONS = [
    {
        "id": "tx-1",
        "date": "2024-01-01",
        "narration": "UPI SWIGGY",
        "amount": Decimal("350.00"),
        "tx_type": "DEBIT",
        "balance": Decimal("49650.00"),
        "payment_mode": "UPI",
        "counterparty": "Swiggy",
        "ledger_name": "Food Expenses",
        "ocr_confidence": Decimal("0.650"),
        "is_reviewed": True,
    },
    {
        "id": "tx-2",
        "date": "2024-01-02",
        "narration": "Salary Credit",
        "amount": Decimal("50000.00"),
        "tx_type": "CREDIT",
        "balance": Decimal("99650.00"),
        "payment_mode": "NEFT",
        "counterparty": "Employer",
        "ledger_name": "Salary Income",
        "ocr_confidence": Decimal("0.900"),
        "is_reviewed": False,
    },
]

STATEMENT_META = {
    "id": "stmt-1",
    "filename": "statement.csv",
    "bank_id": "hdfc",
}


def test_generate_csv_includes_totals_row():
    content = generate_csv(TRANSACTIONS).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(content)))

    assert rows[0] == [
        "Date",
        "Narration",
        "Debit",
        "Credit",
        "Balance",
        "Payment Mode",
        "Counterparty",
        "Ledger",
        "OCR Confidence",
        "Reviewed",
    ]
    assert rows[-1][0] == "TOTAL"
    assert rows[-1][2] == "350.00"
    assert rows[-1][3] == "50000.00"


def test_generate_json_returns_statement_and_transactions():
    payload = json.loads(generate_json(TRANSACTIONS, STATEMENT_META).decode("utf-8"))

    assert payload["statement"]["id"] == "stmt-1"
    assert payload["statement"]["total_transactions"] == 2
    assert payload["statement"]["total_debit"] == 350.0
    assert payload["transactions"][0]["ledger_name"] == "Food Expenses"


def test_generate_excel_creates_summary_and_transactions_sheets():
    workbook = openpyxl.load_workbook(io.BytesIO(generate_excel(TRANSACTIONS, STATEMENT_META)))

    assert workbook.sheetnames == ["Transactions", "Summary"]
    transactions_sheet = workbook["Transactions"]
    summary_sheet = workbook["Summary"]

    assert transactions_sheet["A1"].value == "Date"
    assert transactions_sheet["C2"].value == 350.0
    assert transactions_sheet["D3"].value == 50000.0
    assert transactions_sheet.freeze_panes == "A2"
    assert summary_sheet["B1"].value == "statement.csv"
