"""
Bank Statement Extraction — FastAPI Application
Main entry point. Wires up routes, middleware, and lifecycle events.
"""
import sys
import os
import logging


# Ensure the api directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from core.config import settings
from core.response import ApiResponse
from core.log_filter import configure_pii_logging
from core.observability import init_observability
from db.database import init_db
from auth.router import router as auth_router
from auth.totp_router import router as totp_router
from statements.export_router import export_router
from statements.router import router as statements_router
from statements.jobs_router import router as jobs_router
from statements.admin_router import router as admin_router
from statements.rules_router import rules_router  # Task 20: custom rules engine
from statements.websocket import ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — init DB and template manager on startup."""
    # ── Task 5: configure PII-redacting log filter before any other log output
    configure_pii_logging(debug=settings.DEBUG)
    # ── Tasks 12 & 13: initialize OpenTelemetry tracing and Sentry error tracking
    init_observability(app=app)
    logging.getLogger(__name__).info("[START] Starting Bank Statement Extraction API...")

    print("[START] Starting Bank Statement Extraction API...")
    await init_db()
    print("[OK] Database tables created / verified")
    
    # Initialize template manager for hot-reload
    try:
        from core.template_watcher import initialize_template_manager
        initialize_template_manager()
        print("[OK] Template manager initialized with hot-reload support")
    except Exception as e:
        print(f"[WARN] Could not initialize template manager: {e}")

    # Initialize Qdrant collection (if enabled)
    try:
        from statements.ledger_memory import qdrant_memory
        if qdrant_memory.enabled:
            await qdrant_memory.ensure_collection()
            print("[OK] Qdrant collection initialized")
        else:
            print("[SKIP] Qdrant disabled — ledger memory uses PostgreSQL only")
    except Exception as e:
        print(f"[WARN] Qdrant init failed (non-fatal): {e}")

    yield
    
    # Shutdown template manager
    try:
        from core.template_watcher import shutdown_template_manager
        shutdown_template_manager()
        print("[OK] Template manager shutdown")
    except Exception as e:
        print(f"[WARN] Error during template manager shutdown: {e}")
    
    print("[STOP] Shutting down API...")


app = FastAPI(
    title="Bank Statement Extraction API",
    description="AI-powered PDF/Excel to structured ledger data pipeline",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

# ─── Prometheus Instrumentation ──────────────────────────────
Instrumentator().instrument(app).expose(app)

# ─── CORS Middleware ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────
app.include_router(statements_router)
app.include_router(jobs_router)
app.include_router(admin_router)
app.include_router(export_router)
app.include_router(rules_router)   # Task 20: narration rules CRUD
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(totp_router)  # Task 8: TOTP MFA endpoints


# ─── Health Check ────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    import httpx

    qdrant_status = "disabled"
    if settings.QDRANT_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
                r = await client.get(f"{settings.QDRANT_URL}/collections", headers=headers)
                qdrant_status = "ok" if r.status_code == 200 else "error"
        except Exception:
            qdrant_status = "unreachable"

    return ApiResponse.ok(data={
        "status": "healthy",
        "version": "0.1.0",
        "qdrant": qdrant_status,
    })


@app.get("/", tags=["System"])
async def root():
    return ApiResponse.ok(
        data={
            "service": "Bank Statement Extraction API",
            "version": "0.1.0",
            "docs": "/docs",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
