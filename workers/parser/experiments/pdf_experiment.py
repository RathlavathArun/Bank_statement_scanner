"""
Bank Statement PDF Parser Experiment (Student C - Phase 0)
Tests pdfplumber and Camelot for text extraction.
"""
import os
import sys
import yaml
import pdfplumber
import pandas as pd
from typing import Dict, Any

def load_bank_template(bank_id: str) -> Dict[str, Any]:
    template_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "..", "..", "packages", "bank-templates", f"{bank_id}.yaml"
    )
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    with open(template_path, "r") as f:
        return yaml.safe_load(f)

def extract_with_pdfplumber(pdf_path: str, template: Dict[str, Any]):
    print(f"\n--- Extracting {os.path.basename(pdf_path)} with pdfplumber ---")
    
    columns_config = template.get("columns", {})
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                print(f"Processing Page {i+1}...")
                
                # In a real scenario, use template bounding boxes or table settings
                # For this experiment, we try the default extract_tables()
                tables = page.extract_tables()
                
                for j, table in enumerate(tables):
                    df = pd.DataFrame(table[1:], columns=table[0])
                    print(f"\nTable {j+1} Head:\n{df.head(3)}")
                    
    except Exception as e:
        print(f"Error reading PDF: {e}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python pdf_experiment.py <bank_id> <path_to_pdf>")
        print("Example: python pdf_experiment.py hdfc sample_hdfc.pdf")
        sys.exit(1)
        
    bank_id = sys.argv[1]
    pdf_path = sys.argv[2]
    
    print(f"Loading template for: {bank_id.upper()}")
    template = load_bank_template(bank_id)
    
    print(f"Template loaded. Target headers: {template.get('headers')}")
    
    extract_with_pdfplumber(pdf_path, template)

if __name__ == "__main__":
    main()
