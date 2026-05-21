from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from llama_index.core import VectorStoreIndex, StorageContext, Settings as LlamaSettings
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.retrievers.bm25 import BM25Retriever
import torch

from src.services.models.rag import RetrievedChunk
from src.services.rag.filters import kind_filter
from src.services.rag.embedding_types import EmbeddingKind
from src.core import path_constants
from src.core.config_app import settings as _settings
from src.core.logging_config import setup_logging
from src.infra.vector.vector_utils import physical_table_name, validate_table_name

logger = setup_logging("rag")


_RAG_INDEX: Optional[VectorStoreIndex] = None
_EMBED_MODEL = None
_BM25_NODES: List[TextNode] = []
_VECTOR_TABLE_NAME: str = ""
_VECTOR_DSN: dict = {}

_RERANKER: Any = None
_RERANKER_LOAD_ATTEMPTED: bool = False


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

def get_embed_model(model_name: Optional[str] = None, trust_remote_code: bool = False):
    global _EMBED_MODEL
    target_model = model_name if model_name else str(path_constants.EMBED_MODEL_PATH)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if _EMBED_MODEL is None or (model_name and _EMBED_MODEL.model_name != target_model):
        logger.info("Loading embedding model: %s", target_model)
        _EMBED_MODEL = HuggingFaceEmbedding(
            model_name=target_model,
            device=device,
            trust_remote_code=trust_remote_code,
            normalize=True,
        )
        LlamaSettings.embed_model = _EMBED_MODEL
    return _EMBED_MODEL



def get_rag_index() -> VectorStoreIndex:
    global _RAG_INDEX
    if _RAG_INDEX is None:
        raise RuntimeError("RAG Index not initialized. Check application startup.")
    return _RAG_INDEX


# ---------------------------------------------------------------------------
# RAG index initialization
# ---------------------------------------------------------------------------

def initialize_rag_service(
    *,
    db_host: str,
    db_port: int,
    db_user: str,
    db_password: str,
    db_name: str,
    table_name: str,
    model_name: Optional[str] = None,
) -> None:
    global _RAG_INDEX, _VECTOR_TABLE_NAME, _VECTOR_DSN

    logger.info("Initializing RAG service...")

    embed_model = get_embed_model(model_name)
    probe_vector = embed_model.get_text_embedding("probe")
    embed_dim = len(probe_vector)
    logger.info("Embedding dimension probed: %d", embed_dim)

    vector_store = PGVectorStore.from_params(
        database=db_name,
        host=db_host,
        password=db_password,
        port=db_port,
        user=db_user,
        table_name=table_name,
        embed_dim=embed_dim,
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    _RAG_INDEX = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
        embed_model=embed_model,
    )

    _VECTOR_TABLE_NAME = table_name
    _VECTOR_DSN = {
        "host": db_host,
        "port": db_port,
        "user": db_user,
        "password": db_password,
        "database": db_name,
    }

    logger.info("RAG Service initialized on table: %s with model: %s", table_name, embed_model.model_name)


# ---------------------------------------------------------------------------
# BM25 in-memory index
# ---------------------------------------------------------------------------

async def initialize_bm25_index() -> None:
    """Load all document texts from PGVector and build in-memory BM25 index.

    Called once at startup after initialize_rag_service(), and again after
    each full rebuild so the BM25 index stays in sync with the vector store.
    """
    global _BM25_NODES
    try:
        nodes = await _load_nodes_from_pgvector()
        _BM25_NODES = nodes
        logger.info("BM25 index built with %d nodes.", len(nodes))
    except Exception as exc:
        logger.warning("BM25 index initialization failed — falling back to dense-only: %s", exc)
        _BM25_NODES = []


def update_bm25_index(nodes: List[TextNode], full: bool = False) -> None:
    """Sync the BM25 node list after a vector store commit.

    Called by exercise_vector_service after each commit so new resources are
    immediately searchable via BM25 without a full reload.
    """
    global _BM25_NODES
    if full:
        _BM25_NODES = list(nodes)
    else:
        _BM25_NODES.extend(nodes)
    logger.info("BM25 index updated (%s): %d total nodes.", "full" if full else "incremental", len(_BM25_NODES))


