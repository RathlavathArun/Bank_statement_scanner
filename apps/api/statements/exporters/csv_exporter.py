import csv
import io
from decimal import Decimal
from typing import Any


def _money(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"{Decimal(str(value)):.2f}"


def generate_csv(transactions: list[dict[str, Any]]) -> bytes:
    """Return Excel-friendly UTF-8 CSV bytes for exported transactions."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
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
    )

    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for tx in transactions:
        amount = Decimal(str(tx.get("amount") or 0))
        tx_type = tx.get("tx_type")
        debit = ""
        credit = ""
        if tx_type == "DEBIT":
            debit = f"{amount:.2f}"
            total_debit += amount
        elif tx_type == "CREDIT":
            credit = f"{amount:.2f}"
            total_credit += amount

        ocr_confidence = tx.get("ocr_confidence")
        writer.writerow(
            [
                tx.get("date", ""),
                tx.get("narration", ""),
                debit,
                credit,
                _money(tx.get("balance")),
                tx.get("payment_mode") or "",
                tx.get("counterparty") or "",
                tx.get("ledger_name") or "",
                "" if ocr_confidence is None else f"{float(ocr_confidence):.3f}",
                "Yes" if tx.get("is_reviewed", True) else "No",
            ]
        )

    writer.writerow(
        [
            "TOTAL",
            "",
            f"{total_debit:.2f}",
            f"{total_credit:.2f}",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )

    return output.getvalue().encode("utf-8-sig")
