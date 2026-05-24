"""
Database configuration — lazy-loaded to avoid crashing without PostgreSQL.
On Render free tier, we run in "live-only" mode (no DB needed).
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
        _engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        engine = _get_engine()
        _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
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
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database not available, running in live-only mode: {e}")