async def _load_nodes_from_pgvector() -> List[TextNode]:
    """Query the PGVector table and reconstruct TextNodes for BM25."""
    if not _VECTOR_TABLE_NAME or not _VECTOR_DSN:
        logger.warning("BM25 load skipped — RAG not yet initialized.")
        return []

    physical = physical_table_name(_VECTOR_TABLE_NAME)
    validate_table_name(physical)

    import asyncpg
    conn = await asyncpg.connect(**_VECTOR_DSN)
    try:
        rows = await conn.fetch(f'SELECT text, metadata_ FROM "{physical}"')
    finally:
        await conn.close()

    nodes: List[TextNode] = []
    for row in rows:
        text = row["text"] or ""
        raw_meta = row["metadata_"]
        try:
            metadata = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
        except Exception:
            metadata = {}
        nodes.append(TextNode(text=text, metadata=metadata))

    return nodes


def _build_bm25_retriever(kind: Optional[str] = None, top_k: int = 10) -> Optional[BM25Retriever]:
    """Return a BM25Retriever filtered by kind, or None if the index is empty."""
    nodes = _BM25_NODES
    if kind:
        nodes = [n for n in nodes if n.metadata.get("kind") == kind]
    if not nodes:
        return None
    try:
        return BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=top_k)
    except Exception as exc:
        logger.warning("BM25Retriever construction failed: %s", exc)
        return None


def _rrf_merge(result_lists: list, top_k: int, k: float = 60.0) -> list:
    """Reciprocal Rank Fusion — same algorithm as QueryFusionRetriever.RECIPROCAL_RANK.

    score(d) = Σ  1 / (k + rank_i(d))   for each result list i
    """
    scores: dict = {}
    nodes_map: dict = {}

    for result_list in result_lists:
        for rank, node_with_score in enumerate(
            sorted(result_list, key=lambda x: x.score or 0.0, reverse=True)
        ):
            h = node_with_score.node.hash
            nodes_map[h] = node_with_score
            scores[h] = scores.get(h, 0.0) + 1.0 / (k + rank + 1)

    reranked = sorted(scores.keys(), key=lambda h: scores[h], reverse=True)
    result = []
    for h in reranked[:top_k]:
        node = nodes_map[h]
        node.score = scores[h]
        result.append(node)
    return result


def _hybrid_retrieve(query: str, dense_retriever, bm25_retriever: Optional[BM25Retriever], top_k: int) -> list:
    """Merge dense and BM25 results with Reciprocal Rank Fusion."""
    dense_results = dense_retriever.retrieve(query)
    if bm25_retriever is None:
        return dense_results
    try:
        bm25_results = bm25_retriever.retrieve(query)
        return _rrf_merge([dense_results, bm25_results], top_k=top_k)
    except Exception as exc:
        logger.warning("BM25 retrieval failed — falling back to dense-only: %s", exc)
        return dense_results


def _get_reranker() -> Any:
    """Lazy-load the BGE cross-encoder reranker. Returns None if disabled or unavailable."""
    global _RERANKER, _RERANKER_LOAD_ATTEMPTED
    if _RERANKER_LOAD_ATTEMPTED:
        return _RERANKER
    _RERANKER_LOAD_ATTEMPTED = True

    if not _settings.RERANKER_ENABLED:
        logger.info("Reranker disabled via RERANKER_ENABLED=false.")
        return None

    from sentence_transformers import CrossEncoder

    local_path = path_constants.RERANKER_MODEL_PATH
    model_id = str(local_path) if local_path.exists() else _settings.RERANKER_HF_REPO_ID
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        _RERANKER = CrossEncoder(model_id, max_length=512, device=device)
        logger.info("Reranker loaded from: %s on %s", model_id, device)
    except Exception as exc:
        logger.warning("Reranker load failed (%s) — reranking disabled: %s", model_id, exc)
        _RERANKER = None
    return _RERANKER


def _rerank_nodes(query: str, nodes: list, top_k: int) -> list:
    """Cross-encoder reranking. Falls back to original order on any failure."""
    if not nodes:
        return nodes
    reranker = _get_reranker()
    if reranker is None:
        return nodes[:top_k]
    try:
        pairs = [(query, n.node.get_content()[:600]) for n in nodes]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(scores, nodes), key=lambda x: x[0], reverse=True)
        result = []
        for score, node in ranked[:top_k]:
            node.score = float(score)
            result.append(node)
        logger.debug("Reranker: %d → %d nodes (top score: %.4f)", len(nodes), len(result), float(scores[0]) if len(scores) else 0)
        return result
    except Exception as exc:
        logger.warning("Reranking failed — using original order: %s", exc)
        return nodes[:top_k]


