"""Phase 6 bank template regression coverage and failure alert helpers."""
from __future__ import annotations

import csv
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Statement
from statements.parser import StatementParserError, load_bank_template, parse_statement


if Path("/app/bank-templates").exists():
    TEMPLATE_DIR = Path("/app/bank-templates")
else:
    # Safely handle local dev vs Docker paths
    _current_dir = Path(__file__).resolve().parent
    try:
        TEMPLATE_DIR = _current_dir.parents[2] / "packages" / "bank-templates"
    except IndexError:
        TEMPLATE_DIR = _current_dir.parent / "bank-templates"
REGRESSION_MANIFEST = TEMPLATE_DIR / "regression_manifest.yaml"
FAILURE_STATUSES = {"FAILED", "PARSE_ERROR"}
SUCCESS_STATUSES = {"READY_FOR_REVIEW", "REVIEWED", "EXPORTED"}


@dataclass(frozen=True)
class RegressionCaseResult:
    bank_code: str
    passed: bool
    expected_transactions: int
    actual_transactions: int
    error: str | None = None


def load_regression_manifest() -> dict[str, Any]:
    if not REGRESSION_MANIFEST.exists():
        return {
            "covered_banks": [],
            "failure_alert_threshold": 0.05,
            "minimum_samples_for_alert": 20,
        }

    with REGRESSION_MANIFEST.open("r", encoding="utf-8") as manifest_file:
        return yaml.safe_load(manifest_file) or {}


def list_template_codes() -> list[str]:
    return sorted(path.stem for path in TEMPLATE_DIR.glob("*.yaml") if path.name != REGRESSION_MANIFEST.name)


def get_coverage_report() -> dict[str, Any]:
    templates = set(list_template_codes())
    manifest = load_regression_manifest()
    covered = {str(code).lower() for code in manifest.get("covered_banks", [])}
    covered_existing = sorted(templates & covered)
    missing = sorted(templates - covered)
    stale = sorted(covered - templates)
    total = len(templates)

    return {
        "total_templates": total,
        "covered_templates": len(covered_existing),
        "coverage_percent": round((len(covered_existing) / total * 100) if total else 0, 2),
        "covered_banks": covered_existing,
        "missing_banks": missing,
        "stale_manifest_banks": stale,
        "is_complete": bool(total) and not missing and not stale,
    }


def build_regression_rows(template: dict[str, Any]) -> list[list[str]]:
    headers = list(template.get("extraction", {}).get("headers", []))
    columns = template.get("extraction", {}).get("columns", {})
    if not headers or not columns:
        raise StatementParserError("Template has no headers or column mappings.")

    max_index = max(int(index) for index in columns.values())
    while len(headers) <= max_index:
        headers.append(f"Column {len(headers) + 1}")

    first = [""] * len(headers)
    second = [""] * len(headers)

    def set_cell(row: list[str], key: str, value: str) -> None:
        index = columns.get(key)
        if index is not None:
            row[int(index)] = value

    date_value = sample_date_for_template(template)
    set_cell(first, "date", date_value)
    set_cell(first, "value_date", date_value)
    set_cell(first, "narration", "UPI PAYMENT TO TEST VENDOR")
    set_cell(first, "reference", "REF001")
    set_cell(first, "debit", "100.00")
    set_cell(first, "credit", "")
    set_cell(first, "balance", "9900.00")

    set_cell(second, "date", date_value)
    set_cell(second, "value_date", date_value)
    set_cell(second, "narration", "NEFT CREDIT FROM TEST CUSTOMER")
    set_cell(second, "reference", "REF002")
    set_cell(second, "debit", "")
    set_cell(second, "credit", "500.00")
    set_cell(second, "balance", "10400.00")

    return [headers, first, second]


def sample_date_for_template(template: dict[str, Any]) -> str:
    date_format = template.get("extraction", {}).get("formats", {}).get("date") or "%d/%m/%Y"
    try:
        return datetime(2026, 5, 1).strftime(date_format)
    except ValueError:
        return "01/05/2026"


def run_bank_regression(bank_code: str) -> RegressionCaseResult:
    template = load_bank_template(bank_code)
    if not template:
        return RegressionCaseResult(bank_code, False, 2, 0, "Template not found.")

    rows = build_regression_rows(template)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False, encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerows(rows)
            temp_path = Path(csv_file.name)

        parsed = parse_statement(temp_path, bank_code)
        actual = len(parsed.transactions)
        passed = actual == 2
        return RegressionCaseResult(
            bank_code=bank_code,
            passed=passed,
            expected_transactions=2,
            actual_transactions=actual,
            error=None if passed else f"Expected 2 transactions, parsed {actual}.",
        )
    except Exception as exc:
        return RegressionCaseResult(bank_code, False, 2, 0, str(exc))
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except UnboundLocalError:
            pass


def run_regression_suite() -> dict[str, Any]:
    manifest = load_regression_manifest()
    bank_codes = sorted({str(code).lower() for code in manifest.get("covered_banks", [])})
    results = [run_bank_regression(bank_code) for bank_code in bank_codes]
    failures = [result for result in results if not result.passed]

    return {
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "results": [result.__dict__ for result in results],
        "coverage": get_coverage_report(),
    }


async def get_extraction_failure_alerts(
    db: AsyncSession,
    window_days: int = 30,
    threshold: float | None = None,
    minimum_samples: int | None = None,
) -> dict[str, Any]:
    manifest = load_regression_manifest()
    threshold = float(threshold if threshold is not None else manifest.get("failure_alert_threshold", 0.05))
    minimum_samples = int(minimum_samples if minimum_samples is not None else manifest.get("minimum_samples_for_alert", 20))
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    result = await db.execute(
        select(Statement.bank_code, Statement.status, func.count(Statement.id))
        .where(Statement.created_at >= since)
        .group_by(Statement.bank_code, Statement.status)
    )

    by_bank: dict[str, dict[str, Any]] = {}
    for bank_code, status, count in result.all():
        key = (bank_code or "unknown").lower()
        bucket = by_bank.setdefault(key, {"bank_code": key, "total": 0, "failures": 0, "successes": 0})
        bucket["total"] += count
        if status in FAILURE_STATUSES:
            bucket["failures"] += count
        if status in SUCCESS_STATUSES:
            bucket["successes"] += count

    banks = []
    for bucket in sorted(by_bank.values(), key=lambda item: item["bank_code"]):
        total = bucket["total"]
        failure_rate = (bucket["failures"] / total) if total else 0
        alert = total >= minimum_samples and failure_rate > threshold
        banks.append(
            {
                **bucket,
                "failure_rate": round(failure_rate, 4),
                "threshold": threshold,
                "minimum_samples": minimum_samples,
                "alert": alert,
            }
        )

    return {
        "window_days": window_days,
        "threshold": threshold,
        "minimum_samples": minimum_samples,
        "alert_count": sum(1 for bank in banks if bank["alert"]),
        "banks": banks,
    }
