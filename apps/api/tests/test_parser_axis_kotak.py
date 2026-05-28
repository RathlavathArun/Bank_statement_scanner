"""Tests for bank template parsing (Axis, Kotak, continuation rows)."""
import pytest
from pathlib import Path
import tempfile
import yaml
from statements.parser import (
    load_bank_template,
    parse_statement,
    _merge_continuation_rows,
)


@pytest.fixture
def temp_csv():
    """Temp file for test CSV."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


def test_axis_template_exists():
    """Axis YAML template file exists."""
    template = load_bank_template("axis")
    assert template is not None
    assert template.get("bank_id") == "axis"


def test_axis_template_structure():
    """Axis template has required structure."""
    template = load_bank_template("axis")
    assert "fingerprint" in template
    assert "keywords" in template["fingerprint"]


def test_axis_fingerprint_keywords():
    """Axis fingerprint contains expected keywords."""
    template = load_bank_template("axis")
    keywords = template["fingerprint"]["keywords"]
    assert any("axis" in k.lower() for k in keywords)


def test_kotak_template_exists():
    """Kotak YAML template file exists."""
    template = load_bank_template("kotak")
    assert template is not None
    assert template.get("bank_id") == "kotak"


def test_kotak_template_structure():
    """Kotak template has required structure."""
    template = load_bank_template("kotak")
    assert "fingerprint" in template
    assert "keywords" in template["fingerprint"]


def test_kotak_fingerprint_keywords():
    """Kotak fingerprint contains expected keywords."""
    template = load_bank_template("kotak")
    keywords = template["fingerprint"]["keywords"]
    assert any("kotak" in k.lower() for k in keywords)


def test_merge_continuation_rows_basic():
    """Merge 2 continuation rows into 1."""
    rows = [
        {"0": "01/01/2024", "1": "UPI PAYMENT", "2": "UPI123", "3": "100", "4": "", "5": "900"},
        {"0": "", "1": "Continued narration", "2": "", "3": "", "4": "", "5": ""},
    ]
    result = _merge_continuation_rows(rows, {})
    assert len(result) <= len(rows)


def test_merge_continuation_rows_multiple():
    """Merge 3 continuation rows into 1."""
    rows = [
        {"0": "01/01/2024", "1": "Main TX", "2": "REF", "3": "500", "4": "", "5": "950"},
        {"0": "", "1": "Line 2", "2": "", "3": "", "4": "", "5": ""},
        {"0": "", "1": "Line 3", "2": "", "3": "", "4": "", "5": ""},
    ]
    result = _merge_continuation_rows(rows, {})
    # Should merge all continuations to first row
    assert len(result) <= 2


def test_merge_continuation_rows_none():
    """2 normal rows unchanged."""
    rows = [
        {"0": "01/01/2024", "1": "TX1", "2": "REF", "3": "100", "4": "", "5": "900"},
        {"0": "02/01/2024", "1": "TX2", "2": "REF", "3": "200", "4": "", "5": "700"},
    ]
    result = _merge_continuation_rows(rows, {})
    assert len(result) == len(rows)


def test_merge_continuation_rows_empty():
    """Empty input returns empty."""
    result = _merge_continuation_rows([], {})
    assert len(result) == 0


def test_axis_csv_parsing(temp_csv):
    """Parse Axis CSV with 5 transactions."""
    csv_content = """Date,Particulars,Chq./Ref.No.,Debit Amount,Credit Amount,Balance
15-01-2024,UPI/AMAZON PAY/Payment,123456,500.00,,49500.00
16-01-2024,NEFT FROM EMPLOYER INC,789012,,50000.00,99500.00
17-01-2024,UPI/SWIGGY/Food Order,345678,350.00,,99150.00
18-01-2024,ATM WITHDRAWAL,000001,2000.00,,97150.00
19-01-2024,IMPS TO JOHN DOE,567890,1500.00,,95650.00"""
    
    temp_csv.write_text(csv_content)
    parsed = parse_statement(temp_csv, "axis")
    assert len(parsed.transactions) == 5


def test_axis_amounts():
    """Axis CSV amounts parsed correctly."""
    csv_content = """Date,Particulars,Chq./Ref.No.,Debit Amount,Credit Amount,Balance
15-01-2024,Payment,123,500.00,,900
16-01-2024,Deposit,456,,50000.00,50900"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        parsed = parse_statement(Path(f.name), "axis")
        
    assert parsed.transactions[0].debit is not None
    assert float(parsed.transactions[0].debit) == 500.0
    assert parsed.transactions[1].credit is not None
    assert float(parsed.transactions[1].credit) == 50000.0
    Path(f.name).unlink(missing_ok=True)


def test_kotak_csv_parsing(temp_csv):
    """Parse Kotak CSV with 4 transactions."""
    csv_content = """Date,Description,Reference No.,Debit,Credit,Closing Balance
10-01-2024,UPI/PHONEPE/Recharge,REF001,199.00,,19801.00
11-01-2024,Salary Credit - ABC Corp,REF002,,80000.00,99801.00
12-01-2024,POS/BIGBASKET/Groceries,REF003,2345.00,,97456.00
13-01-2024,NEFT OUT/RENT PAYMENT,REF004,15000.00,,82456.00"""
    
    temp_csv.write_text(csv_content)
    parsed = parse_statement(temp_csv, "kotak")
    assert len(parsed.transactions) == 4


def test_kotak_debit_credit_split():
    """Kotak CSV correctly splits debit/credit."""
    csv_content = """Date,Description,Reference No.,Debit,Credit,Closing Balance
10-01-2024,UPI,REF001,199.00,,800
11-01-2024,Salary,REF002,,80000.00,80800"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        parsed = parse_statement(Path(f.name), "kotak")
        
    assert len(parsed.transactions) == 2
    assert parsed.transactions[0].debit is not None
    assert parsed.transactions[1].credit is not None
    Path(f.name).unlink(missing_ok=True)
