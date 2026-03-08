"""
Database setup service.

Responsible for ensuring all tables exist and are up-to-date at server
startup via a versioned migration system.

Architecture
------------
1. ``_ensure_tables``   - creates any missing tables via SQLAlchemy metadata
                          (create_all) and adds any new columns declared in the
                          models but absent from the DB.
2. ``run_migrations``   - applies versioned SQL migrations in order.  The current
                          DB version is stored in ``schema_migration_version``.
                          Each migration runs in its own transaction so a failure
                          rolls back only that step.
3. ``_sync_prompts``    - keeps system-prompt rows in sync with on-disk .txt files.

Everything is idempotent: safe to call on every restart.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.core.path_constants import PROMPTS_DIR
from src.infra.db.resource_models import ResourceBase
from src.infra.log.models import LogBase
from src.infra.vector.sync_tracker import SyncTrackerBase

logger = logging.getLogger(__name__)


class SchemaDriftError(RuntimeError):
    """Raised when a column type mismatch is detected that requires manual migration."""


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_prompts_from_disk() -> Dict[str, str]:
    prompts: Dict[str, str] = {}
    if not PROMPTS_DIR.exists():
        logger.warning("Prompts directory not found: %s", PROMPTS_DIR)
        return prompts
    for path in sorted(PROMPTS_DIR.glob("*.txt")):
        try:
            content = path.read_text(encoding="utf-8")
            prompts[path.stem] = content
        except OSError as exc:
            logger.error("Failed to read prompt file %s: %s", path, exc)
    return prompts


async def _get_existing_tables(conn: AsyncConnection) -> set[str]:
    result = await conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in result.fetchall()}


async def _get_existing_columns(conn: AsyncConnection, table_name: str) -> Dict[str, str]:
    result = await conn.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table_name},
    )
    return {row[0]: row[1] for row in result.fetchall()}


async def _ensure_tables(conn: AsyncConnection, base, existing_tables: set[str]) -> None:
    """Create missing tables then add any new columns declared in the models."""
    metadata = base.metadata

    missing_any = any(t not in existing_tables for t in metadata.tables)
    if missing_any:
        await conn.run_sync(lambda c: metadata.create_all(c, checkfirst=True))
        for table_name in metadata.tables:
            if table_name not in existing_tables:
                logger.info("Created table: %s", table_name)

    for table_name, table in metadata.tables.items():
        db_cols = await _get_existing_columns(conn, table_name)
        for col in table.columns:
            col_name = col.key
            if col_name not in db_cols:
                col_type_sql = col.type.compile(dialect=conn.dialect)
                nullable_clause = "NULL" if col.nullable else "NOT NULL DEFAULT ''"
                logger.info("Adding column %s.%s (%s)", table_name, col_name, col_type_sql)
                await conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN IF NOT EXISTS {col_name} {col_type_sql} {nullable_clause}"
                    )
                )


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

_VERSION_TABLE = "schema_migration_version"


async def _ensure_version_table(conn: AsyncConnection) -> None:
    """Create the migration version tracking table if it does not exist."""
    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_VERSION_TABLE} (
                id         INTEGER PRIMARY KEY DEFAULT 1,
                version    INTEGER NOT NULL DEFAULT 0,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT single_row CHECK (id = 1)
            )
            """
        )
    )
    result = await conn.execute(text(f"SELECT COUNT(*) FROM {_VERSION_TABLE}"))
    if result.scalar() == 0:
        await conn.execute(
            text(f"INSERT INTO {_VERSION_TABLE} (id, version) VALUES (1, 0)")
        )


async def _get_current_version(conn: AsyncConnection) -> int:
    result = await conn.execute(
        text(f"SELECT version FROM {_VERSION_TABLE} WHERE id = 1")
    )
    row = result.scalar_one_or_none()
    return row if row is not None else 0


