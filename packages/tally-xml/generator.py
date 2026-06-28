"""
Tally XML Generator — produces TALLYMESSAGE-compatible XML from a list of
transactions for import into Tally Prime / Tally ERP 9.

Usage:
    from packages.tally_xml.generator import TallyXMLGenerator

    generator = TallyXMLGenerator(company_name="Acme Corp", bank_ledger="HDFC Bank")
    xml_bytes = generator.generate(transactions)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class TallyTransaction:
    """Minimal transaction needed to generate a Tally voucher."""

    txn_date: date
    narration: str
    debit: Optional[Decimal]
    credit: Optional[Decimal]
    ledger_name: Optional[str]
    reference_no: Optional[str] = None


class TallyXMLGenerator:
    """Generates Tally-compatible XML import files."""

    TALLY_DATE_FORMAT = "%Y%m%d"

    def __init__(self, company_name: str, bank_ledger: str = "Bank Account") -> None:
        self.company_name = company_name
        self.bank_ledger = bank_ledger

    def generate(self, transactions: list[TallyTransaction]) -> bytes:
        """Return UTF-8 encoded Tally XML bytes."""
        root = ET.Element("ENVELOPE")
        header = ET.SubElement(root, "HEADER")
        ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

        body = ET.SubElement(root, "BODY")
        import_data = ET.SubElement(body, "IMPORTDATA")
        request_desc = ET.SubElement(import_data, "REQUESTDESC")
        ET.SubElement(request_desc, "REPORTNAME").text = "All Masters"
        request_data = ET.SubElement(import_data, "REQUESTDATA")
        tally_message = ET.SubElement(request_data, "TALLYMESSAGE",
                                       attrib={"xmlns:UDF": "TallyUDF"})

        for txn in transactions:
            self._add_voucher(tally_message, txn)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        import io
        buf = io.BytesIO()
        tree.write(buf, encoding="utf-8", xml_declaration=True)
        return buf.getvalue()

    def _add_voucher(self, parent: ET.Element, txn: TallyTransaction) -> None:
        """Append a single payment/receipt voucher element."""
        voucher_type = "Receipt" if txn.credit else "Payment"
        amount = txn.credit or txn.debit or Decimal("0")
        ledger = txn.ledger_name or "Suspense Account"

        voucher = ET.SubElement(parent, "VOUCHER",
                                 attrib={"VCHTYPE": voucher_type,
                                         "ACTION": "Create"})
        ET.SubElement(voucher, "DATE").text = txn.txn_date.strftime(self.TALLY_DATE_FORMAT)
        ET.SubElement(voucher, "NARRATION").text = txn.narration
        if txn.reference_no:
            ET.SubElement(voucher, "VOUCHERNUMBER").text = txn.reference_no

        # Debit leg (bank receives credit = debit in bank ledger)
        all_ledger_entries = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        dr_entry = ET.SubElement(all_ledger_entries, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(dr_entry, "LEDGERNAME").text = self.bank_ledger if txn.credit else ledger
        ET.SubElement(dr_entry, "ISDEEMEDPOSITIVE").text = "Yes" if txn.credit else "No"
        ET.SubElement(dr_entry, "AMOUNT").text = f"-{amount}" if txn.credit else str(amount)

        # Credit leg
        cr_entry = ET.SubElement(all_ledger_entries, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(cr_entry, "LEDGERNAME").text = ledger if txn.credit else self.bank_ledger
        ET.SubElement(cr_entry, "ISDEEMEDPOSITIVE").text = "No" if txn.credit else "Yes"
        ET.SubElement(cr_entry, "AMOUNT").text = str(amount) if txn.credit else f"-{amount}"
