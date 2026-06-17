"""Phase 6 Part D per-bank regression, coverage, and failure alert tests."""
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.bank_regression import (
    get_coverage_report,
    get_extraction_failure_alerts,
    run_bank_regression,
    run_regression_suite,
)
from db.models import Client, Firm, Statement


def test_regression_coverage_tracks_every_bank_template():
    report = get_coverage_report()

    assert report["total_templates"] >= 16
    assert report["coverage_percent"] == 100
    assert report["missing_banks"] == []
    assert report["stale_manifest_banks"] == []
    assert report["is_complete"] is True


def test_per_bank_regression_suite_parses_all_covered_templates():
    suite = run_regression_suite()

    assert suite["failed"] == 0
    assert suite["passed"] == suite["total"]
    assert suite["coverage"]["is_complete"] is True


@pytest.mark.parametrize(
    "bank_code",
    [
        "axis",
        "au_small_finance",
        "bank_of_baroda",
        "bank_of_india",
        "canara",
        "cbi",
        "federal",
        "hdfc",
        "icici",
        "idfc_first",
        "indusind",
        "kotak",
        "pnb",
        "rbl",
        "sbi",
        "union_bank",
        "yes_bank",
    ],
)
def test_each_bank_template_has_a_passing_parser_regression(bank_code):
    result = run_bank_regression(bank_code)

    assert result.passed is True
    assert result.actual_transactions == 2


@pytest.mark.asyncio
async def test_failure_alert_flags_banks_above_five_percent(db: AsyncSession):
    firm = Firm(name="Regression Alert Firm")
    db.add(firm)
    await db.flush()

    client = Client(firm_id=firm.id, name="Regression Alert Client")
    db.add(client)
    await db.flush()

    statements = []
    statements.extend(build_statements(client.id, "hdfc", "READY_FOR_REVIEW", 19))
    statements.extend(build_statements(client.id, "hdfc", "FAILED", 2))
    statements.extend(build_statements(client.id, "icici", "READY_FOR_REVIEW", 19))
    statements.extend(build_statements(client.id, "icici", "FAILED", 1))
    statements.extend(build_statements(client.id, "sbi", "READY_FOR_REVIEW", 10))
    statements.extend(build_statements(client.id, "sbi", "FAILED", 2))
    db.add_all(statements)
    await db.commit()

    alerts = await get_extraction_failure_alerts(db, threshold=0.05, minimum_samples=20)
    by_bank = {bank["bank_code"]: bank for bank in alerts["banks"]}

    assert by_bank["hdfc"]["failure_rate"] > 0.05
    assert by_bank["hdfc"]["alert"] is True
    assert by_bank["icici"]["failure_rate"] == 0.05
    assert by_bank["icici"]["alert"] is False
    assert by_bank["sbi"]["total"] == 12
    assert by_bank["sbi"]["alert"] is False
    assert alerts["alert_count"] == 1


def build_statements(client_id: str, bank_code: str, status: str, count: int) -> list[Statement]:
    return [
        Statement(
            client_id=client_id,
            file_url=f"/tmp/{bank_code}-{status.lower()}-{index}.csv",
            file_type="csv",
            bank_code=bank_code,
            status=status,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
        )
        for index in range(count)
    ]
