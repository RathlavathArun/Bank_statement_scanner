"""
Bank template loader and validator.
Handles loading YAML bank templates, validation, and metadata extraction.
Now with hot-reload support via template manager.
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# Path to bank templates directory
BANK_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "packages" / "bank-templates"


class BankTemplateSchema(BaseModel):
    """Pydantic schema for validating bank templates."""
    bank_code: str
    bank_name: str
    type: str
    fingerprint: Dict[str, Any]
    extraction: Dict[str, Any]


class BankMetadata(BaseModel):
    """Extracted metadata from a bank template."""
    bank_code: str
    bank_name: str
    extraction_type: str
    supported_formats: List[str] = ["pdf_text", "excel", "csv"]


def load_template_file(bank_code: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Load a bank template YAML file (with optional cache).
    
    Args:
        bank_code: Bank code (e.g., 'hdfc', 'icici')
        use_cache: Use template manager cache if available
    
    Returns:
        Dict with template content, or None if not found
    """
    # Try cache first if available
    if use_cache:
        try:
            from core.template_watcher import get_template_manager
            manager = get_template_manager()
            cached = manager.get_template(bank_code)
            if cached:
                return cached
        except (ImportError, RuntimeError):
            pass  # Template manager not initialized, fall back to file load
    
    # Load from file
    template_file = BANK_TEMPLATES_DIR / f"{bank_code.lower()}.yaml"
    
    if not template_file.exists():
        logger.warning(f"Template not found: {template_file}")
        return None
    
    try:
        with open(template_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading template {bank_code}: {e}")
        return None


def validate_template(template_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate a bank template against schema.
    
    Args:
        template_data: Template dictionary from YAML
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        BankTemplateSchema(**template_data)
        return True, None
    except ValidationError as e:
        return False, str(e)


def extract_bank_metadata(bank_code: str, template_data: Dict[str, Any]) -> Optional[BankMetadata]:
    """
    Extract bank metadata from template.
    
    Args:
        bank_code: Bank code
        template_data: Template dictionary
    
    Returns:
        BankMetadata object
    """
    try:
        return BankMetadata(
            bank_code=bank_code,
            bank_name=template_data.get("bank_name", ""),
            extraction_type=template_data.get("type", "pdf_text")
        )
    except Exception as e:
        logger.error(f"Error extracting metadata for {bank_code}: {e}")
        return None


def list_available_banks() -> List[Dict[str, Any]]:
    """
    List all available bank templates.
    
    Returns:
        List of bank metadata dictionaries
    """
    if not BANK_TEMPLATES_DIR.exists():
        logger.warning(f"Bank templates directory not found: {BANK_TEMPLATES_DIR}")
        return []
    
    banks = []
    for template_file in BANK_TEMPLATES_DIR.glob("*.yaml"):
        bank_code = template_file.stem
        template_data = load_template_file(bank_code)
        
        if template_data:
            is_valid, error = validate_template(template_data)
            if is_valid:
                metadata = extract_bank_metadata(bank_code, template_data)
                if metadata:
                    banks.append({
                        "id": metadata.bank_code,
                        "code": metadata.bank_code,
                        "name": metadata.bank_name,
                        "extraction_type": metadata.extraction_type,
                        "template_path": str(template_file),
                        "is_active": True,
                    })
            else:
                logger.warning(f"Invalid template for {bank_code}: {error}")
    
    return sorted(banks, key=lambda x: x["name"])


def get_bank_by_code(bank_code: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific bank template by code.
    
    Args:
        bank_code: Bank code
    
    Returns:
        Bank template data or None
    """
    template_data = load_template_file(bank_code)
    if template_data:
        is_valid, _ = validate_template(template_data)
        if is_valid:
            metadata = extract_bank_metadata(bank_code, template_data)
            if metadata:
                return {
                    "id": metadata.bank_code,
                    "code": metadata.bank_code,
                    "name": metadata.bank_name,
                    "extraction_type": metadata.extraction_type,
                    "template_path": str(BANK_TEMPLATES_DIR / f"{bank_code.lower()}.yaml"),
                    "is_active": True,
                    "template": template_data,
                }
    return None


def save_template_file(bank_code: str, template_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Save a bank template to YAML file.
    
    Args:
        bank_code: Bank code
        template_data: Template dictionary
    
    Returns:
        Tuple of (success, error_message)
    """
    # Validate before saving
    is_valid, error = validate_template(template_data)
    if not is_valid:
        return False, f"Invalid template: {error}"
    
    try:
        template_file = BANK_TEMPLATES_DIR / f"{bank_code.lower()}.yaml"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(template_file, 'w') as f:
            yaml.dump(template_data, f, default_flow_style=False)
        
        logger.info(f"Template saved for {bank_code}")
        return True, None
    except Exception as e:
        logger.error(f"Error saving template {bank_code}: {e}")
        return False, str(e)


def delete_template_file(bank_code: str) -> tuple[bool, Optional[str]]:
    """
    Delete a bank template file.
    
    Args:
        bank_code: Bank code
    
    Returns:
        Tuple of (success, error_message)
    """
    try:
        template_file = BANK_TEMPLATES_DIR / f"{bank_code.lower()}.yaml"
        if template_file.exists():
            template_file.unlink()
            logger.info(f"Template deleted for {bank_code}")
            return True, None
        else:
            return False, "Template not found"
    except Exception as e:
        logger.error(f"Error deleting template {bank_code}: {e}")
        return False, str(e)
