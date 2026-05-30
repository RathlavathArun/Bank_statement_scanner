"""Quick debug script to see what pdfplumber extracts from the ICICI PDF."""
import pdfplumber
from pathlib import Path

UPLOADS = Path(__file__).parent / "uploads"
pdf_file = sorted(UPLOADS.glob("*0197.pdf"))[-1]  # latest upload

print(f"File: {pdf_file.name}\n")

with pdfplumber.open(str(pdf_file), password="") as pdf:
    print(f"Total pages: {len(pdf.pages)}\n")
    
    for i, page in enumerate(pdf.pages):
        print(f"{'='*60}")
        print(f"PAGE {i+1}")
        print(f"{'='*60}")
        
        tables = page.extract_tables()
        if tables:
            for t_idx, table in enumerate(tables):
                print(f"\n  Table {t_idx+1} ({len(table)} rows):")
                for r_idx, row in enumerate(table[:5]):  # first 5 rows
                    print(f"    Row {r_idx}: {row}")
                if len(table) > 5:
                    print(f"    ... ({len(table) - 5} more rows)")
        else:
            print("  No tables found via extract_tables()")
        
        text = page.extract_text() or ""
        lines = text.strip().splitlines()
        print(f"\n  Raw text ({len(lines)} lines):")
        for line in lines[:8]:
            print(f"    {line}")
        if len(lines) > 8:
            print(f"    ... ({len(lines) - 8} more lines)")
        print()
