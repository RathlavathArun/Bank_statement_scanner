"""
Tests for Excel (.xlsx/.xls) statement parsing — Phase 4.

These tests exercise the Excel branch of ``parse_statement`` which reads
.xlsx files via openpyxl, maps columns using the same bank-template logic
that CSV/PDF already use, and returns ``ParsedStatement`` objects.

Fixtures are pre-generated Excel workbooks in ``tests/fixtures/``.
Run ``python tests/fixtures/generate_fixtures.py`` if they don't exist.
"""
from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

# ── make sure the API package is importable ──────────────────
API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test_placeholder.db")
os.environ.setdefault("DEBUG", "False")

from statements.parser import StatementParserError, parse_statement  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ─── helpers ────────────────────────────────────────────────
def _require_fixture(name: str) -> Path:
    """Return the fixture path or skip the test when it is missing."""
    path = FIXTURE_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} not found — run generate_fixtures.py first")
    return path


# ─── per-bank parsing ──────────────────────────────────────
class TestExcelParser:
    """Verify that each bank's Excel fixture can be parsed correctly."""

    def test_hdfc_xlsx_parsing(self):
        """Parse HDFC format Excel → 5+ transactions."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        assert len(result.transactions) >= 5
        assert result.metadata["parser"] == "excel"

    def test_icici_xlsx_parsing(self):
        """Parse ICICI format Excel → 5+ transactions."""
        path = _require_fixture("icici_sample.xlsx")
        result = parse_statement(path, bank_code="icici")
        assert len(result.transactions) >= 5

    def test_sbi_xlsx_parsing(self):
        """Parse SBI format Excel → 5+ transactions."""
        path = _require_fixture("sbi_sample.xlsx")
        result = parse_statement(path, bank_code="sbi")
        assert len(result.transactions) >= 5

    def test_axis_xlsx_parsing(self):
        """Parse Axis format Excel → 5+ transactions."""
        path = _require_fixture("axis_sample.xlsx")
        result = parse_statement(path, bank_code="axis")
        assert len(result.transactions) >= 5

    def test_kotak_xlsx_parsing(self):
        """Parse Kotak format Excel → 5+ transactions."""
        path = _require_fixture("kotak_sample.xlsx")
        result = parse_statement(path, bank_code="kotak")
        assert len(result.transactions) >= 5


class TestExcelHeaderDetection:
    """Verify that the parser copes with title/junk rows above the real header."""

    def test_header_autodetection_with_offset(self):
        """Parser finds the header row even with 2 title rows above it."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        # The first parsed transaction should have a real narration (not a title)
        assert result.transactions[0].narration
        assert "HDFC BANK" not in result.transactions[0].narration

    def test_excel_without_bank_code_uses_generic_detection(self):
        """Parser should auto-detect columns using generic column aliases."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path)  # no bank_code
        assert len(result.transactions) >= 5


class TestExcelAmounts:
    """Verify that monetary values are parsed as Decimal, not float."""

    def test_amounts_parsed_as_decimal(self):
        """Debit/credit amounts should be Decimal instances."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        for txn in result.transactions:
            if txn.debit is not None:
                assert isinstance(txn.debit, Decimal), (
                    f"Expected Decimal for debit, got {type(txn.debit)}"
                )
            if txn.credit is not None:
                assert isinstance(txn.credit, Decimal), (
                    f"Expected Decimal for credit, got {type(txn.credit)}"
                )

    def test_balance_parsed_as_decimal(self):
        """Balance should also be Decimal."""
        path = _require_fixture("sbi_sample.xlsx")
        result = parse_statement(path, bank_code="sbi")
        for txn in result.transactions:
            if txn.balance is not None:
                assert isinstance(txn.balance, Decimal)

    def test_debit_credit_separation(self):
        """Transactions should have debit OR credit, not both."""
        path = _require_fixture("icici_sample.xlsx")
        result = parse_statement(path, bank_code="icici")
        for txn in result.transactions:
            # A given transaction shouldn't have both debit and credit non-None
            assert not (txn.debit and txn.credit), (
                f"Row {txn.row_number} has both debit={txn.debit} and credit={txn.credit}"
            )


