"""
Exercise vector synchronisation service.

Three resource kinds are embedded:
- EXERCICE        — standalone exercises (no template_id in DB)
- TEMPLATE_EXO    — exercises based on a template (template_id IS NOT NULL)
- TEMPLATE        — configurable templates

Key distinction between TEMPLATE and TEMPLATE_EXO
--------------------------------------------------
A **TEMPLATE** (configurable) has a ``main.plc`` file that describes its
input parameters (name, description, type, default values).  We fetch that
file to enrich the embedding with parameter semantics.

A **TEMPLATE_EXO** is a filled-in instance of a template.  It does NOT have
a ``main.plc`` file.  Instead, it has a ``main.plo`` file that contains the
concrete values each parameter was assigned for this specific instance
(e.g. ``{"question": "Calculez ...", "reponse": 42}``).
To make the TEMPLATE_EXO embedding semantically distinct from both its parent
and other instances, we:
  1. Read ``main.plo`` from the template_exo's own platon_id → filled values.
  2. Read ``main.plc`` from the parent template's platon_id → param descriptions.
  3. Merge both into ``FilledTemplateParameter`` objects that combine each
     parameter's human description with its concrete value.

Lifecycle
---------
1. ``ensure_populated``   — startup hook.  Full population if empty, else
   incremental from last recorded sync timestamp.
2. ``run_incremental_sync`` — daily scheduler hook.
3. ``run_from_prefetched`` — called by resource_sync_service to reuse already-
   fetched Platon data and avoid redundant API calls.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config_app import settings
from src.core.path_constants import EMBED_MODEL_PATH
from src.infra.platon.cached_platon_client import CachedPlatonClient
from src.infra.vector.models import (
    ExerciseMetadata,
    ExerciseParts,
    FilledTemplateParameter,
    TemplateParameter,
)
from src.infra.vector.sync_tracker import get_last_sync, set_last_sync
from src.infra.vector.text_builder import build_exercise_text, build_template_exo_text, build_template_text
from src.infra.vector.vector_utils import (
    physical_table_name,
    table_row_count,
    validate_table_name,
)
from src.services.rag.embedding_types import EmbeddingKind

logger = logging.getLogger(__name__)

_JOB_NAME = "exercise_vector_sync"
_TASK_INSTRUCTION = (
    "Instruct: Retrieve relevant exercises, templates, and examples matching the query.\nQuery: "
)


# ---------------------------------------------------------------------------
# Internal data transfer types
# ---------------------------------------------------------------------------

class _ResourceRow:
    """One row fetched from the local DB, ready for embedding."""

    __slots__ = ("db_id", "platon_id", "kind", "template_platon_id")

    def __init__(
        self,
        db_id: UUID,
        platon_id: str,
        kind: EmbeddingKind,
        template_platon_id: Optional[str] = None,
    ) -> None:
        self.db_id = db_id
        self.platon_id = platon_id
        self.kind = kind
        self.template_platon_id = template_platon_id


# ---------------------------------------------------------------------------
# Terminal progress
# ---------------------------------------------------------------------------

def _print_item(done: int, total: int, kind: str, platon_id: str, ok: bool, elapsed: float) -> None:
    """Print one line per completed resource — visible immediately in Docker logs."""
    pct = int(done / total * 100) if total else 100
    status = "✓" if ok else "✗"
    print(
        f"  {status} [{done:>4}/{total}  {pct:>3}%]  {kind:<12}  {platon_id[:8]}…  {elapsed:.2f}s",
        flush=True,
    )


def _print_summary(done: int, total: int, ok: int, failed: int, wall: float) -> None:
    bar_filled = int(30 * done / total) if total else 30
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    print(
        f"\n  [{bar}]  {done}/{total} processed  "
        f"({ok} embedded, {failed} failed)  total {wall:.1f}s\n",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Platon data enrichment — all calls go through CachedPlatonClient
# ---------------------------------------------------------------------------

async def _fetch_metadata(
    platon_id: str,
    client: CachedPlatonClient,
    admin_token: Optional[str],
) -> ExerciseMetadata:
    info = await client.get_resource(platon_id, token=admin_token)
    topics = [t["name"] for t in info.get("topics", []) if isinstance(t, dict) and t.get("name")] or None
    levels = [lv["name"] for lv in info.get("levels", []) if isinstance(lv, dict) and lv.get("name")] or None
    return ExerciseMetadata(
        db_id=UUID(info["id"]),
        platon_id=platon_id,
        name=info.get("name") or "",
        cercle=info.get("parentId") or "",
        description=info.get("desc"),
        topics=topics,
        levels=levels,
    )


async def _fetch_parts(
    platon_id: str,
    client: CachedPlatonClient,
    admin_token: Optional[str],
) -> ExerciseParts:
    compiled = await client.compile_resource_json(platon_id, token=admin_token)
    variables = compiled.get("variables", {}) if isinstance(compiled, dict) else {}
    return ExerciseParts(
        title=variables.get("title") or "",
        statement=variables.get("statement") or "",
        form=variables.get("form") or "",
        solution=variables.get("solution"),
    )


async def _fetch_template_parameters(
    template_platon_id: str,
    client: CachedPlatonClient,
    admin_token: Optional[str],
) -> List[TemplateParameter]:
    try:
        raw = await client.get_file_content(template_platon_id, "main.plc", "latest", token=admin_token)
        data = json.loads(raw)
        params: List[TemplateParameter] = []
        if isinstance(data, dict):
            for var in data.get("inputs", []):
                if isinstance(var, dict) and var.get("name"):
                    params.append(TemplateParameter(
                        name=var["name"],
                        description=var.get("description"),
                        type=var.get("type"),
                        default_value=var.get("value"),
                    ))
        return params
    except Exception as exc:
        logger.warning("Could not read main.plc for %s: %s", template_platon_id, exc)
        return []


async def _fetch_filled_parameters(
    template_exo_platon_id: str,
    parent_template_platon_id: str,
    client: CachedPlatonClient,
    admin_token: Optional[str],
) -> List[FilledTemplateParameter]:
    filled_values: Dict[str, Any] = {}
    try:
        plo_raw = await client.get_file_content(template_exo_platon_id, "main.plo", "latest", token=admin_token)
        parsed = json.loads(plo_raw)
        if isinstance(parsed, dict):
            filled_values = parsed
    except Exception as exc:
        logger.warning("Could not read main.plo for %s: %s", template_exo_platon_id, exc)

    parent_params = await _fetch_template_parameters(parent_template_platon_id, client, admin_token)
    param_meta: Dict[str, TemplateParameter] = {p.name: p for p in parent_params}

    result: List[FilledTemplateParameter] = []
    all_names = list(param_meta.keys()) or list(filled_values.keys())
    for name in all_names:
        meta = param_meta.get(name)
        result.append(FilledTemplateParameter(
            name=name,
            filled_value=str(filled_values[name]) if name in filled_values else None,
            description=meta.description if meta else None,
            type=meta.type if meta else None,
        ))
    return result


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

def _build_embed_model() -> HuggingFaceEmbedding:
    return HuggingFaceEmbedding(model_name=str(EMBED_MODEL_PATH), normalize=True)


def _make_node(
    content: str,
    metadata: Dict[str, Any],
    node_id: str,
    embed_model: HuggingFaceEmbedding,
) -> TextNode:
    embedding = embed_model.get_text_embedding(_TASK_INSTRUCTION + content)
    return TextNode(text=content, metadata=metadata, embedding=embedding, id_=node_id)


async def _build_node_for_resource(
    row: _ResourceRow,
    client: CachedPlatonClient,
    embed_model: HuggingFaceEmbedding,
    admin_token: Optional[str],
) -> Optional[TextNode]:
    """
    Build one TextNode for any resource kind.

    All Platon calls go through ``CachedPlatonClient`` — results are served
    from Redis on subsequent calls, making restarts virtually free.
    """
    try:
        metadata = await _fetch_metadata(row.platon_id, client, admin_token)
        metadata.db_id = row.db_id
        parts = await _fetch_parts(row.platon_id, client, admin_token)

        if row.kind == EmbeddingKind.EXERCICE:
            content = build_exercise_text(metadata, parts, "Exercice")
            node_id = f"exercise_{row.platon_id}"

        elif row.kind == EmbeddingKind.TEMPLATE:
            parameters = await _fetch_template_parameters(row.platon_id, client, admin_token)
            content = build_template_text(metadata, parts, parameters, is_configurable=True)
            node_id = f"template_{row.platon_id}"

        else:  # TEMPLATE_EXO
            filled = await _fetch_filled_parameters(
                row.platon_id, row.template_platon_id or "", client, admin_token
            )
            content = build_template_exo_text(metadata, parts, filled)
            node_id = f"template_{row.platon_id}"

        return _make_node(
            content=content,
            metadata={
                "db_id": str(row.db_id),
                "platon_id": row.platon_id,
                "name": metadata.name,
                "kind": row.kind.value,
            },
            node_id=node_id,
            embed_model=embed_model,
        )

    except Exception as exc:
        logger.warning("Failed to build node for %s %s: %s", row.kind.value, row.platon_id, exc)
        return None


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

async def _fetch_rows_from_db(
    engine: AsyncEngine,
    since: Optional[datetime] = None,
) -> List[_ResourceRow]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        params = {"since": since} if since else {}

        standalone = await session.execute(
            text(
                "SELECT id, platon_id FROM exercise WHERE template_id IS NULL"
                + (" AND last_modified_at >= :since" if since else "")
            ),
            params,
        )
        tpl_exo = await session.execute(
            text(
                "SELECT e.id, e.platon_id, t.platon_id AS template_platon_id "
                "FROM exercise e JOIN template t ON t.id = e.template_id "
                "WHERE e.template_id IS NOT NULL"
                + (" AND e.last_modified_at >= :since" if since else "")
            ),
            params,
        )
        templates = await session.execute(
            text(
                "SELECT id, platon_id FROM template"
                + (" WHERE last_modified_at >= :since" if since else "")
            ),
            params,
        )

    rows: List[_ResourceRow] = []
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
# Vector store helpers
# ---------------------------------------------------------------------------

def _build_vector_store(table_name: str, embed_dim: int) -> PGVectorStore:
    return PGVectorStore.from_params(
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        password=settings.POSTGRES_PASSWORD,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        table_name=table_name,
        embed_dim=embed_dim,
    )


def _get_dsn() -> dict:
    return {
        "host": settings.POSTGRES_HOST,
        "port": settings.POSTGRES_PORT,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
        "database": settings.POSTGRES_DB,
    }


# ---------------------------------------------------------------------------
# Core sync engine
# ---------------------------------------------------------------------------

async def _build_nodes(
    rows: List[_ResourceRow],
    client: CachedPlatonClient,
    embed_model: HuggingFaceEmbedding,
    admin_token: Optional[str],
) -> Tuple[List[TextNode], int]:
    total = len(rows)
    nodes: List[TextNode] = []
    failed = 0
    wall_start = time.monotonic()

    for i, row in enumerate(rows, start=1):
        item_start = time.monotonic()
        node = await _build_node_for_resource(row, client, embed_model, admin_token)
        item_elapsed = time.monotonic() - item_start
        if node:
            nodes.append(node)
            _print_item(i, total, row.kind.value, row.platon_id, ok=True, elapsed=item_elapsed)
        else:
            failed += 1
            _print_item(i, total, row.kind.value, row.platon_id, ok=False, elapsed=item_elapsed)

    _print_summary(total, total, len(nodes), failed, time.monotonic() - wall_start)
    return nodes, failed


async def _commit_nodes(nodes: List[TextNode], embed_model: HuggingFaceEmbedding, full: bool) -> None:
    probe = embed_model.get_text_embedding("probe")
    embed_dim = len(probe)
    table_name = settings.RAG_TABLE_NAME
    vector_store = _build_vector_store(table_name, embed_dim)

    print(f"  → Committing {len(nodes)} node(s) to vector store…", flush=True)
    if full:
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex(nodes=nodes, storage_context=storage_context, embed_model=embed_model)
    else:
        vector_store.add(nodes)


async def _run_sync(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    since: Optional[datetime],
    full: bool,
    admin_token: Optional[str] = None,
    prefetched_rows: Optional[List[_ResourceRow]] = None,
) -> None:
    started_at = datetime.now(timezone.utc)
    rows = prefetched_rows if prefetched_rows is not None else await _fetch_rows_from_db(engine, since)

    if not rows:
        logger.info("No resources to embed — vector store is up to date.")
        await set_last_sync(engine, _JOB_NAME, started_at)
        return

    counts = {k: sum(1 for r in rows if r.kind == k) for k in EmbeddingKind}
    print(
        f"\n  Vector sync: {len(rows)} resource(s) "
        f"[exercises={counts.get(EmbeddingKind.EXERCICE, 0)}, "
        f"templates={counts.get(EmbeddingKind.TEMPLATE, 0)}, "
        f"template_exos={counts.get(EmbeddingKind.TEMPLATE_EXO, 0)}]",
        flush=True,
    )

    embed_model = _build_embed_model()
    nodes, failed = await _build_nodes(rows, client, embed_model, admin_token)

    if nodes:
        await _commit_nodes(nodes, embed_model, full)

    logger.info("Exercise vector sync complete: %d embedded, %d failed.", len(nodes), failed)
    await set_last_sync(engine, _JOB_NAME, started_at)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_from_prefetched(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    rows: List[_ResourceRow],
    admin_token: Optional[str] = None,
) -> None:
    """
    Embed a pre-determined set of rows.  Called by resource_sync_service after
    a DB sync so no redundant resource listing is made.  All Platon data calls
    (get_resource, compile, file reads) are served from the Redis cache that
    was populated during the DB sync pass.
    """
    await _run_sync(engine, client, since=None, full=False, admin_token=admin_token, prefetched_rows=rows)


async def run_full_rebuild(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    admin_token: Optional[str] = None,
) -> None:
    logger.info("Running full exercise vector rebuild…")
    await _run_sync(engine, client, since=None, full=True, admin_token=admin_token)


async def ensure_populated(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    admin_token: Optional[str] = None,
) -> None:
    """
    Startup hook.

    - Empty table  → full population.
    - Existing rows → incremental sync since last recorded timestamp.

    All Platon data requests are served from Redis if the cache was populated
    during a prior startup within the TTL window.
    """
    table_name = settings.RAG_TABLE_NAME
    physical = physical_table_name(table_name)
    validate_table_name(physical)

    count = await table_row_count(_get_dsn(), physical)

    if count is None or count == 0:
        logger.info("Vector table is empty — running full initial population.")
        await _run_sync(engine, client, since=None, full=True, admin_token=admin_token)
    else:
        last_sync = await get_last_sync(engine, _JOB_NAME)
        if last_sync is None:
            logger.info(
                "Vector table has %d rows but no sync record — assuming current. Recording timestamp.",
                count,
            )
            await set_last_sync(engine, _JOB_NAME, datetime.now(timezone.utc))
            return
        logger.info("Vector table has %d rows — incremental sync since %s.", count, last_sync)
        await _run_sync(engine, client, since=last_sync, full=False, admin_token=admin_token)


async def run_incremental_sync(
    engine: AsyncEngine,
    client: CachedPlatonClient,
    admin_token: Optional[str] = None,
) -> None:
    last_sync = await get_last_sync(engine, _JOB_NAME)
    logger.info("Running daily exercise vector sync (since=%s).", last_sync)
    await _run_sync(engine, client, since=last_sync, full=False, admin_token=admin_token)
