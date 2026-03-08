"""
Asset setup service.

Orchestrates the sequential, idempotent startup sequence that ensures all
static assets required by the application are present and ready:

1. Embedding model        — download from HuggingFace Hub if absent.
2. Platon docs            — download MDX files from GitHub if absent or changed.
3. Component metadata     — (re)generate metadata.json when docs were updated.
4. Platon docs RAG        — populate the pgvector table from MDX files if empty
                            or if the docs were just refreshed.

Each step is independent: a failure is logged and the setup flag is cleared
so that downstream steps that require a previous step are gracefully skipped.

Blocking I/O (downloads) is always executed inside ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.core.config_app import settings
from src.infra.assets.embedding_model_downloader import (
    download_embedding_model,
    is_model_present,
)
from src.infra.assets.platon_docs_downloader import (
    check_docs_changed,
    download_platon_docs,
    is_docs_present,
)
from src.infra.assets.components_metadata_builder import (
    is_metadata_present,
    rebuild_components_metadata,
)

logger = logging.getLogger(__name__)


async def run_asset_setup() -> bool:
    """
    Run the full asset-readiness sequence at server startup.

    The sequence is linear: a failing step sets an internal flag that prevents
    dependent downstream steps from running, so the server still starts even
    when GitHub or HuggingFace are unreachable.

    Returns:
        True when the embedding model is ready (either pre-existing or freshly
        downloaded), False otherwise.  Callers must not attempt to load the
        embedding model when this returns False.
    """
    embedding_ready = await _ensure_embedding_model()

    docs_ready, docs_changed = await _ensure_platon_docs()

    if docs_ready:
        await _ensure_components_metadata(docs_changed=docs_changed)

    if docs_ready and embedding_ready:
        await _ensure_platon_docs_vectors(docs_changed=docs_changed)
    else:
        logger.warning(
            "Asset setup: one or more assets are missing — "
            "Platon docs vector population is skipped."
        )

    return embedding_ready


# ---------------------------------------------------------------------------
# Step 1: Embedding model
# ---------------------------------------------------------------------------

async def _ensure_embedding_model() -> bool:
    if is_model_present():
        logger.info("Asset setup [1/4]: embedding model already present.")
        return True

    logger.info("Asset setup [1/4]: embedding model not found — downloading…")
    try:
        await asyncio.to_thread(download_embedding_model)
        logger.info("Asset setup [1/4]: embedding model downloaded successfully.")
        return True
    except RuntimeError as exc:
        logger.error(
            "Asset setup [1/4]: embedding model download failed — %s", exc, exc_info=True
        )
        return False


# ---------------------------------------------------------------------------
# Step 2: Platon documentation files
# ---------------------------------------------------------------------------

async def _ensure_platon_docs() -> tuple[bool, bool]:
    """
    Ensure the Platon docs corpus is present and up-to-date.

    Returns:
        (docs_ready, docs_changed) where *docs_changed* is True when a fresh
        download was performed (so dependent steps know a rebuild is needed).
    """
    docs_present = is_docs_present()

    try:
        changed, remote_sha = await asyncio.to_thread(
            check_docs_changed, settings.GITHUB_TOKEN
        )
    except RuntimeError as exc:
        logger.warning(
            "Asset setup [2/4]: cannot reach GitHub to check for doc updates — %s. "
            "Using local copy as-is.",
            exc,
        )
        return docs_present, False

    if docs_present and not changed:
        logger.info("Asset setup [2/4]: Platon docs are present and up-to-date.")
        return True, False

    if changed and docs_present:
        logger.info("Asset setup [2/4]: Platon docs changed upstream — re-downloading…")
    else:
        logger.info("Asset setup [2/4]: Platon docs not found — downloading…")

    try:
        downloaded, _ = await asyncio.to_thread(
            download_platon_docs, settings.GITHUB_TOKEN
        )
        logger.info("Asset setup [2/4]: Platon docs ready — %d files.", downloaded)
        return True, True
    except RuntimeError as exc:
        logger.error(
            "Asset setup [2/4]: Platon docs download failed — %s", exc, exc_info=True
        )
        return False, False


# ---------------------------------------------------------------------------
# Step 3: Component metadata.json
# ---------------------------------------------------------------------------

async def _ensure_components_metadata(docs_changed: bool) -> None:
    """
    Generate (or regenerate) the components/metadata.json file.

    Rebuilds unconditionally when docs were just refreshed.  On a fresh
    install where the file is absent it also rebuilds.
    """
    if not docs_changed and is_metadata_present():
        logger.info("Asset setup [3/4]: component metadata is present and up-to-date.")
        return

    reason = "docs updated" if docs_changed else "metadata not found"
    logger.info("Asset setup [3/4]: rebuilding component metadata (%s)…", reason)
    try:
        entries = await asyncio.to_thread(rebuild_components_metadata)
        logger.info(
            "Asset setup [3/4]: component metadata rebuilt — %d entries.", len(entries)
        )
    except Exception as exc:
        logger.error(
            "Asset setup [3/4]: component metadata rebuild failed — %s", exc, exc_info=True
        )


# ---------------------------------------------------------------------------
# Step 4: Platon docs pgvector table
# ---------------------------------------------------------------------------

async def _ensure_platon_docs_vectors(docs_changed: bool) -> None:
    """
    Ensure the Platon docs pgvector table is populated.

    Forces a full repopulation when docs were just refreshed so that stale
    embeddings do not persist.
    """
    logger.info("Asset setup [4/4]: verifying Platon docs vector table…")
    try:
        from src.infra.vector.platon_docs_vector_service import ensure_populated
        await ensure_populated(force_rebuild=docs_changed)
        logger.info("Asset setup [4/4]: Platon docs vector table is ready.")
    except Exception as exc:
        logger.error(
            "Asset setup [4/4]: Platon docs vector population failed — %s", exc, exc_info=True
        )

