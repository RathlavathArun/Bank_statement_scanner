import json
import os
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta

# Add core path to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bank_regression import list_template_codes, load_bank_template
from statements.parser import parse_statement

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet


def generate_eval_rows(template, count=18):
    headers = list(template.get("extraction", {}).get("headers", []))
    columns = template.get("extraction", {}).get("columns", {})
    
    max_index = max(int(index) for index in columns.values())
    while len(headers) <= max_index:
        headers.append(f"Column {len(headers) + 1}")
        
    rows = [headers]
    expected_data = []
    
    date_format = template.get("extraction", {}).get("formats", {}).get("date") or "%d/%m/%Y"
    base_date = datetime(2026, 5, 1)
    
    balance = Decimal("10000.00")
    
    for i in range(count):
        row = [""] * len(headers)
        
        # Calculate dates, amounts, etc.
        tx_date = base_date + timedelta(days=i)
        date_str = tx_date.strftime(date_format)
        
        narration = f"TRANSACTION REF {i+1:03d} DETAILS"
        ref = f"REF{i+1:03d}"
        
        is_debit = (i % 2 == 0)
        amount = Decimal(f"{(i + 1) * 10.0:.2f}")
        
        if is_debit:
            debit_str = f"{amount:.2f}"
            credit_str = ""
            balance -= amount
        else:
            debit_str = ""
            credit_str = f"{amount:.2f}"
            balance += amount
            
        # Map values to columns
        def set_cell(col_key, val):
            idx = columns.get(col_key)
            if idx is not None:
                row[int(idx)] = val
                
        set_cell("date", date_str)
        set_cell("value_date", date_str)
        set_cell("narration", narration)
        set_cell("reference", ref)
        set_cell("debit", debit_str)
        set_cell("credit", credit_str)
        set_cell("balance", f"{balance:.2f}")
        
        rows.append(row)
        expected_data.append({
            "txn_date": tx_date.date(),
            "narration": narration,
            "reference_no": ref,
            "debit": amount if is_debit else None,
            "credit": amount if not is_debit else None,
            "balance": balance
        })
        
    return rows, expected_data


def evaluate():
    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    normal_style = styles["Normal"]
    
    bank_codes = list_template_codes()
    
    total_rows = 0
    correct_rows = 0
    failures = []
    
    print(f"Starting extraction accuracy evaluation on {len(bank_codes)} banks...")
    
    for bank_code in bank_codes:
        template = load_bank_template(bank_code)
        if not template:
            continue
            
        # Build eval PDF
        rows, expected = generate_eval_rows(template, count=18)
        
        temp_pdf_path = Path(f"temp_eval_{bank_code}.pdf")
        doc = SimpleDocTemplate(str(temp_pdf_path), pagesize=letter)
        elements = []
        
        bank_name = template.get("bank_name") or bank_code.upper()
        elements.append(Paragraph(f"Account Statement - {bank_name}", title_style))
        elements.append(Spacer(1, 12))
        
        regex_list = template.get("fingerprint", {}).get("regex", [])
        if regex_list:
            sample_ifsc = regex_list[0].replace("\\s*", " ").replace("\\s*:?\\s*", ": ").replace("[0-9]{6}", "001234").replace("[0-9]{4}", "1234").replace("[A-Z0-9]{6}", "001234").replace("\\", "")
            elements.append(Paragraph(f"Bank Details: {sample_ifsc}", normal_style))
            elements.append(Spacer(1, 12))
            
        table_data = []
        for r in rows:
            table_row = []
            for cell in r:
                table_row.append(Paragraph(str(cell), normal_style))
            table_data.append(table_row)
            
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        elements.append(t)
        doc.build(elements)
        
        # Parse it
        try:
            parsed = parse_statement(temp_pdf_path, bank_code)
            actual_txs = parsed.transactions
            
            for idx, exp in enumerate(expected):
                total_rows += 1
                if idx >= len(actual_txs):
                    failures.append({
                        "bank_code": bank_code,
                        "row": idx + 1,
                        "error": "Row missing in parsed transactions"
                    })
                    continue
                    
                tx = actual_txs[idx]
                row_correct = True
                
                # Check narration
                exp_norm = "".join(c for c in exp["narration"].lower() if c.isalnum())
                tx_norm = "".join(c for c in tx.narration.lower() if c.isalnum())
                if exp_norm not in tx_norm:
                    row_correct = False
                    
                # Check debit
                if exp["debit"] != tx.debit:
                    row_correct = False
                    
                # Check credit
                if exp["credit"] != tx.credit:
                    row_correct = False
                    
                # Check balance
                if exp["balance"] != tx.balance:
                    row_correct = False
                    
                if row_correct:
                    correct_rows += 1
                else:
                    failures.append({
                        "bank_code": bank_code,
                        "row": idx + 1,
                        "expected": {
                            "narration": exp["narration"],
                            "debit": str(exp["debit"]) if exp["debit"] else None,
                            "credit": str(exp["credit"]) if exp["credit"] else None,
                            "balance": str(exp["balance"])
                        },
                        "actual": {
                            "narration": tx.narration,
                            "debit": str(tx.debit) if tx.debit else None,
                            "credit": str(tx.credit) if tx.credit else None,
                            "balance": str(tx.balance)
                        }
                    })
        except Exception as e:
            failures.append({
                "bank_code": bank_code,
                "error": str(e)
            })
            total_rows += len(expected)
        finally:
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()
                
    accuracy = correct_rows / total_rows if total_rows else 0.0
    report = {
        "evaluation_timestamp": datetime.now().isoformat(),
        "total_transactions_evaluated": total_rows,
        "correct_transactions": correct_rows,
        "extraction_accuracy_rate": accuracy,
        "status": "PASSED" if accuracy >= 0.98 else "FAILED",
        "failures_count": len(failures),
        "failures": failures[:10]  # first 10 failure samples
    }
    
    output_path = Path(__file__).resolve().parents[1] / "accuracy_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Accuracy report generated: {output_path}")
    print(f"Total Evaluated: {total_rows}, Accuracy: {accuracy*100:.2f}%")
    return report


if __name__ == "__main__":
    evaluate()