# ---------------------------------------------------------------------------
# RetrievalService
# ---------------------------------------------------------------------------

class RetrievalService:
    """High-level retrieval for templates and examples."""

    def retrieve_resources(self, *, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        """General hybrid retrieval across all resource kinds (backwards-compatible)."""
        index = get_rag_index()
        dense = index.as_retriever(similarity_top_k=top_k)
        bm25 = _build_bm25_retriever(top_k=top_k)
        nodes = _hybrid_retrieve(query, dense, bm25, top_k)
        return self._to_chunks(nodes, default_kind=EmbeddingKind.EXERCICE)

    def retrieve_templates(self, *, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        """Retrieve TEMPLATE resources only.

        Fetches fetch_k candidates via hybrid search, then cross-encoder reranks
        to the requested top_k for higher precision in template selection.
        """
        index = get_rag_index()
        fetch_k = top_k + 8
        dense = index.as_retriever(
            similarity_top_k=fetch_k,
            filters=kind_filter(EmbeddingKind.TEMPLATE),
        )
        bm25 = _build_bm25_retriever(kind=EmbeddingKind.TEMPLATE.value, top_k=fetch_k)
        nodes = _hybrid_retrieve(query, dense, bm25, fetch_k)
        nodes = _rerank_nodes(query, nodes, top_k)
        return self._to_chunks(nodes, default_kind=EmbeddingKind.TEMPLATE)

    def retrieve_examples(self, *, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Retrieve EXERCICE and TEMPLATE_EXO resources for few-shot examples.

        Templates are excluded: they belong in retrieve_templates() and would
        add noise here (parameter descriptions ≠ concrete exercise content).
        """
        index = get_rag_index()
        dense = index.as_retriever(similarity_top_k=top_k)
        bm25 = _build_bm25_retriever(top_k=top_k)
        nodes = _hybrid_retrieve(query, dense, bm25, top_k)
        chunks = self._to_chunks(nodes, default_kind=EmbeddingKind.EXERCICE)
        return [c for c in chunks if c.doc_type != EmbeddingKind.TEMPLATE.value]

    def retrieve_by_kind(self, *, query: str, kind: EmbeddingKind, top_k: int = 10) -> list[RetrievedChunk]:
        """Retrieve closest resources of a specific kind."""
        index = get_rag_index()
        filters = kind_filter(kind)
        dense = index.as_retriever(similarity_top_k=top_k, filters=filters)
        bm25 = _build_bm25_retriever(kind=kind.value, top_k=top_k)
        nodes = _hybrid_retrieve(query, dense, bm25, top_k)
        return self._to_chunks(nodes, default_kind=kind)

    def retrieve_all_kinds_separately(self, *, query: str, top_k: int = 10) -> dict[str, list[RetrievedChunk]]:
        """Retrieve top K results for each kind separately."""
        all_results = self.retrieve_resources(query=query, top_k=top_k)
        templates = self.retrieve_by_kind(query=query, kind=EmbeddingKind.TEMPLATE, top_k=top_k)
        exercises = self.retrieve_by_kind(query=query, kind=EmbeddingKind.EXERCICE, top_k=top_k)
        template_exos = self.retrieve_by_kind(query=query, kind=EmbeddingKind.TEMPLATE_EXO, top_k=top_k)
        return {
            "all": all_results,
            "templates": templates,
            "exercises": exercises,
            "template_exos": template_exos,
        }

    @staticmethod
    def _to_chunks(nodes: list[Any], default_kind: EmbeddingKind) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for n in nodes:
            md = dict(getattr(n.node, "metadata", {}) or {})
            out.append(
                RetrievedChunk(
                    doc_type=md.get("kind", default_kind.value),
                    name=md.get("name"),
                    score=getattr(n, "score", None),
                    content=n.node.get_content(),
                    metadata=md,
                )
            )
        return out


retrieval_service = RetrievalService()
