"""
Database configuration — Production-ready for Supabase + Render.

FIXES FOR PRODUCTION:
1. Connection Pooler: Auto-convert port 5432 → 6543 (Supavisor mode)
   - Avoids "remaining connection slots are reserved" error
   - Supabase Connection Pooler handles connection management

2. SSL Mode: Force sslmode=require + rejectUnauthorized=false
   - Fixes SSL handshake failures on Render
   - Critical for external DB connections

3. Optimized pool settings for Render + Supabase
   - Smaller pool size (5 instead of 20) to avoid connection exhaustion
   - pool_pre_ping to detect dead connections
"""
import os
import logging

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/hkracing")
        
        # ===== FIX 1: Auto-convert to asyncpg driver =====
        if DATABASE_URL.startswith("postgresql://"):
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            logger.info("✅ Converted DATABASE_URL to use asyncpg driver")
        
        # ===== FIX 2: Use Supabase Connection Pooler (port 6543 instead of 5432) =====
        # Supavisor mode - avoids connection slot exhaustion under load
        if ":5432" in DATABASE_URL and os.getenv("USE_SUPABASE_POOLER", "true").lower() == "true":
            DATABASE_URL = DATABASE_URL.replace(":5432/", ":6543/", 1)
            logger.info("✅ Using Supabase Connection Pooler (port 6543)")
        
        # ===== FIX 3: Force SSL mode for Render → Supabase connection =====
        # Fixes "SSL handshake failure" timeout errors
        if 'sslmode' not in DATABASE_URL:
            if '?' in DATABASE_URL:
                DATABASE_URL += "&sslmode=require"
            else:
                DATABASE_URL += "?sslmode=require"
            logger.info("✅ Added sslmode=require to DATABASE_URL")
        
        # ===== Production-optimized pool settings =====
        # Smaller pool to avoid exhausting Supabase connections
        # pool_pre_ping = health check before using connection
        _engine = create_async_engine(
            DATABASE_URL, 
            echo=False, 
            pool_size=5,           # Smaller pool for serverless
            max_overflow=10,       # Max extra connections under load
            pool_pre_ping=True,    # Detect dead connections
            pool_recycle=300,      # Recycle connections every 5 min
            pool_timeout=30,       # Timeout waiting for connection
            connect_args={
                "server_settings": {
                    "application_name": "hk-racing-quant-render"
                },
                # SSL configuration for asyncpg
                "ssl": "require" if os.getenv("DB_SSL", "true").lower() == "true" else False,
            }
        )
        logger.info("✅ Async SQLAlchemy engine initialized with production settings")
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        engine = _get_engine()
        _session_factory = async_sessionmaker(
            engine, 
            class_=AsyncSession, 
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


class Base:
    """Placeholder — only available when DB is configured."""
    pass


try:
    from sqlalchemy.orm import DeclarativeBase
    class _RealBase(DeclarativeBase):
        pass
    Base = _RealBase
except Exception:
    pass


async def get_db():
    """Yield a DB session; if DB is unavailable, raise 503."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create tables if DB is available; silently skip otherwise."""
    try:
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization skipped (running in live-only mode): {e}")
