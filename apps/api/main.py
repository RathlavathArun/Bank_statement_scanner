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
from db.database import init_db
from auth.router import router as auth_router
from auth.totp_router import router as totp_router
from statements.export_router import export_router
from statements.router import router as statements_router
from statements.admin_router import router as admin_router
from statements.websocket import ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — init DB and template manager on startup."""
    # ── Task 5: configure PII-redacting log filter before any other log output
    configure_pii_logging(debug=settings.DEBUG)
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
app.include_router(admin_router)
app.include_router(export_router)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(totp_router)  # Task 8: TOTP MFA endpoints


# ─── Health Check ────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return ApiResponse.ok(data={"status": "healthy", "version": "0.1.0"})


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
