"""Generate real golden PDF test files for each bank template."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from core.bank_regression import TEMPLATE_DIR, list_template_codes, load_bank_template, build_regression_rows


def generate_all_golden_pdfs() -> None:
    golden_dir = TEMPLATE_DIR / "golden_pdfs"
    golden_dir.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    normal_style = styles["Normal"]

    for bank_code in list_template_codes():
        template = load_bank_template(bank_code)
        if not template:
            print(f"Skipping {bank_code}: template not found.")
            continue

        pdf_path = golden_dir / f"{bank_code}.pdf"
        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
        elements = []

        # Add Bank Name and Header info
        bank_name = template.get("bank_name") or template.get("display_name") or bank_code.upper()
        elements.append(Paragraph(f"Account Statement - {bank_name}", title_style))
        elements.append(Spacer(1, 12))

        # Add fingerprint regex match if available to satisfy fingerprinting
        regex_list = template.get("fingerprint", {}).get("regex", [])
        if regex_list:
            # Create a sample string that matches typical IFSC regexes
            sample_ifsc = regex_list[0].replace("\\s*", " ").replace("\\s*:?\\s*", ": ").replace("[0-9]{6}", "001234").replace("[0-9]{4}", "1234").replace("[A-Z0-9]{6}", "001234").replace("\\", "")
            elements.append(Paragraph(f"Bank Details: {sample_ifsc}", normal_style))
            elements.append(Spacer(1, 12))

        # Build table data
        rows = build_regression_rows(template)
        
        # Wrap cells in Paragraph to handle wrapping and clean string rendering
        table_data = []
        for row_idx, row in enumerate(rows):
            table_row = []
            for cell in row:
                table_row.append(Paragraph(str(cell), normal_style))
            table_data.append(table_row)

        t = Table(table_data)
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t)

        doc.build(elements)
        print(f"Generated golden PDF for {bank_code} at {pdf_path}")


if __name__ == "__main__":
    generate_all_golden_pdfs()
