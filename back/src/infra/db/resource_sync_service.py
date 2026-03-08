"""
Resource synchronisation service.

Fetches the current state of exercises, templates, and their component links
from the Platon API and upserts them into the local database.

Algorithm
---------
- **First run** (resource tables are empty): full fetch, all resources.
- **Subsequent runs** (tables already have rows): delta fetch only — Platon
  returns resources updated within the last N days.  Only those ids are
  upserted and re-embedded.

Every Platon API call that returns re-usable data (compile, get_resource,
get_file_content) goes through ``CachedPlatonClient`` so that the result is
written to Redis on the first call and read back on all subsequent calls
within the TTL window — eliminating redundant Platon requests across restarts.

This service is idempotent: running it multiple times produces the same result.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.expression import bindparam

from src.core.path_constants import COMPONENT_METADATA_PATH
from src.infra.platon.cached_platon_client import CachedPlatonClient
from src.infra.vector.sync_tracker import get_last_sync, set_last_sync
from src.services.rag.embedding_types import EmbeddingKind

logger = logging.getLogger(__name__)

_JOB_NAME = "resource_sync"


# ---------------------------------------------------------------------------
# Terminal progress helpers
# ---------------------------------------------------------------------------

class _Progress:
    """Single-line terminal progress renderer with elapsed time."""

    def __init__(self, total: int, label: str) -> None:
        self._total = max(total, 1)
        self._label = label
        self._done = 0
        self._start = time.monotonic()
        self._render()

    def advance(self, label: Optional[str] = None) -> None:
        self._done += 1
        if label:
            self._label = label
        self._render()

    def finish(self, label: Optional[str] = None) -> None:
        self._done = self._total
        elapsed = time.monotonic() - self._start
        final_label = label or self._label
        bar = "█" * 30
        line = (
            f"\r  ✓ [{bar}] {self._total}/{self._total} (100%)"
            f"  {final_label:<55}  {elapsed:.1f}s\n"
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    def _render(self) -> None:
        pct = int(self._done / self._total * 100)
        filled = int(30 * self._done / self._total)
        bar = "█" * filled + "░" * (30 - filled)
        elapsed = time.monotonic() - self._start
        line = (
            f"\r  [{bar}] {self._done}/{self._total} ({pct}%)"
            f"  {self._label:<55}  {elapsed:.1f}s"
        )
        sys.stdout.write(line)
        sys.stdout.flush()


def _section(title: str) -> None:
    print(f"\n  ── {title}", flush=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _days_since(since: Optional[datetime]) -> Optional[int]:
    if since is None:
        return None
    delta = datetime.now(timezone.utc) - since
    return max(1, delta.days + 1)


# ---------------------------------------------------------------------------
# Platon resource listing
# ---------------------------------------------------------------------------

async def _fetch_all_resources(
    client: CachedPlatonClient,
    since: Optional[datetime],
    admin_token: Optional[str],
) -> List[Dict[str, Any]]:
    period = _days_since(since)

    async def _paginate(configurable: Optional[bool]) -> List[Dict[str, Any]]:
        resources: List[Dict[str, Any]] = []
        offset = 0
        limit = 50
        while True:
            batch = await client.get_ready_exercises(
                offset=offset,
                limit=limit,
                configurable=configurable,
                period=period,
                token=admin_token,
            )
            if not batch:
                break
            resources.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return resources

    templates = await _paginate(configurable=True)
    template_ids = {r["id"] for r in templates if r.get("id")}
    all_ready = await _paginate(configurable=None)

    for r in templates:
        r["_is_template"] = True

    exercises: List[Dict[str, Any]] = []
    for r in all_ready:
        if r.get("id") in template_ids:
            continue
        r["_is_template"] = False
        exercises.append(r)

    return templates + exercises


# ---------------------------------------------------------------------------
# DB population steps
# ---------------------------------------------------------------------------

async def _sync_components(session: AsyncSession) -> int:
    with open(COMPONENT_METADATA_PATH, encoding="utf-8") as fh:
        components: List[Dict[str, Any]] = json.load(fh)

    stmt = text(
        """
        INSERT INTO component (tag, name, category, description, usage, properties, url, created_at, last_modified_at)
        VALUES (:tag, :name, :category, :description, :usage, :properties, :url, now(), now())
        ON CONFLICT (tag) DO UPDATE
            SET name             = EXCLUDED.name,
                category         = EXCLUDED.category,
                description      = EXCLUDED.description,
                usage            = EXCLUDED.usage,
                properties       = EXCLUDED.properties,
                url              = EXCLUDED.url,
                last_modified_at = now()
        """
    ).bindparams(bindparam("properties", type_=JSONB))

    for comp in components:
        await session.execute(stmt, {
            "tag": comp["tag"],
            "name": comp["name"],
            "category": comp["category"],
            "description": comp.get("description"),
            "usage": comp.get("usage"),
            "properties": comp.get("properties", {}),
            "url": comp.get("url"),
        })
    await session.commit()
    return len(components)


async def _sync_templates(
    session: AsyncSession,
    resources: List[Dict[str, Any]],
) -> Dict[str, str]:
    template_map: Dict[str, str] = {}
    for r in resources:
        if not r.get("_is_template"):
            continue
        result = await session.execute(
            text(
                """
                INSERT INTO template (platon_id, created_at, last_modified_at)
                VALUES (:platon_id, :created_at, :updated_at)
                ON CONFLICT (platon_id) DO UPDATE
                    SET last_modified_at = EXCLUDED.last_modified_at
                RETURNING id
                """
            ),
            {
                "platon_id": r["id"],
                "created_at": _parse_dt(r.get("createdAt")),
                "updated_at": _parse_dt(r.get("updatedAt")),
            },
        )
        row = result.fetchone()
        if row:
            template_map[r["id"]] = str(row.id)
    await session.commit()
    return template_map


async def _sync_exercises(
    session: AsyncSession,
    resources: List[Dict[str, Any]],
    template_map: Dict[str, str],
) -> int:
    count = 0
    for r in resources:
        if r.get("_is_template"):
            continue
        tpl_id = template_map.get(r.get("templateId"))
        await session.execute(
            text(
                """
                INSERT INTO exercise (platon_id, template_id, created_at, last_modified_at)
                VALUES (:platon_id, :template_id, :created_at, :updated_at)
                ON CONFLICT (platon_id) DO UPDATE
                    SET template_id      = EXCLUDED.template_id,
                        last_modified_at = EXCLUDED.last_modified_at
                """
            ),
            {
                "platon_id": r["id"],
                "template_id": tpl_id,
                "created_at": _parse_dt(r.get("createdAt")),
                "updated_at": _parse_dt(r.get("updatedAt")),
            },
        )
        count += 1
    await session.commit()
    return count


async def _sync_component_links(
    session: AsyncSession,
    client: CachedPlatonClient,
    synced_exercise_platon_ids: List[str],
    synced_template_platon_ids: List[str],
    admin_token: Optional[str],
) -> Tuple[int, int]:
    """
    Populate component link tables for the synced resources.

    compile_resource_json() goes through the cached client — the result is
    written to Redis on first call and served from cache on subsequent ones.
    """
    if not synced_exercise_platon_ids and not synced_template_platon_ids:
        return 0, 0

    comp_result = await session.execute(text("SELECT id, tag FROM component"))
    component_map: Dict[str, Any] = {row.tag: row.id for row in comp_result.fetchall()}

    if not component_map:
        logger.warning("No components in DB — skipping component link population.")
        return 0, 0

    exercise_links = 0
    template_links = 0
    total = len(synced_exercise_platon_ids) + len(synced_template_platon_ids)
    progress = _Progress(total, "component links")

    if synced_exercise_platon_ids:
        id_list = ", ".join(f"'{pid}'" for pid in synced_exercise_platon_ids)
        exercises = (
            await session.execute(
                text(f"SELECT id, platon_id FROM exercise WHERE platon_id::text IN ({id_list})")
            )
        ).fetchall()
        for ex in exercises:
            try:
                compiled = await client.compile_resource_json(str(ex.platon_id), token=admin_token)
                selectors = await client.extract_exercise_components(
                    exercise_id=str(ex.platon_id),
                    token=admin_token,
                    compiled_json=compiled,
                )
                for selector in selectors:
                    if selector in component_map:
                        await session.execute(
                            text(
                                "INSERT INTO exercise_component_link (exercise_id, component_id) "
                                "VALUES (:eid, :cid) ON CONFLICT DO NOTHING"
                            ),
                            {"eid": ex.id, "cid": component_map[selector]},
                        )
                        exercise_links += 1
            except Exception as exc:
                logger.warning("Could not extract components for exercise %s: %s", ex.platon_id, exc)
            progress.advance(f"exercise {str(ex.platon_id)[:8]}…")

    if synced_template_platon_ids:
        id_list = ", ".join(f"'{pid}'" for pid in synced_template_platon_ids)
        templates = (
            await session.execute(
                text(f"SELECT id, platon_id FROM template WHERE platon_id::text IN ({id_list})")
            )
        ).fetchall()
        for tpl in templates:
            try:
                compiled = await client.compile_resource_json(str(tpl.platon_id), token=admin_token)
                for var_val in compiled.get("variables", {}).values():
                    if isinstance(var_val, dict) and "cid" in var_val and "selector" in var_val:
                        selector = var_val.get("selector", "")
                        if selector and selector in component_map:
                            await session.execute(
                                text(
                                    "INSERT INTO template_component_link (template_id, component_id) "
                                    "VALUES (:tid, :cid) ON CONFLICT DO NOTHING"
                                ),
                                {"tid": tpl.id, "cid": component_map[selector]},
                            )
                            template_links += 1
            except Exception as exc:
                logger.warning("Could not extract components for template %s: %s", tpl.platon_id, exc)
            progress.advance(f"template {str(tpl.platon_id)[:8]}…")

    progress.finish(f"component links — {exercise_links} ex, {template_links} tpl")
    await session.commit()
    return exercise_links, template_links


# ---------------------------------------------------------------------------
# Resource row builder (for vector service)
# ---------------------------------------------------------------------------

async def _build_resource_rows_from_db(
    session: AsyncSession,
    synced_platon_ids: List[str],
) -> List[Any]:
    from src.infra.vector.exercise_vector_service import _ResourceRow

    if not synced_platon_ids:
        return []

    id_list = ", ".join(f"'{pid}'" for pid in synced_platon_ids)

    standalone = await session.execute(
        text(
            f"SELECT id, platon_id FROM exercise "
            f"WHERE template_id IS NULL AND platon_id::text IN ({id_list})"
        )
    )
    tpl_exo = await session.execute(
        text(
            f"""
            SELECT e.id, e.platon_id, t.platon_id AS template_platon_id
            FROM exercise e
            JOIN template t ON t.id = e.template_id
            WHERE e.template_id IS NOT NULL AND e.platon_id::text IN ({id_list})
            """
        )
    )
    templates = await session.execute(
        text(f"SELECT id, platon_id FROM template WHERE platon_id::text IN ({id_list})")
    )

    rows = []
    for r in standalone.fetchall():
        rows.append(_ResourceRow(r.id, str(r.platon_id), EmbeddingKind.EXERCICE))
    for r in tpl_exo.fetchall():
        rows.append(_ResourceRow(
            r.id, str(r.platon_id), EmbeddingKind.TEMPLATE_EXO,
            template_platon_id=str(r.template_platon_id),
        ))
    for r in templates.fetchall():
        rows.append(_ResourceRow(r.id, str(r.platon_id), EmbeddingKind.TEMPLATE))
    return rows


# ---------------------------------------------------------------------------
# First-run detection
# ---------------------------------------------------------------------------

async def _is_first_run(engine: AsyncEngine) -> bool:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        ex_count = (await session.execute(text("SELECT COUNT(*) FROM exercise"))).scalar()
        tpl_count = (await session.execute(text("SELECT COUNT(*) FROM template"))).scalar()
    return (ex_count or 0) == 0 and (tpl_count or 0) == 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_resource_sync(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    admin_token: Optional[str] = None,
    sync_vectors: bool = True,
) -> None:
    """
    Full resource synchronisation.

    First run (empty tables)
    ~~~~~~~~~~~~~~~~~~~~~~~~
    1. Upsert all components from local metadata.json.
    2. Fetch the full resource catalogue from Platon.
    3. Upsert templates and exercises.
    4. Build component link tables (compile calls are cached in Redis).

    Subsequent runs (delta)
    ~~~~~~~~~~~~~~~~~~~~~~~
    Same pipeline but only resources updated since the last sync are fetched.

    In both cases, if *sync_vectors* is True, the vector service is triggered
    for the same set of resources — no resource is listed twice from Platon.

    Args:
        engine: SQLAlchemy async engine.
        client: Cache-aware Platon client (reads from Redis before calling Platon).
        admin_token: Admin access token.
        sync_vectors: When True, also update the vector store for synced resources.
    """
    from src.infra.vector.exercise_vector_service import run_from_prefetched

    started_at = datetime.now(timezone.utc)
    first_run = await _is_first_run(engine)
    last_sync = await get_last_sync(engine, _JOB_NAME)

    if first_run:
        print("\n  ┌─ Resource sync: FIRST RUN ──────────────────────────────────────────┐", flush=True)
    else:
        since_str = last_sync.isoformat() if last_sync else "unknown"
        print(f"\n  ┌─ Resource sync: DELTA since {since_str} ────────┐", flush=True)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        _section("1/4 — components")
        component_count = await _sync_components(session)
        print(f"  ✓ {component_count} component(s) synced.", flush=True)

        _section("2/4 — fetching resources from Platon")
        resources = await _fetch_all_resources(
            client,
            since=None if first_run else last_sync,
            admin_token=admin_token,
        )
        templates_list = [r for r in resources if r.get("_is_template")]
        exercises_list = [r for r in resources if not r.get("_is_template")]
        print(
            f"  ✓ {len(resources)} resource(s) fetched: "
            f"{len(templates_list)} template(s), {len(exercises_list)} exercise(s).",
            flush=True,
        )

        _section("3/4 — upserting to database")
        tpl_progress = _Progress(max(len(templates_list), 1), "templates")
        template_map = await _sync_templates(session, resources)
        tpl_progress.finish(f"{len(template_map)} template(s) upserted")

        ex_progress = _Progress(max(len(exercises_list), 1), "exercises")
        exercise_count = await _sync_exercises(session, resources, template_map)
        ex_progress.finish(f"{exercise_count} exercise(s) upserted")

        _section("4/4 — component links")
        synced_exercise_ids = [r["id"] for r in exercises_list if r.get("id")]
        synced_template_ids = list(template_map.keys())
        ex_links, tpl_links = await _sync_component_links(
            session, client,
            synced_exercise_platon_ids=synced_exercise_ids,
            synced_template_platon_ids=synced_template_ids,
            admin_token=admin_token,
        )

        if sync_vectors and resources:
            synced_ids = [r["id"] for r in resources if r.get("id")]
            vector_rows = await _build_resource_rows_from_db(session, synced_ids)
        else:
            vector_rows = []

    await set_last_sync(engine, _JOB_NAME, started_at)
    print("\n  └─ Resource sync complete. ──────────────────────────────────────────┘\n", flush=True)

    if sync_vectors and vector_rows:
        await run_from_prefetched(engine, client, vector_rows, admin_token=admin_token)