async def _set_version(conn: AsyncConnection, version: int) -> None:
    await conn.execute(
        text(f"UPDATE {_VERSION_TABLE} SET version = :v, applied_at = now() WHERE id = 1"),
        {"v": version},
    )


def _split_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL block on semicolons, skipping blanks."""
    return [s.strip() for s in sql.split(";") if s.strip()]


async def run_migrations(engine: AsyncEngine) -> None:
    """
    Detect the current DB schema version and apply all pending migrations.

    Each migration runs in its own transaction.  The version counter is
    incremented atomically with the SQL so a crash leaves the version unchanged
    and the migration will be retried on the next start.
    """
    from src.infra.db.migrations import _MIGRATIONS, LATEST_VERSION

    async with engine.begin() as conn:
        await _ensure_version_table(conn)
        current_version = await _get_current_version(conn)

    if current_version >= LATEST_VERSION:
        logger.info("DB schema is up-to-date (version %d).", current_version)
        return

    pending = sorted(v for v in _MIGRATIONS if v > current_version)
    logger.info(
        "DB schema at version %d - applying %d migration(s) up to version %d.",
        current_version, len(pending), LATEST_VERSION,
    )

    for version in pending:
        sql = _MIGRATIONS[version].strip()
        logger.info("Applying migration v%d ...", version)
        async with engine.begin() as conn:
            for statement in _split_statements(sql):
                if statement:
                    await conn.execute(text(statement))
            await _set_version(conn, version)
        logger.info("Migration v%d applied.", version)

    logger.info("All migrations applied. DB schema is now at version %d.", LATEST_VERSION)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_startup_setup(engine: AsyncEngine) -> None:
    """
    Idempotent startup routine executed on every server start:

    1. Create any missing tables (via SQLAlchemy create_all).
    2. Add columns present in models but absent from the DB.
    3. Apply all pending versioned SQL migrations.
    4. Synchronise system-prompt rows with on-disk .txt files.
    """
    logger.info("Running startup database setup...")

    async with engine.begin() as conn:
        existing = await _get_existing_tables(conn)
        logger.info("Existing tables: %d found", len(existing))

        await _ensure_tables(conn, ResourceBase, existing)
        await _ensure_tables(conn, LogBase, existing)
        await _ensure_tables(conn, SyncTrackerBase, existing)

    logger.info("Table schema verified / updated.")

    await run_migrations(engine)

    await _sync_prompts(engine)

    logger.info("Startup database setup complete.")


async def _sync_prompts(engine: AsyncEngine) -> None:
    """
    Keep system-prompt rows in sync with on-disk .txt files.
    Rows for deleted files are preserved for historical log references.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from src.infra.log.models import Prompt

    disk_prompts = _load_prompts_from_disk()
    if not disk_prompts:
        logger.warning("No prompt files found on disk - skipping prompt sync.")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(text("SELECT name, content FROM log_prompt"))
            db_rows: Dict[str, str] = {row[0]: row[1] for row in result.fetchall()}

            inserted = updated = skipped = 0

            for name, content in disk_prompts.items():
                if name not in db_rows:
                    session.add(Prompt(name=name, content=content))
                    inserted += 1
                    logger.info("Prompt inserted: %s", name)
                elif _sha256(content) != _sha256(db_rows[name]):
                    await session.execute(
                        text(
                            "UPDATE log_prompt SET content = :content, updated_at = now() WHERE name = :name"
                        ),
                        {"content": content, "name": name},
                    )
                    updated += 1
                    logger.info("Prompt updated: %s", name)
                else:
                    skipped += 1

            for db_name in db_rows:
                if db_name not in disk_prompts:
                    logger.warning(
                        "Prompt '%s' exists in DB but has no corresponding file - "
                        "row kept for historical reference.",
                        db_name,
                    )

    logger.info(
        "Prompt sync complete: %d inserted, %d updated, %d unchanged.",
        inserted, updated, skipped,
    )
