"""
HK Racing Quant System — FastAPI Application Entry Point.

Deployment modes:
  - Render: Live-only mode (no DB), serves /api/live/* endpoints
  - Full mode: With PostgreSQL, also serves /api/v1/* endpoints
"""
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.routers.live import router as live_router
from app.routers.scraper import router as scraper_router
from app.routers.pre_race import router as pre_race_router
from app.middleware.rate_limit import RateLimitMiddleware

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hkrq")

# Check if DB-dependent routes should be loaded
ENABLE_DB_ROUTES = os.getenv("ENABLE_DB_ROUTES", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables if DB available; Shutdown: cleanup."""
    logger.info("🚀 HK Racing Quant starting up...")
    logger.info(f"Mode: {'full' if ENABLE_DB_ROUTES else 'live-only'}")
    logger.info("Rate limiting: 30 req/min, 300 req/hr per IP")
    try:
        from app.database import init_db
        await init_db()
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")
    yield
    logger.info("👋 HK Racing Quant shutting down")


app = FastAPI(
    title="🇭🇰 HK Racing Quant System",
    description="香港賽馬量化分析與 +EV 投注系統 API",
    version="0.4.0",
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

# Rate limiting (must be added before other middleware for correct IP detection)
app.add_middleware(RateLimitMiddleware)


# ═══ Request logging middleware ═══
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    method = request.method
    path = request.url.path

    # Skip health check spam from cron
    if path == "/health":
        return await call_next(request)

    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000)

    # Log warnings for slow requests or errors
    level = logging.WARNING if response.status_code >= 400 or duration_ms > 5000 else logging.INFO
    logger.log(level, f"{method} {path} → {response.status_code} ({duration_ms}ms)")

    return response


# Always available — live data proxy (no DB needed)
app.include_router(live_router)
app.include_router(pre_race_router)

# DB-dependent routes — only load when DB is configured
if ENABLE_DB_ROUTES:
    try:
        from app.routers.racing import router as racing_router
        from app.routers.import_data import router as import_router
        app.include_router(racing_router)
        app.include_router(import_router)
        app.include_router(scraper_router)
        logger.info("DB routes enabled")
    except Exception as e:
        logger.warning(f"DB routes skipped: {e}")


@app.get("/")
async def root():
    return {
        "system": "HK Racing Quant System",
        "version": "0.4.0",
        "status": "running",
        "mode": "full" if ENABLE_DB_ROUTES else "live-only",
        "rate_limit": "30/min, 300/hr per IP",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint — used by Render and keep-alive cron."""
    return {"status": "healthy", "mode": "full" if ENABLE_DB_ROUTES else "live-only"}
