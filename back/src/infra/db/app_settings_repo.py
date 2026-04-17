"""
Repository for the ``app_settings`` table.

Provides CRUD operations for persistent, admin-tuneable runtime
configuration values.  Infrastructure-only concern -- no business
logic belongs here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.infra.log.models import LogBase

logger = logging.getLogger(__name__)


class AppSetting(LogBase):
    """Persisted key/value runtime configuration entry.

    Lives in the same metadata as log tables so that ``LogBase.metadata.create_all``
    picks it up automatically during startup.
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="str")
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class AppSettingsRepository:
    """Thin async wrapper around the ``app_setting`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> List[AppSetting]:
        result = await self._session.execute(
            select(AppSetting).order_by(AppSetting.key)
        )
        return list(result.scalars().all())

    async def get_by_key(self, key: str) -> Optional[AppSetting]:
        result = await self._session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        key: str,
        value: str,
        value_type: str,
        description: str,
        updated_by: Optional[str] = None,
    ) -> AppSetting:
        existing = await self.get_by_key(key)
        if existing is not None:
            existing.value = value
            existing.value_type = value_type
            existing.description = description
            existing.updated_by = updated_by
            await self._session.flush()
            return existing

        new_setting = AppSetting(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            updated_by=updated_by,
        )
        self._session.add(new_setting)
        await self._session.flush()
        return new_setting

    async def upsert_many(
        self,
        entries: Dict[str, str],
        registry: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> List[AppSetting]:
        """Upsert multiple settings in a single transaction scope."""
        rows : List[AppSetting] = []
        for key, raw_value in entries.items():
            definition = registry.get(key)
            if definition is None:
                continue
            rows.append({
                "key": key,
                "value": raw_value,
                "value_type": definition.value_type,
                "description": definition.description,
                "updated_by": updated_by 
            })

        if not rows:
            return list()
        stmt = (
            pg_insert(AppSetting)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "value": pg_insert(AppSetting).excluded.value,
                    "value_type": pg_insert(AppSetting).excluded.value_type,
                    "description": pg_insert(AppSetting).excluded.description,
                    "updated_by": pg_insert(AppSetting).excluded.updated_by,
                    "updated_at": func.now(),
                },
            )
            .returning(AppSetting)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return list(result.scalars().all())





