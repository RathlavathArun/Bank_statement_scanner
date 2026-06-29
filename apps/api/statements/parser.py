"""
Statement parsing helpers for the upload API.

The parser intentionally starts narrow: CSV files are parsed with the standard
library, and PDFs use pdfplumber when that optional dependency is installed.
Excel files (.xlsx/.xls) are handled via openpyxl and xlrd respectively.
All tabular paths share the bank template column mapping.
"""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

logger = logging.getLogger(__name__)


if Path("/app/bank-templates").exists():
    TEMPLATE_DIR = Path("/app/bank-templates")
else:
    # Safely handle local dev vs Docker paths
    _current_dir = Path(__file__).resolve().parent
    try:
        TEMPLATE_DIR = _current_dir.parents[2] / "packages" / "bank-templates"
    except IndexError:
        TEMPLATE_DIR = _current_dir.parent / "bank-templates"


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
    ocr_confidence: float | None = None


@dataclass(frozen=True)
class ParsedStatement:
    transactions: list[ParsedTransaction]
    metadata: dict[str, Any]


class PDFReadError(StatementParserError):
    """Raised when the uploaded PDF cannot be opened as a PDF at all."""


class PasswordProtectedError(StatementParserError):
    """Raised when the PDF is password-protected and no/wrong password was supplied."""


GENERIC_ALIASES = {
    "date": ("date", "txn date", "transaction date", "transaction dt"),
    "value_date": ("value date", "value dt", "val date"),
    "narration": ("narration", "description", "transaction remarks", "remarks", "particulars"),
    "reference": ("ref", "reference", "reference no", "chq ref no", "cheque number", "chq num", "chq no"),
    "debit": ("debit", "withdrawal", "withdrawal amt", "withdrawal amount"),
    "credit": ("credit", "deposit", "deposit amt", "deposit amount"),
    "balance": ("balance", "closing balance"),
}

TEXT_TRANSACTION_RE = re.compile(
    r"(?P<date>\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b)"
    r"\s+(?P<body>.+?)\s+"
    r"(?P<amount>-?\(?\d[\d,]*(?:\.\d{1,2})?\)?)"
    r"(?:\s+(?P<balance>-?\(?\d[\d,]*(?:\.\d{1,2})?\)?))?$"
)


def parse_statement(
    file_path: Path,
    bank_code: str | None = None,
    password: str | None = None,
    on_ocr_progress: Callable[[int, int], None] | None = None,
) -> ParsedStatement:
    suffix = file_path.suffix.lower()
    template = load_bank_template(bank_code)

    if suffix == ".csv":
        return parse_rows(read_csv_rows(file_path), template, source="csv")

    if suffix == ".pdf":
        return parse_pdf(file_path, template, password=password, on_ocr_progress=on_ocr_progress)

    if suffix in (".xlsx", ".xls"):
        return parse_rows(parse_excel(file_path), template, source="excel")

    raise StatementParserError(
        f"Unsupported statement format '{suffix or 'unknown'}'. Upload a CSV, PDF, or Excel file."
    )


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


