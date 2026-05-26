"""
Bank Statement Extraction — FastAPI Application
Main entry point. Wires up routes, middleware, and lifecycle events.
"""
import sys
import os


# Ensure the api directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.response import ApiResponse
from db.database import init_db
from auth.router import router as auth_router
from statements.router import router as statements_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — init DB on startup."""
    print("[START] Starting Bank Statement Extraction API...")
    await init_db()
    print("[OK] Database tables created / verified")
    yield
    print("[STOP] Shutting down API...")


app = FastAPI(
    title="Bank Statement Extraction API",
    description="AI-powered PDF/Excel to structured ledger data pipeline",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(statements_router)
# ─── CORS Middleware ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────
app.include_router(auth_router)


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
