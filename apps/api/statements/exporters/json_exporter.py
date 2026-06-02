import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def generate_json(
    transactions: list[dict[str, Any]],
    statement_meta: dict[str, Any],
) -> bytes:
    """Return UTF-8 JSON bytes with statement metadata and full transaction rows."""
    total_debit = sum(Decimal(str(tx.get("amount") or 0)) for tx in transactions if tx.get("tx_type") == "DEBIT")
    total_credit = sum(Decimal(str(tx.get("amount") or 0)) for tx in transactions if tx.get("tx_type") == "CREDIT")

    payload = {
        "statement": {
            "id": statement_meta.get("id"),
            "filename": statement_meta.get("filename"),
            "bank_id": statement_meta.get("bank_id"),
            "export_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_transactions": len(transactions),
            "total_debit": float(total_debit),
            "total_credit": float(total_credit),
        },
        "transactions": [{key: _to_jsonable(value) for key, value in tx.items()} for tx in transactions],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
