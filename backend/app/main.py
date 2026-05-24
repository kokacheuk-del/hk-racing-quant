"""
HK Racing Quant System — FastAPI Application Entry Point.

Deployment modes:
  - Render: Live-only mode (no DB), serves /api/live/* endpoints
  - Full mode: With PostgreSQL, also serves /api/v1/* endpoints
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.live import router as live_router

logger = logging.getLogger(__name__)

# Check if DB-dependent routes should be loaded
ENABLE_DB_ROUTES = os.getenv("ENABLE_DB_ROUTES", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables if DB available; Shutdown: cleanup."""
    try:
        from app.database import init_db
        await init_db()
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")
    yield


app = FastAPI(
    title="🇭🇰 HK Racing Quant System",
    description="香港賽馬量化分析與 +EV 投注系統 API",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow Vercel frontend and local dev
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Always available — live data proxy (no DB needed)
app.include_router(live_router)

# DB-dependent routes — only load when DB is configured
if ENABLE_DB_ROUTES:
    try:
        from app.routers.racing import router as racing_router
        from app.routers.import_data import router as import_router
        app.include_router(racing_router)
        app.include_router(import_router)
        logger.info("DB routes enabled")
    except Exception as e:
        logger.warning(f"DB routes skipped: {e}")


@app.get("/")
async def root():
    return {
        "system": "HK Racing Quant System",
        "version": "0.2.0",
        "status": "running",
        "mode": "full" if ENABLE_DB_ROUTES else "live-only",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint — used by Render and keep-alive cron."""
    return {"status": "healthy", "mode": "full" if ENABLE_DB_ROUTES else "live-only"}
