"""
Platon documentation vector service.

Builds and maintains the pgvector table used by the Platon docs QA pipeline.

Design
------
- The table is populated once from local MDX files.  There is no incremental
  update because the docs corpus is static (baked into the Docker image).
- If the table already contains rows the service does nothing, making it safe
  to call on every server restart.
- A CLI wrapper in scripts/ allows operators to force a full rebuild with the
  ``--recreate`` flag.

Text processing pipeline
------------------------
MDX → strip frontmatter / code blocks / HTML → plain text → sentence-chunk
→ embed in batches → upsert into PGVectorStore.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable, List

from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore

from src.core.config_app import settings
from src.core import path_constants
from src.core.path_constants import PLATON_DOCS_DIR
from src.infra.vector.vector_utils import physical_table_name, table_row_count, validate_table_name

logger = logging.getLogger(__name__)

_DEFAULT_TARGET_CHARS = 900
_DEFAULT_MAX_CHARS = 1_200
_DEFAULT_OVERLAP_SENTENCES = 1
_DEFAULT_BATCH_SIZE = 32


# ---------------------------------------------------------------------------
# MDX → text
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def mdx_to_plain_text(mdx: str) -> str:
    text = _strip_frontmatter(mdx).replace("\r\n", "\n")
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"~~~[\s\S]*?~~~", " ", text)
    text = re.sub(r"^\s*(import|export)\b.*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"<(video|audio|picture|iframe)\b[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<(img|source)\b[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<Image\b[\s\S]*?/>\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<Image\b[\s\S]*?</Image>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"</?[A-Za-z][^>]*>", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sentence_split(text: str) -> List[str]:
    parts = re.split(r"(?<=[\.\!\?…])\s+|\n+", text)
    return [
        s.strip()
        for s in parts
        if len(s.strip()) >= 3 and re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", s)
    ]


def _sentence_chunks(
    sentences: List[str],
    target_chars: int,
    max_chars: int,
    overlap: int,
) -> List[str]:
    chunks: List[str] = []
    i = 0
    while i < len(sentences):
        current: List[str] = []
        total = 0
        j = i
        while j < len(sentences):
            next_len = len(sentences[j]) + (1 if current else 0)
            if current and total + next_len > max_chars:
                break
            current.append(sentences[j])
            total += next_len
            j += 1
            if total >= target_chars:
                break
        if not current:
            current = [sentences[i]]
            j = i + 1
        chunks.append(" ".join(current).strip())
        i = max(i + 1, j - max(0, overlap))
    return chunks


# ---------------------------------------------------------------------------
# Node building
# ---------------------------------------------------------------------------

def _collect_mdx_files(docs_root: Path) -> List[Path]:
    if not docs_root.exists():
        raise RuntimeError(f"Platon docs root not found: {docs_root}")
    return sorted(docs_root.rglob("*.mdx"))


def _build_nodes(
    docs_root: Path,
    target_chars: int = _DEFAULT_TARGET_CHARS,
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP_SENTENCES,
) -> List[TextNode]:
    files = _collect_mdx_files(docs_root)
    logger.info("Building Platon docs nodes from %d MDX files in %s", len(files), docs_root)
    nodes: List[TextNode] = []
    for file_path in files:
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        text = mdx_to_plain_text(raw)
        if not text:
            continue
        sentences = _sentence_split(text)
        if not sentences:
            continue
        rel = file_path.relative_to(docs_root).as_posix()
        for idx, chunk in enumerate(_sentence_chunks(sentences, target_chars, max_chars, overlap)):
            if chunk:
                nodes.append(
                    TextNode(
                        text=chunk,
                        metadata={"source_path": rel, "chunk_index": idx, "lang": "fr"},
                        id_=f"{rel}::chunk::{idx}",
                    )
                )
    logger.info("Built %d Platon docs nodes", len(nodes))
    return nodes


# ---------------------------------------------------------------------------
# Terminal progress
# ---------------------------------------------------------------------------

def _print_chunk_progress(done: int, total: int, source: str, elapsed: float) -> None:
    """Print one line per embedded chunk — immediately visible in Docker logs."""
    pct = int(done / total * 100) if total else 100
    short_source = source.split("/")[-1] if "/" in source else source
    print(
        f"  [chunk {done:>4}/{total}  {pct:>3}%]  {short_source:<40}  {elapsed:.2f}s",
        flush=True,
    )


def _print_doc_summary(total: int, wall: float) -> None:
    print(
        f"\n  Platon docs: {total}/{total} chunks embedded  total {wall:.1f}s\n",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _embed_and_store(
    nodes: List[TextNode],
    embed_model: HuggingFaceEmbedding,
    vector_store: PGVectorStore,
    batch_size: int,
) -> None:
    total = len(nodes)
    wall_start = time.monotonic()

    for i, node in enumerate(nodes):
        text = node.get_content(metadata_mode="none")
        t0 = time.monotonic()
        node.embedding = embed_model.get_text_embedding(text)
        elapsed = time.monotonic() - t0
        source = node.metadata.get("source_path", "")
        _print_chunk_progress(i + 1, total, source, elapsed)

        is_batch_boundary = (i + 1) % batch_size == 0
        is_last = i + 1 == total
        if is_batch_boundary or is_last:
            batch_start = (i + 1) - ((i + 1) % batch_size or batch_size)
            vector_store.add(nodes[batch_start : i + 1])

    _print_doc_summary(total, time.monotonic() - wall_start)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def ensure_populated(force_rebuild: bool = False) -> None:
    """
    Startup hook.  Populates the Platon docs vector table if it is empty.

    Args:
        force_rebuild: When True, unconditionally drops and rebuilds the table
                       (used when the docs corpus was just refreshed).
    """
    from src.infra.vector.vector_utils import drop_vector_table

    table_name = settings.PLATON_DOCS_VECTOR_TABLE
    physical = physical_table_name(table_name)
    validate_table_name(physical)

    dsn = {
        "host": settings.POSTGRES_HOST,
        "port": settings.POSTGRES_PORT,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
        "database": settings.POSTGRES_DB,
    }

    if force_rebuild:
        logger.info(
            "Platon docs changed — dropping and rebuilding vector table '%s'.", physical
        )
        await drop_vector_table(dsn, physical)
    else:
        count = await table_row_count(dsn, physical)
        if count is not None and count > 0:
            logger.info(
                "Platon docs vector table '%s' already has %d rows — skipping population.",
                physical, count,
            )
            return

    logger.info("Platon docs vector table is empty — running full population.")
    await _run_full_population()


async def _run_full_population(
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> None:
    embed_model = HuggingFaceEmbedding(model_name=str(path_constants.PLATON_DOCS_EMBED_MODEL), normalize=True)
    probe = embed_model.get_text_embedding("probe")
    embed_dim = len(probe)

    vector_store = PGVectorStore.from_params(
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        password=settings.POSTGRES_PASSWORD,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        table_name=settings.PLATON_DOCS_VECTOR_TABLE,
        embed_dim=embed_dim,
    )

    nodes = _build_nodes(PLATON_DOCS_DIR)
    if not nodes:
        logger.warning("No Platon docs nodes to embed — population skipped.")
        return

    print(
        f"\n  Platon docs vector sync: {len(nodes)} chunk(s) to embed\n",
        flush=True,
    )
    logger.info("Starting Platon docs embedding: %d chunks", len(nodes))
    _embed_and_store(nodes, embed_model, vector_store, batch_size)
    logger.info("Platon docs vector table population complete: %d chunks.", len(nodes))


async def force_rebuild(batch_size: int = _DEFAULT_BATCH_SIZE) -> None:
    """
    Unconditionally drops and rebuilds the Platon docs vector table.
    Used by the CLI script when ``--recreate`` is passed.
    """
    from src.infra.vector.vector_utils import drop_vector_table

    physical = physical_table_name(settings.PLATON_DOCS_VECTOR_TABLE)
    dsn = {
        "host": settings.POSTGRES_HOST,
        "port": settings.POSTGRES_PORT,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
        "database": settings.POSTGRES_DB,
    }
    await drop_vector_table(dsn, physical)
    await _run_full_population(batch_size=batch_size)



