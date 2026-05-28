"""
Async SQLAlchemy engine + session factory + `get_db` dependency.

Connection pool is tuned for Cloud Run: small pool per instance (Cloud Run
scales horizontally), pre-ping to detect dropped connections after the
VPC connector's 10-minute idle timeout.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


engine = create_async_engine(
    settings.database_url,
    echo=settings.DB_ECHO,
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    pool_recycle=300,  # < VPC 10-min idle timeout
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "checkout")
def _log_pool_pressure(dbapi_conn, conn_record, conn_proxy):  # noqa: ANN001
    """Warn when overflow is engaged — early signal of pool exhaustion."""
    pool = engine.pool
    overflow = pool.overflow()
    if overflow > 0:
        logger.warning(
            "pool.pressure checkedout=%d overflow=%d size=%d",
            pool.checkedout(),
            overflow,
            pool.size(),
        )


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """Per-request session. Commits on success, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
