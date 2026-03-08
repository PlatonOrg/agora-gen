"""
Database migration registry.

Each migration is a pure SQL string registered under a sequential integer
version.  The MigrationRunner (in setup_service.py) applies every migration
whose version number is higher than the one stored in the
``schema_migration_version`` table.

Rules for adding a migration
-----------------------------
1. Append a new entry to ``_MIGRATIONS`` with the next integer key.
2. Write idempotent SQL — use ``IF NOT EXISTS``, ``IF EXISTS``, or check-then-act
   patterns so that re-running is always safe.
3. Never delete or renumber existing entries.
4. One logical change per entry (column add, index add, table rename, …).

The runner executes each migration inside its own transaction so a failure
rolls back only the failing step and preserves the version counter for all
previously applied migrations.
"""

from __future__ import annotations

from typing import Dict

_MIGRATIONS: Dict[int, str] = {
    1: """
        ALTER TABLE log_exo_generation_result
            ADD COLUMN IF NOT EXISTS llm_raw_output TEXT;
        ALTER TABLE log_discussion_generation_result
            ADD COLUMN IF NOT EXISTS llm_raw_output TEXT;
    """,
    2: """
        ALTER TABLE log_exo_generation_result
            ADD COLUMN IF NOT EXISTS llm_calls JSONB NULL;
    """,
}

LATEST_VERSION: int = max(_MIGRATIONS.keys()) if _MIGRATIONS else 0

