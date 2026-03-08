"""
Sync-tracker: records the timestamp of the last successful vector/resource
synchronisation in the database so subsequent syncs only request delta updates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped

logger = logging.getLogger(__name__)

_TABLE = "sync_tracker"


class SyncTrackerBase(DeclarativeBase):
    pass


class SyncRecord(SyncTrackerBase):
    """Stores the last successful sync timestamp per named job."""

    __tablename__ = _TABLE

    job_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


async def ensure_sync_tracker_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SyncTrackerBase.metadata.create_all, checkfirst=True)


async def get_last_sync(engine: AsyncEngine, job_name: str) -> Optional[datetime]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        result = await session.execute(
            text(f"SELECT last_synced_at FROM {_TABLE} WHERE job_name = :name"),
            {"name": job_name},
        )
        row = result.fetchone()
        return row[0] if row else None


async def set_last_sync(engine: AsyncEngine, job_name: str, synced_at: Optional[datetime] = None) -> None:
    if synced_at is None:
        synced_at = datetime.now(timezone.utc)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    f"INSERT INTO {_TABLE} (job_name, last_synced_at) VALUES (:name, :ts) "
                    f"ON CONFLICT (job_name) DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at"
                ),
                {"name": job_name, "ts": synced_at},
            )
    logger.info("Sync timestamp updated for job '%s': %s", job_name, synced_at.isoformat())

