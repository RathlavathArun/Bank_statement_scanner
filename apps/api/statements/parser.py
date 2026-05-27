"""
Statement parsing helpers for the upload API.

The parser intentionally starts narrow: CSV files are parsed with the standard
library, and PDFs use pdfplumber when that optional dependency is installed.
Both paths share the bank template column mapping.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT_DIR / "packages" / "bank-templates"


class StatementParserError(Exception):
    """Raised when a statement cannot be parsed into transaction rows."""


@dataclass(frozen=True)
class ParsedTransaction:
    row_number: int
    txn_date: date
    value_date: date | None
    narration: str
    reference_no: str | None
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None


@dataclass(frozen=True)
class ParsedStatement:
    transactions: list[ParsedTransaction]
    metadata: dict[str, Any]


GENERIC_ALIASES = {
    "date": ("date", "txn date", "transaction date", "transaction dt"),
    "value_date": ("value date", "value dt", "val date"),
    "narration": ("narration", "description", "transaction remarks", "remarks"),
    "reference": ("ref", "reference", "reference no", "chq ref no", "cheque number"),
    "debit": ("debit", "withdrawal", "withdrawal amt", "withdrawal amount"),
    "credit": ("credit", "deposit", "deposit amt", "deposit amount"),
    "balance": ("balance", "closing balance"),
}


def parse_statement(file_path: Path, bank_code: str | None = None) -> ParsedStatement:
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        rows = read_csv_rows(file_path)
        source = "csv"
    elif suffix == ".pdf":
        try:
            import pdfplumber
        except ImportError as exc:
            raise StatementParserError(
                "PDF parsing requires pdfplumber. Install API requirements and retry."
            ) from exc
        rows = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    rows.extend([[cell or "" for cell in row] for row in table])
        source = "pdf"
    else:
        raise StatementParserError(
            f"Unsupported statement format '{suffix or 'unknown'}'. Upload a CSV or text-based PDF."
        )

    # Auto-detect bank code if not provided
    if not bank_code:
        bank_code = auto_detect_bank(rows)

    template = load_bank_template(bank_code)
    return parse_rows(rows, template, source=source)


def auto_detect_bank(rows: list[list[str]]) -> str | None:
    # Flatten the first 30 rows to search for keywords/regex
    header_text = " ".join([cell for row in rows[:30] for cell in row if cell])
    
    for code in ["HDFC", "ICICI", "AXIS", "KOTAK"]:
        template = load_bank_template(code)
        if not template:
            continue
        fingerprint = template.get("fingerprint", {})
        
        # Check keywords
        keywords = fingerprint.get("keywords", [])
        if keywords and all(kw.lower() in header_text.lower() for kw in keywords):
            return code
            
        # Check regex
        regexes = fingerprint.get("regex", [])
        if regexes and any(re.search(rx, header_text, re.IGNORECASE) for rx in regexes):
            return code
            
    return None


def load_bank_template(bank_code: str | None) -> dict[str, Any]:
    if not bank_code:
        return {}

    template_path = TEMPLATE_DIR / f"{bank_code.lower()}.yaml"
    if not template_path.exists():
        return {}

    with template_path.open("r", encoding="utf-8") as template_file:
        return yaml.safe_load(template_file) or {}


def read_csv_rows(file_path: Path) -> list[list[str]]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(4096)
        csv_file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        return [list(row) for row in csv.reader(csv_file, dialect)]


def parse_rows(rows: list[list[str]], template: dict[str, Any], source: str) -> ParsedStatement:
    rows = [normalize_row(row) for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise StatementParserError("No readable rows found in the statement.")

    header_index, column_indexes = detect_columns(rows, template)
    date_formats = get_date_formats(template)

    transactions: list[ParsedTransaction] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=1):
        txn_date_str = get_cell(row, column_indexes.get("date"))
        txn_date = parse_date(txn_date_str, date_formats)
        narration = get_cell(row, column_indexes.get("narration"))

        if txn_date and narration:
            debit = parse_amount(get_cell(row, column_indexes.get("debit")))
            credit = parse_amount(get_cell(row, column_indexes.get("credit")))
            balance = parse_amount(get_cell(row, column_indexes.get("balance")))
            
            txn = ParsedTransaction(
                row_number=row_number,
                txn_date=txn_date,
                value_date=parse_date(get_cell(row, column_indexes.get("value_date")), date_formats),
                narration=narration,
                reference_no=get_cell(row, column_indexes.get("reference")) or None,
                debit=debit,
                credit=credit,
                balance=balance,
            )
            transactions.append(txn)
        elif transactions and narration:
            debit_str = get_cell(row, column_indexes.get("debit"))
            credit_str = get_cell(row, column_indexes.get("credit"))
            if not txn_date_str and not debit_str and not credit_str:
                last_txn = transactions[-1]
                updated_txn = ParsedTransaction(
                    row_number=last_txn.row_number,
                    txn_date=last_txn.txn_date,
                    value_date=last_txn.value_date,
                    narration=f"{last_txn.narration} {narration}".strip(),
                    reference_no=last_txn.reference_no,
                    debit=last_txn.debit,
                    credit=last_txn.credit,
                    balance=last_txn.balance,
                )
                transactions[-1] = updated_txn

    if not transactions:
        raise StatementParserError("No transaction rows matched the selected bank template.")

    return ParsedStatement(
        transactions=transactions,
        metadata={
            "parser": source,
            "template_bank": template.get("bank_code"),
            "row_count": len(transactions),
        },
    )


def normalize_row(row: Iterable[Any]) -> list[str]:
    return [str(cell or "").strip() for cell in row]


def detect_columns(
    rows: list[list[str]], template: dict[str, Any]
) -> tuple[int, dict[str, int | None]]:
    expected_headers = [normalize_header(header) for header in template_headers(template)]
    template_columns = template.get("extraction", {}).get("columns", {})

    for index, row in enumerate(rows[:15]):
        normalized = [normalize_header(cell) for cell in row]
        if expected_headers and header_match_count(normalized, expected_headers) >= 3:
            return index, {key: int(value) for key, value in template_columns.items()}

        generic_columns = detect_generic_columns(normalized)
        required = {"date", "narration"}
        if required.issubset({key for key, value in generic_columns.items() if value is not None}):
            return index, generic_columns

    if template_columns:
        return 0, {key: int(value) for key, value in template_columns.items()}

    raise StatementParserError("Could not find a recognizable statement header row.")


def template_headers(template: dict[str, Any]) -> list[str]:
    extraction = template.get("extraction", {})
    return list(extraction.get("headers") or template.get("headers") or [])


def header_match_count(row_headers: list[str], expected_headers: list[str]) -> int:
    return sum(1 for header in expected_headers if header in row_headers)


def detect_generic_columns(headers: list[str]) -> dict[str, int | None]:
    columns: dict[str, int | None] = {
        "date": None,
        "value_date": None,
        "narration": None,
        "reference": None,
        "debit": None,
        "credit": None,
        "balance": None,
    }

    for index, header in enumerate(headers):
        for key, aliases in GENERIC_ALIASES.items():
            if columns[key] is None and any(alias in header for alias in aliases):
                columns[key] = index

    return columns


def parse_transaction_row(
    row: list[str],
    row_number: int,
    columns: dict[str, int | None],
    date_formats: list[str],
) -> ParsedTransaction:
    txn_date = parse_date(get_cell(row, columns.get("date")), date_formats)
    narration = get_cell(row, columns.get("narration"))

    if not txn_date or not narration:
        raise StatementParserError("Skipping non-transaction row.")

    return ParsedTransaction(
        row_number=row_number,
        txn_date=txn_date,
        value_date=parse_date(get_cell(row, columns.get("value_date")), date_formats),
        narration=narration,
        reference_no=get_cell(row, columns.get("reference")) or None,
        debit=parse_amount(get_cell(row, columns.get("debit"))),
        credit=parse_amount(get_cell(row, columns.get("credit"))),
        balance=parse_amount(get_cell(row, columns.get("balance"))),
    )


def get_cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return row[index].strip()


def get_date_formats(template: dict[str, Any]) -> list[str]:
    configured = template.get("extraction", {}).get("formats", {}).get("date")
    formats = [
        "%d/%m/%y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    return [configured, *formats] if configured else formats


def parse_date(value: str, formats: list[str]) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> Decimal | None:
    cleaned = value.strip()
    if not cleaned or cleaned in {"-", "--"}:
        return None

    is_negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.replace(",", "")
    cleaned = re.sub(r"(?i)\b(cr|dr)\b", "", cleaned)
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)

    if not cleaned:
        return None

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    return -amount if is_negative else amount


def normalize_header(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
