"""
Admin API router for managing bank templates.
Provides endpoints for CRUD operations on bank templates with admin authorization.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime
import yaml
import logging

from core.response import ApiResponse
from core.bank_loader import (
    list_available_banks,
    get_bank_by_code,
    load_template_file,
    validate_template,
    save_template_file,
    delete_template_file,
)
from core.bank_regression import (
    get_coverage_report,
    get_extraction_failure_alerts,
    run_regression_suite,
)
from db.database import get_db
from db.models import BankTemplate, User
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/banks", tags=["admin", "banks"])


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Verify user has admin role."""
    # Check if user is firm admin or owner
    # For now, we'll allow any logged-in user
    # In production, check FirmMember.role == "admin" or "owner"
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user


@router.get("")
async def list_banks(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all available bank templates.
    Returns banks from file system and database metadata.
    """
    try:
        banks = list_available_banks()
        return ApiResponse.ok(
            data={
                "banks": banks,
                "total": len(banks),
            }
        )
    except Exception as e:
        logger.error(f"Error listing banks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qa/coverage")
async def get_template_regression_coverage(
    current_user: User = Depends(get_admin_user),
):
    """Get per-bank regression coverage for available templates."""
    try:
        return ApiResponse.ok(data=get_coverage_report())
    except Exception as e:
        logger.error(f"Error getting template coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qa/regression")
async def run_template_regressions(
    current_user: User = Depends(get_admin_user),
):
    """Run synthetic parser regression checks for every covered bank template."""
    try:
        return ApiResponse.ok(data=run_regression_suite())
    except Exception as e:
        logger.error(f"Error running template regressions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qa/failure-alerts")
async def get_bank_failure_alerts(
    window_days: int = 30,
    threshold: float | None = None,
    minimum_samples: int | None = None,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Alert when a bank's extraction failure rate crosses the configured threshold."""
    try:
        alerts = await get_extraction_failure_alerts(
            db,
            window_days=window_days,
            threshold=threshold,
            minimum_samples=minimum_samples,
        )
        return ApiResponse.ok(data=alerts)
    except Exception as e:
        logger.error(f"Error getting failure alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bank_code}")
async def get_bank(
    bank_code: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific bank template with full details."""
    try:
        bank = get_bank_by_code(bank_code.lower())
        if not bank:
            raise HTTPException(status_code=404, detail="Bank template not found")
        
        return ApiResponse.ok(data=bank)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bank {bank_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_bank(
    file: UploadFile = File(...),
    bank_code: Optional[str] = None,
    bank_name: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a new bank template.
    
    Args:
        file: YAML template file
        bank_code: Bank code (optional, extracted from file if not provided)
        bank_name: Bank name (optional, extracted from file if not provided)
    """
    try:
        # Read uploaded file
        content = await file.read()
        
        # Parse YAML
        try:
            template_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
        
        # Extract bank code from file or template
        code = (bank_code or template_data.get("bank_code", "")).lower()
        if not code:
            raise HTTPException(status_code=400, detail="Bank code is required")
        
        name = bank_name or template_data.get("bank_name", "")
        if not name:
            raise HTTPException(status_code=400, detail="Bank name is required")
        
        # Validate template
        is_valid, error = validate_template(template_data)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid template: {error}")
        
        # Save template file
        success, error = save_template_file(code, template_data)
        if not success:
            raise HTTPException(status_code=500, detail=f"Error saving template: {error}")
        
        # Save to database
        db_template = BankTemplate(
            bank_code=code,
            bank_name=name,
            template_path=f"packages/bank-templates/{code}.yaml",
            description=template_data.get("description", ""),
            uploaded_by=current_user.id,
            extraction_type=template_data.get("type", "pdf_text"),
            metadata_={"fingerprint": template_data.get("fingerprint", {})}
        )
        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        
        return ApiResponse.ok(
            data={
                "id": db_template.id,
                "bank_code": db_template.bank_code,
                "bank_name": db_template.bank_name,
                "created_at": db_template.created_at.isoformat(),
            },
            message="Bank template uploaded successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading bank template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{bank_code}")
async def update_bank(
    bank_code: str,
    file: Optional[UploadFile] = File(None),
    bank_name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a bank template.
    
    Args:
        bank_code: Bank code
        file: Optional new YAML template file
        bank_name: Optional new bank name
        description: Optional description
        is_active: Optional active status
    """
    try:
        code = bank_code.lower()
        
        # Get existing template from database
        stmt = select(BankTemplate).where(BankTemplate.bank_code == code)
        result = await db.execute(stmt)
        db_template = result.scalar_one_or_none()
        
        if not db_template:
            raise HTTPException(status_code=404, detail="Bank template not found")
        
        # Update file if provided
        if file:
            content = await file.read()
            try:
                template_data = yaml.safe_load(content)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
            
            is_valid, error = validate_template(template_data)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid template: {error}")
            
            success, error = save_template_file(code, template_data)
            if not success:
                raise HTTPException(status_code=500, detail=f"Error saving template: {error}")
            
            db_template.metadata_ = {"fingerprint": template_data.get("fingerprint", {})}
        
        # Update metadata
        if bank_name:
            db_template.bank_name = bank_name
        if description is not None:
            db_template.description = description
        if is_active is not None:
            db_template.is_active = is_active
        
        await db.commit()
        await db.refresh(db_template)
        
        return ApiResponse.ok(
            data={
                "id": db_template.id,
                "bank_code": db_template.bank_code,
                "bank_name": db_template.bank_name,
                "is_active": db_template.is_active,
                "updated_at": db_template.updated_at.isoformat(),
            },
            message="Bank template updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating bank template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{bank_code}")
async def delete_bank(
    bank_code: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a bank template.
    
    Args:
        bank_code: Bank code
    """
    try:
        code = bank_code.lower()
        
        # Delete from database
        stmt = select(BankTemplate).where(BankTemplate.bank_code == code)
        result = await db.execute(stmt)
        db_template = result.scalar_one_or_none()
        
        if not db_template:
            raise HTTPException(status_code=404, detail="Bank template not found")
        
        await db.delete(db_template)
        
        # Delete file
        success, error = delete_template_file(code)
        if not success:
            logger.warning(f"Could not delete template file for {code}: {error}")
        
        await db.commit()
        
        return ApiResponse.ok(
            data={"bank_code": code},
            message="Bank template deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting bank template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bank_code}/download", response_class=FileResponse)
async def download_template(
    bank_code: str,
    current_user: User = Depends(get_admin_user),
):
    """
    Download a bank template file.
    
    Args:
        bank_code: Bank code
    """
    try:
        from pathlib import Path
        template_path = Path(__file__).parent.parent.parent.parent / "packages" / "bank-templates" / f"{bank_code.lower()}.yaml"
        
        if not template_path.exists():
            raise HTTPException(status_code=404, detail="Template file not found")
        
        return FileResponse(
            path=template_path,
            filename=f"{bank_code.lower()}.yaml",
            media_type="application/x-yaml"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Template Hot-Reload Endpoints ──────────────────────────────

@router.post("/reload/all")
async def reload_all_templates(
    current_user: User = Depends(get_admin_user),
):
    """
    Force reload all templates from disk.
    """
    try:
        from core.template_watcher import get_template_manager
        manager = get_template_manager()
        results = manager.reload_all()
        
        return ApiResponse.ok(
            data={
                "reloaded_count": len([r for r in results.values() if r]),
                "failed_count": len([r for r in results.values() if not r]),
                "results": results,
            },
            message=f"Reloaded {len([r for r in results.values() if r])} templates"
        )
    except Exception as e:
        logger.error(f"Error reloading templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bank_code}/reload")
async def reload_bank_template(
    bank_code: str,
    current_user: User = Depends(get_admin_user),
):
    """
    Force reload a specific bank template.
    
    Args:
        bank_code: Bank code to reload
    """
    try:
        from core.template_watcher import get_template_manager
        manager = get_template_manager()
        success = manager.reload_bank(bank_code)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Could not reload template: {bank_code}")
        
        return ApiResponse.ok(
            data={"bank_code": bank_code},
            message=f"Template reloaded: {bank_code}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading bank {bank_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Cache Management Endpoints ──────────────────────────────────

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_admin_user),
):
    """
    Get template cache statistics.
    """
    try:
        from core.template_watcher import get_template_manager
        manager = get_template_manager()
        stats = manager.get_stats()
        
        return ApiResponse.ok(data=stats)
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/clear")
async def clear_cache(
    current_user: User = Depends(get_admin_user),
):
    """
    Clear all template cache.
    """
    try:
        from core.template_watcher import get_template_manager
        manager = get_template_manager()
        manager.clear_cache()
        
        return ApiResponse.ok(
            data={},
            message="Template cache cleared"
        )
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
