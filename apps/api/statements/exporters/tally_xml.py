from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET


def _tally_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value[:10])
        return parsed.strftime("%Y%m%d")
    raise ValueError(f"Unsupported date value: {value!r}")


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _add_text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = "" if value is None else str(value)
    return node


def generate_tally_xml(
    transactions: list[dict],
    company_name: str = "My Company",
    bank_ledger_name: str = "Bank Account",
    strict_reviewed_only: bool = False,
) -> str:
    """
    Return a UTF-8 XML string ready to import into Tally Prime.
    """
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    _add_text(header, "TALLYREQUEST", "Import Data")

    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    request_desc = ET.SubElement(import_data, "REQUESTDESC")
    _add_text(request_desc, "REPORTNAME", "Vouchers")
    static_variables = ET.SubElement(request_desc, "STATICVARIABLES")
    _add_text(static_variables, "SVCURRENTCOMPANY", company_name)
    request_data = ET.SubElement(import_data, "REQUESTDATA")

    voucher_number = 1
    for tx in transactions:
        if strict_reviewed_only and not tx.get("is_reviewed", True):
            continue

        amount = _decimal(tx.get("amount"))
        if amount <= 0:
            continue

        tx_type = tx.get("tx_type")
        if tx_type not in {"DEBIT", "CREDIT"}:
            continue

        voucher_type = "Payment" if tx_type == "DEBIT" else "Receipt"
        counter_ledger = tx.get("ledger_name") or "Suspense Account"

        tally_message = ET.SubElement(request_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        voucher = ET.SubElement(
            tally_message,
            "VOUCHER",
            {
                "VCHTYPE": voucher_type,
                "ACTION": "Create",
                "OBJVIEW": "Accounting Voucher View",
            },
        )
        formatted_date = _tally_date(tx.get("date"))
        _add_text(voucher, "DATE", formatted_date)
        _add_text(voucher, "EFFECTIVEDATE", formatted_date)
        _add_text(voucher, "NARRATION", tx.get("narration") or "")
        _add_text(voucher, "VOUCHERTYPENAME", voucher_type)
        _add_text(voucher, "VOUCHERNUMBER", voucher_number)
        _add_text(voucher, "PARTYLEDGERNAME", bank_ledger_name)
        _add_text(voucher, "PERSISTEDVIEW", "Accounting Voucher View")

        first_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        second_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")

        if voucher_type == "Payment":
            _add_text(first_entry, "LEDGERNAME", bank_ledger_name)
            _add_text(first_entry, "ISDEEMEDPOSITIVE", "No")
            _add_text(first_entry, "AMOUNT", f"{amount:.2f}")

            _add_text(second_entry, "LEDGERNAME", counter_ledger)
            _add_text(second_entry, "ISDEEMEDPOSITIVE", "Yes")
            _add_text(second_entry, "AMOUNT", f"-{amount:.2f}")
        else:
            _add_text(first_entry, "LEDGERNAME", bank_ledger_name)
            _add_text(first_entry, "ISDEEMEDPOSITIVE", "Yes")
            _add_text(first_entry, "AMOUNT", f"-{amount:.2f}")

            _add_text(second_entry, "LEDGERNAME", counter_ledger)
            _add_text(second_entry, "ISDEEMEDPOSITIVE", "No")
            _add_text(second_entry, "AMOUNT", f"{amount:.2f}")

        voucher_number += 1

    xml_body = ET.tostring(envelope, encoding="unicode", short_empty_elements=True)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
