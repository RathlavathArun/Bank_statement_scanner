"""Phase 6 Part C bank template coverage checks."""
from pathlib import Path

import yaml

from core.bank_loader import validate_template
from statements.parser import detect_columns


ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT_DIR / "packages" / "bank-templates"

PHASE_6_C_BANKS = {
    "yes_bank",
    "idfc_first",
    "indusind",
    "kotak",
    "rbl",
    "federal",
    "pnb",
    "canara",
    "bank_of_baroda",
    "union_bank",
    "au_small_finance",
    "bank_of_india",
}


def load_template(bank_code: str) -> dict:
    with (TEMPLATE_DIR / f"{bank_code}.yaml").open("r", encoding="utf-8") as template_file:
        return yaml.safe_load(template_file) or {}


def test_phase_6_c_templates_exist():
    missing = [bank for bank in PHASE_6_C_BANKS if not (TEMPLATE_DIR / f"{bank}.yaml").exists()]
    assert missing == []


def test_all_bank_templates_validate_against_admin_loader_schema():
    invalid = {}
    for template_path in TEMPLATE_DIR.glob("*.yaml"):
        if template_path.name == "regression_manifest.yaml":
            continue
        template = load_template(template_path.stem)
        is_valid, error = validate_template(template)
        if not is_valid:
            invalid[template_path.name] = error

    assert invalid == {}


def test_phase_6_c_templates_have_parser_column_mappings():
    for bank_code in PHASE_6_C_BANKS:
        template = load_template(bank_code)
        headers = template["extraction"]["headers"]
        header_index, columns = detect_columns([headers], template)

        assert header_index == 0
        assert columns["date"] is not None
        assert columns["narration"] is not None
        assert columns["debit"] is not None
        assert columns["credit"] is not None
        assert columns["balance"] is not None
