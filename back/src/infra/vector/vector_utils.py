"""
Vector table utility functions: validation, existence checks, drop.

All operations use raw asyncpg for efficiency; they are intentionally
independent of SQLAlchemy to avoid ORM interference with LlamaIndex-managed
tables.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_MAX_IDENTIFIER_LENGTH = 63


def validate_table_name(name: str) -> None:
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid table name '{name}': must start with a letter or underscore "
            "and contain only letters, digits, and underscores."
        )
    if len(name) > _MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"Table name '{name}' exceeds PostgreSQL's {_MAX_IDENTIFIER_LENGTH}-character limit."
        )


def physical_table_name(logical_name: str) -> str:
    """LlamaIndex PGVectorStore prepends 'data_' to the logical table name."""
    validate_table_name(logical_name)
    return logical_name if logical_name.startswith("data_") else f"data_{logical_name}"


async def table_row_count(dsn: dict, table_name: str) -> Optional[int]:
    validate_table_name(table_name)
    conn = await asyncpg.connect(**dsn)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
            table_name,
        )
        if not exists:
            return None
        return await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
    finally:
        await conn.close()


async def drop_vector_table(dsn: dict, table_name: str) -> None:
    validate_table_name(table_name)
    conn = await asyncpg.connect(**dsn)
    try:
        await conn.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        logger.info("Dropped vector table: %s", table_name)
    finally:
        await conn.close()


async def ensure_pgvector_extension(dsn: dict) -> None:
    conn = await asyncpg.connect(**dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()