def parse_excel(file_path: Path) -> list[list[str]]:
    """Read an Excel workbook (.xlsx or legacy .xls) and return all rows as strings.

    The function iterates through every sheet and appends all non-empty rows.
    Header auto-detection is handled downstream by ``detect_columns()`` which
    already scans the first 15 rows.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise StatementParserError(
                "Excel (.xlsx) parsing requires openpyxl. Install API requirements and retry."
            ) from exc

        wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        rows: list[list[str]] = []
        try:
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    str_row = [str(cell) if cell is not None else "" for cell in row]
                    if any(cell.strip() for cell in str_row):
                        rows.append(str_row)
        finally:
            wb.close()

        if not rows:
            raise StatementParserError("The uploaded Excel file contains no data rows.")
        return rows

    if suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise StatementParserError(
                "Legacy Excel (.xls) parsing requires xlrd. Install API requirements and retry."
            ) from exc

        wb = xlrd.open_workbook(str(file_path))
        rows = []
        for sheet_idx in range(wb.nsheets):
            ws = wb.sheet_by_index(sheet_idx)
            for row_idx in range(ws.nrows):
                str_row = [str(ws.cell_value(row_idx, col)) for col in range(ws.ncols)]
                if any(cell.strip() for cell in str_row):
                    rows.append(str_row)

        if not rows:
            raise StatementParserError("The uploaded Excel file contains no data rows.")
        return rows

    raise StatementParserError(f"Unsupported Excel format: {suffix}")


def parse_pdf(
    file_path: Path,
    template: dict[str, Any],
    password: str | None = None,
    on_ocr_progress: Callable[[int, int], None] | None = None,
) -> ParsedStatement:
    try:
        import pdfplumber
    except ImportError as exc:
        raise StatementParserError(
            "PDF parsing requires pdfplumber. Install API requirements and retry."
        ) from exc

    from pdfminer.pdfdocument import PDFPasswordIncorrect

    rows: list[list[str]] = []
    text_pages: list[str] = []
    try:
        with pdfplumber.open(str(file_path), password=password) as pdf:
            for page in pdf.pages:
                text_pages.append(page.extract_text() or "")
                for table in page.extract_tables() or []:
                    rows.extend([[cell or "" for cell in row] for row in table])
    except PDFPasswordIncorrect:
        if password:
            raise PasswordProtectedError(
                "Incorrect password. Please provide the correct PDF password."
            )
        raise PasswordProtectedError(
            "This PDF is password-protected. Please re-upload with the document password."
        )
    except Exception as exc:
        raise PDFReadError(
            "Could not read this PDF. Please upload a valid PDF bank statement."
        ) from exc

    if rows:
        try:
            return parse_rows(rows, template, source="pdf")
        except StatementParserError:
            pass

    text = "\n".join(text_pages)
    if not text.strip():
        # ── OCR fallback for scanned / image-only PDFs ──────────
        return _ocr_fallback(file_path, template, on_ocr_progress=on_ocr_progress)

    text_transactions = parse_text_transactions(text, template)
    if text_transactions:
        return ParsedStatement(
            transactions=text_transactions,
            metadata={
                "parser": "pdf_text",
                "template_bank": template.get("bank_code"),
                "row_count": len(text_transactions),
            },
        )

    # Last resort – try OCR in case the text was just page headers / footers
    try:
        return _ocr_fallback(file_path, template, on_ocr_progress=on_ocr_progress)
    except Exception:
        raise StatementParserError(
            "PDF uploaded successfully, but no transaction rows matched the current bank template."
        )


def _auto_detect_ocr_columns(
    rows: list[list[str]],
    date_formats: list[str],
) -> dict[str, int | None]:
    """Auto-detect column roles from OCR output by scanning cell content patterns.

    Scans the first 20 data rows and scores each column index based on:
      - Date patterns → date column
      - Numeric/amount patterns → debit, credit, balance columns
      - Long text without amounts → narration column

    Returns a dict mapping role names to column indexes.
    """
    if not rows:
        return {}

    # Determine max column count
    max_cols = max(len(row) for row in rows)
    if max_cols < 2:
        return {}

    # Score each column
    date_scores: list[int] = [0] * max_cols
    amount_scores: list[int] = [0] * max_cols
    text_lengths: list[int] = [0] * max_cols
    serial_scores: list[int] = [0] * max_cols

    # Scan up to 20 rows (skip the first row — likely header)
    sample_rows = rows[1:21] if len(rows) > 1 else rows[:20]

    date_pattern = re.compile(
        r"^\s*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s*$|"
        r"^\s*\d{4}-\d{1,2}-\d{1,2}\s*$|"
        r"^\s*\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4}\s*$",
        re.IGNORECASE,
    )
    amount_pattern = re.compile(r"^\s*-?\(?[\d,]+(?:\.\d{1,2})?\)?\s*(?:Cr|Dr)?\s*$", re.IGNORECASE)
    serial_pattern = re.compile(r"^\s*\d{1,3}\s*$")

    for row in sample_rows:
        for col_idx, cell in enumerate(row):
            cell = cell.strip()
            if not cell:
                continue

            if col_idx < max_cols:
                if date_pattern.match(cell):
                    date_scores[col_idx] += 1
                if amount_pattern.match(cell):
                    amount_scores[col_idx] += 1
                if serial_pattern.match(cell) and col_idx == 0:
                    serial_scores[col_idx] += 1
                # Track text length for narration detection
                if not amount_pattern.match(cell) and not date_pattern.match(cell):
                    text_lengths[col_idx] += len(cell)

    # Assign column roles
    result: dict[str, int | None] = {
        "date": None,
        "narration": None,
        "debit": None,
        "credit": None,
        "balance": None,
    }

    # Date: column with the highest date score
    if max(date_scores) > 0:
        result["date"] = date_scores.index(max(date_scores))

    # Amount columns: columns with highest amount scores (up to 3)
    amount_candidates = [
        (col_idx, score) for col_idx, score in enumerate(amount_scores)
        if score > 0 and col_idx != result["date"]
    ]
    amount_candidates.sort(key=lambda x: x[0])  # sort by column position

    if len(amount_candidates) >= 3:
        # Typical layout: withdrawal, deposit, balance (in order)
        result["debit"] = amount_candidates[-3][0]
        result["credit"] = amount_candidates[-2][0]
        result["balance"] = amount_candidates[-1][0]
    elif len(amount_candidates) == 2:
        result["debit"] = amount_candidates[0][0]
        result["credit"] = amount_candidates[1][0]
    elif len(amount_candidates) == 1:
        result["debit"] = amount_candidates[0][0]

    # Narration: column with the longest total text that isn't date or amount
    used_cols = {v for v in result.values() if v is not None}
    narration_candidates = [
        (col_idx, length) for col_idx, length in enumerate(text_lengths)
        if col_idx not in used_cols and length > 0
    ]
    if narration_candidates:
        narration_candidates.sort(key=lambda x: x[1], reverse=True)
        result["narration"] = narration_candidates[0][0]

    return result


def _ocr_fallback(
    file_path: Path,
    template: dict[str, Any],
    on_ocr_progress: Callable[[int, int], None] | None = None,
) -> ParsedStatement:
    """Run OCR on a scanned PDF and convert the result to a ``ParsedStatement``.

    Steps:
      1. Call ``process_scanned_pdf`` from the OCR worker module.
      2. Convert ``OCRRow`` objects into plain ``list[list[str]]`` rows.
      3. Try ``parse_rows()`` with template column detection.
      4. If that fails, build ``ParsedTransaction`` objects directly from OCR cells,
         preserving per-row confidence scores.
    """
    from statements.ocr_worker import process_scanned_pdf

    try:
        ocr_result = process_scanned_pdf(file_path, on_progress=on_ocr_progress)
    except RuntimeError as exc:
        raise StatementParserError(str(exc)) from exc

    if not ocr_result.rows:
        raise StatementParserError(
            "OCR completed but found no text rows. The document may be blank or heavily degraded."
        )

    # Convert OCR rows to plain string rows for the normal pipeline
    plain_rows: list[list[str]] = [[cell.text for cell in row.cells] for row in ocr_result.rows]
    confidence_by_row: list[float] = [row.row_confidence for row in ocr_result.rows]
    page_by_row: list[int] = [row.page_number for row in ocr_result.rows]

    try:
        parsed = parse_rows(plain_rows, template, source="ocr")
    except StatementParserError:
        # Build transactions using auto-detected column positions
        date_formats = get_date_formats(template)
        col_map = _auto_detect_ocr_columns(plain_rows, date_formats)
        logger.info("OCR auto-detected columns: %s", col_map)

        transactions: list[ParsedTransaction] = []
        for idx, row in enumerate(ocr_result.rows):
            cells = [cell.text for cell in row.cells]
            if len(cells) < 2:
                continue

            date_col = col_map.get("date")
            txn_date = parse_date(cells[date_col], date_formats) if date_col is not None and date_col < len(cells) else None
            if not txn_date:
                # Try all cells for a date (handles column misdetection)
                for ci, cell_text in enumerate(cells):
                    txn_date = parse_date(cell_text, date_formats)
                    if txn_date:
                        break
            if not txn_date:
                continue

            narr_col = col_map.get("narration")
            narration = cells[narr_col] if narr_col is not None and narr_col < len(cells) else ""
            if not narration:
                # Fall back: use the longest text cell that isn't a date or number
                for ci, cell_text in enumerate(cells):
                    if ci == date_col:
                        continue
                    if cell_text and not parse_amount(cell_text) and len(cell_text) > len(narration):
                        narration = cell_text

            debit_col = col_map.get("debit")
            credit_col = col_map.get("credit")
            balance_col = col_map.get("balance")

            debit = parse_amount(cells[debit_col]) if debit_col is not None and debit_col < len(cells) else None
            credit = parse_amount(cells[credit_col]) if credit_col is not None and credit_col < len(cells) else None
            balance = parse_amount(cells[balance_col]) if balance_col is not None and balance_col < len(cells) else None

            transactions.append(
                ParsedTransaction(
                    row_number=len(transactions) + 1,
                    txn_date=txn_date,
                    value_date=None,
                    narration=narration,
                    reference_no=None,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                    ocr_confidence=row.row_confidence,
                )
            )
        if not transactions:
            raise StatementParserError("OCR found text but no valid transaction rows could be extracted.")

        return ParsedStatement(
            transactions=transactions,
            metadata={
                "parser": "ocr",
                "ocr_engine": ocr_result.engine_used,
                "pages_processed": ocr_result.pages_processed,
                "template_bank": template.get("bank_code"),
                "row_count": len(transactions),
            },
        )


    # Augment successfully-parsed transactions with OCR confidence data.
    # ``parse_rows`` detected a header row; data rows follow it.  We match
    # them back to OCR rows using the header offset detected by parse_rows.
    augmented: list[ParsedTransaction] = []
    header_offset = 0
    try:
        header_offset, _ = detect_columns(plain_rows, template)
    except StatementParserError:
        pass
    data_start = header_offset + 1

    for txn in parsed.transactions:
        ocr_idx = data_start + txn.row_number - 1
        ocr_conf = confidence_by_row[ocr_idx] if ocr_idx < len(confidence_by_row) else None
        augmented.append(
            ParsedTransaction(
                row_number=txn.row_number,
                txn_date=txn.txn_date,
                value_date=txn.value_date,
                narration=txn.narration,
                reference_no=txn.reference_no,
                debit=txn.debit,
                credit=txn.credit,
                balance=txn.balance,
                ocr_confidence=ocr_conf,
            )
        )

    return ParsedStatement(
        transactions=augmented,
        metadata={
            **parsed.metadata,
            "parser": "ocr",
            "ocr_engine": ocr_result.engine_used,
            "pages_processed": ocr_result.pages_processed,
        },
    )


def parse_text_transactions(text: str, template: dict[str, Any]) -> list[ParsedTransaction]:
    date_formats = get_date_formats(template)
    transactions: list[ParsedTransaction] = []
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        match = TEXT_TRANSACTION_RE.search(cleaned)
        if not match:
            continue

        txn_date = parse_date(match.group("date"), date_formats)
        if not txn_date:
            continue

        body = match.group("body").strip()
        amount = parse_amount(match.group("amount"))
        balance = parse_amount(match.group("balance") or "")
        if amount is None:
            continue

        is_credit = bool(re.search(r"\b(cr|credit|received|deposit|refund|salary)\b", body, re.I))
        is_debit = bool(re.search(r"\b(dr|debit|paid|payment|withdrawal|purchase|to)\b", body, re.I))
        credit = amount if is_credit and not is_debit else None
        debit = amount if credit is None else None

        transactions.append(
            ParsedTransaction(
                row_number=len(transactions) + 1,
                txn_date=txn_date,
                value_date=None,
                narration=body,
                reference_no=None,
                debit=debit,
                credit=credit,
                balance=balance,
            )
        )

    return transactions


def parse_rows(rows: list[list[str]], template: dict[str, Any], source: str) -> ParsedStatement:
    rows = [normalize_row(row) for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise StatementParserError("No readable rows found in the statement.")

    header_index, column_indexes = detect_columns(rows, template)
    header = rows[header_index]
    data_rows = rows[header_index + 1 :]
    rows_as_dicts = [
        {header[index] if index < len(header) else str(index): cell for index, cell in enumerate(row)}
        for row in data_rows
    ]
    merged_dicts = _merge_continuation_rows(rows_as_dicts)
    rows = rows[: header_index + 1] + [
        [row.get(header[index] if index < len(header) else str(index), "") for index in range(len(header))]
        for row in merged_dicts
    ]
    date_formats = get_date_formats(template)

    transactions: list[ParsedTransaction] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=1):
        try:
            txn = parse_transaction_row(row, row_number, column_indexes, date_formats)
        except StatementParserError:
            continue
        transactions.append(txn)

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


def _merge_continuation_rows(
    rows: list[dict[str, Any]],
    template: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    Merge continuation rows (rows with narration but empty amounts/dates) 
    into the previous transaction row.
    
    A continuation row is detected by:
    - Having narration text but empty/NaN in date, debit, credit, balance columns
    
    All such rows are merged into the previous row and dropped from the list.
    """
    def clean(value: Any) -> str:
        text = str(value or "").strip()
        return "" if text.lower() in {"nan", "none", "null"} else text

    def matching_keys(patterns: tuple[str, ...]) -> list[str]:
        keys: list[str] = []
        for key in rows[0].keys():
            normalized = normalize_header(str(key))
            if any(pattern in normalized for pattern in patterns):
                keys.append(key)
        return keys

    if not rows:
        return []

    narration_keys = matching_keys(("narration", "particular", "description", "remark"))
    date_keys = matching_keys(("date",))
    amount_keys = matching_keys(("debit", "credit", "withdrawal", "deposit", "amount", "dr", "cr"))
    balance_keys = matching_keys(("balance", "bal"))

    if not narration_keys:
        narration_keys = [list(rows[0].keys())[1]] if len(rows[0]) > 1 else [list(rows[0].keys())[0]]
    if not date_keys and all(str(key).isdigit() for key in rows[0].keys()):
        date_keys = [list(rows[0].keys())[0]]
    if not amount_keys and all(str(key).isdigit() for key in rows[0].keys()) and len(rows[0]) >= 5:
        keys = list(rows[0].keys())
        amount_keys = [keys[3], keys[4]]
    if not balance_keys and all(str(key).isdigit() for key in rows[0].keys()) and len(rows[0]) >= 6:
        balance_keys = [list(rows[0].keys())[5]]

    merged: list[dict[str, str]] = []
    for row in rows:
        normalized_row = {str(key): clean(value) for key, value in row.items()}
        has_narration = any(clean(row.get(key)) for key in narration_keys)
        date_empty = all(not clean(row.get(key)) for key in date_keys)
        amounts_empty = all(not clean(row.get(key)) for key in amount_keys)
        balance_empty = all(not clean(row.get(key)) for key in balance_keys)
        is_continuation = has_narration and date_empty and amounts_empty and balance_empty

        if merged and is_continuation:
            prev_row = merged[-1]
            for key in narration_keys:
                curr_val = clean(row.get(key))
                if curr_val:
                    prev_row[str(key)] = " ".join(part for part in [prev_row.get(str(key), ""), curr_val] if part)
        else:
            merged.append(normalized_row)

    return merged


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

    # First attempt: Try parsing directly (fast path for correct dates)
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    # Second attempt: OCR typo correction and cleaning
    # Remove spaces around typical separators like /, -, .
    cleaned_ocr = re.sub(r'\s*([/\-\.])\s*', r'\1', cleaned)

    for fmt in formats:
        candidate = cleaned_ocr
        has_alpha_format = any(char in fmt for char in ('%b', '%B', '%a', '%A'))

        if not has_alpha_format:
            # Numeric format: check if format expects spaces
            if ' ' in fmt:
                candidate = re.sub(r'\s+', ' ', candidate)
            else:
                candidate = re.sub(r'\s+', '', candidate)
            # Standardize separators depending on format expectation
            if '/' in fmt:
                candidate = candidate.replace('-', '/').replace('.', '/')
            elif '-' in fmt:
                candidate = candidate.replace('/', '-').replace('.', '-')
            elif '.' in fmt:
                candidate = candidate.replace('/', '.').replace('-', '.')

            # Correct OCR letter-to-digit substitutions
            candidate = (
                candidate.replace('O', '0')
                .replace('o', '0')
                .replace('I', '1')
                .replace('l', '1')
                .replace('i', '1')
                .replace('S', '5')
                .replace('s', '5')
                .replace('Z', '2')
                .replace('z', '2')
            )
        else:
            # Word-based month format: keep single spaces
            candidate = re.sub(r'\s+', ' ', candidate)
            words = candidate.split()
            cleaned_words = []
            for word in words:
                # Replace typos in words that are otherwise meant to be digits/separators
                if re.match(r'^[0-9OolIiSsZz/\-\.]+$', word):
                    word = (
                        word.replace('O', '0')
                        .replace('o', '0')
                        .replace('I', '1')
                        .replace('l', '1')
                        .replace('i', '1')
                        .replace('S', '5')
                        .replace('s', '5')
                        .replace('Z', '2')
                        .replace('z', '2')
                    )
                    # Standardize separators in these numeric blocks
                    if '/' in fmt:
                        word = word.replace('-', '/').replace('.', '/')
                    elif '-' in fmt:
                        word = word.replace('/', '-').replace('.', '-')
                    elif '.' in fmt:
                        word = word.replace('/', '.').replace('-', '.')
                cleaned_words.append(word)
            candidate = " ".join(cleaned_words)

        try:
            return datetime.strptime(candidate, fmt).date()
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
