import xml.etree.ElementTree as ET
from pathlib import Path

from statements.exporters.tally_xml import generate_tally_xml


GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_tally.xml"

GOLDEN_TRANSACTIONS = [
    {
        "id": "tx-001",
        "date": "2024-01-01",
        "narration": "UPI-SWIGGY Payment",
        "amount": 350.00,
        "tx_type": "DEBIT",
        "balance": 49650.0,
        "ledger_name": "Food & Beverages",
        "is_reviewed": True,
        "ocr_confidence": None,
    },
    {
        "id": "tx-002",
        "date": "2024-01-02",
        "narration": "NEFT CR-Salary",
        "amount": 50000.00,
        "tx_type": "CREDIT",
        "balance": 99650.0,
        "ledger_name": "Salary Income",
        "is_reviewed": True,
        "ocr_confidence": None,
    },
    {
        "id": "tx-003",
        "date": "2024-01-03",
        "narration": "ATM WITHDRAWAL",
        "amount": 2000.00,
        "tx_type": "DEBIT",
        "balance": 97650.0,
        "ledger_name": None,
        "is_reviewed": False,
        "ocr_confidence": None,
    },
]


def _normalize_xml(xml_str: str) -> ET.Element:
    root = ET.fromstring(xml_str)
    _strip_whitespace(root)
    return root


def _strip_whitespace(el: ET.Element) -> None:
    if el.text:
        el.text = el.text.strip()
    if el.tail:
        el.tail = el.tail.strip()
    for child in el:
        _strip_whitespace(child)


def _elements_equal(e1: ET.Element, e2: ET.Element) -> bool:
    if e1.tag != e2.tag:
        return False
    if (e1.text or "").strip() != (e2.text or "").strip():
        return False
    if e1.attrib != e2.attrib:
        return False
    if len(e1) != len(e2):
        return False
    return all(_elements_equal(c1, c2) for c1, c2 in zip(e1, e2))


def test_generate_tally_xml_matches_golden_file():
    actual = generate_tally_xml(
        GOLDEN_TRANSACTIONS,
        company_name="Acme Pvt Ltd",
        bank_ledger_name="HDFC Bank A/c",
    )
    expected = GOLDEN_PATH.read_text(encoding="utf-8")

    assert actual.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert _elements_equal(_normalize_xml(actual), _normalize_xml(expected))


def test_generate_tally_xml_strict_mode_skips_unreviewed_rows():
    actual = generate_tally_xml(
        GOLDEN_TRANSACTIONS,
        company_name="Acme Pvt Ltd",
        bank_ledger_name="HDFC Bank A/c",
        strict_reviewed_only=True,
    )

    root = ET.fromstring(actual)
    messages = root.findall(".//TALLYMESSAGE")
    assert len(messages) == 2