class TestExcelDates:
    """Verify date parsing from Excel cells (may be native datetime or string)."""

    def test_dates_are_date_objects(self):
        """txn_date should be a Python date, not a string."""
        from datetime import date as Date

        path = _require_fixture("axis_sample.xlsx")
        result = parse_statement(path, bank_code="axis")
        for txn in result.transactions:
            assert isinstance(txn.txn_date, Date), (
                f"Expected date, got {type(txn.txn_date)} = {txn.txn_date}"
            )


class TestExcelMetadata:
    """Verify the ParsedStatement metadata dict for Excel sources."""

    def test_parser_metadata_set(self):
        """metadata['parser'] should be 'excel'."""
        path = _require_fixture("kotak_sample.xlsx")
        result = parse_statement(path, bank_code="kotak")
        assert result.metadata.get("parser") == "excel"

    def test_row_count_in_metadata(self):
        """metadata['row_count'] should match len(transactions)."""
        path = _require_fixture("sbi_sample.xlsx")
        result = parse_statement(path, bank_code="sbi")
        assert result.metadata["row_count"] == len(result.transactions)

    def test_template_bank_in_metadata(self):
        """When a bank_code is provided, metadata should record the template bank."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        # The HDFC template has bank_code: "HDFC"
        assert result.metadata.get("template_bank") is not None


class TestExcelErrorHandling:
    """Error-path tests for the Excel parser branch."""

    def test_unsupported_format_raises_error(self):
        """Unsupported file extension (.docx) should raise StatementParserError."""
        with pytest.raises(StatementParserError, match="Unsupported"):
            parse_statement(Path("foo.docx"))

    def test_empty_excel_raises_error(self):
        """Excel file with no data rows should raise StatementParserError."""
        path = _require_fixture("empty_sample.xlsx")
        with pytest.raises(StatementParserError):
            parse_statement(path)

    def test_nonexistent_file_raises_error(self):
        """Parsing a file that doesn't exist should raise an error."""
        with pytest.raises((StatementParserError, FileNotFoundError, OSError)):
            parse_statement(Path("/tmp/does_not_exist_xyz.xlsx"), bank_code="hdfc")

    def test_corrupt_xlsx_raises_error(self):
        """A file with .xlsx extension but non-Excel content should error."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"this is not an excel file at all")
            f.flush()
            tmp_path = Path(f.name)

        try:
            with pytest.raises((StatementParserError, Exception)):
                parse_statement(tmp_path, bank_code="hdfc")
        finally:
            tmp_path.unlink(missing_ok=True)


class TestExcelTransactionContent:
    """Spot-check that parsed transaction fields match fixture data."""

    def test_hdfc_first_transaction_narration(self):
        """HDFC first transaction narration should contain 'SWIGGY'."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        assert "SWIGGY" in result.transactions[0].narration.upper()

    def test_sbi_has_reference_numbers(self):
        """SBI fixture transactions should have reference numbers."""
        path = _require_fixture("sbi_sample.xlsx")
        result = parse_statement(path, bank_code="sbi")
        refs = [txn.reference_no for txn in result.transactions if txn.reference_no]
        assert len(refs) >= 3, "Expected at least 3 transactions with reference numbers"

    def test_icici_has_value_dates(self):
        """ICICI fixture should populate value_date on transactions."""
        path = _require_fixture("icici_sample.xlsx")
        result = parse_statement(path, bank_code="icici")
        value_dates = [txn.value_date for txn in result.transactions if txn.value_date]
        assert len(value_dates) >= 3, "Expected at least 3 transactions with value dates"

    def test_totals_row_excluded(self):
        """The totals row at the bottom should NOT appear as a transaction."""
        path = _require_fixture("hdfc_sample.xlsx")
        result = parse_statement(path, bank_code="hdfc")
        narrations = [txn.narration.lower() for txn in result.transactions]
        assert not any("total" in n for n in narrations), (
            "Totals row should have been excluded from transactions"
        )
