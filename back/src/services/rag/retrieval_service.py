from __future__ import annotations

from typing import Any, Optional

from llama_index.core import VectorStoreIndex, StorageContext, Settings as LlamaSettings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.retrievers.bm25 import BM25Retriever
import torch

from src.services.models.rag import RetrievedChunk
from src.services.rag.filters import kind_filter
from src.services.rag.embedding_types import EmbeddingKind
from src.core import path_constants
from src.core.logging_config import setup_logging

logger = setup_logging("rag")


_RAG_INDEX: Optional[VectorStoreIndex] = None
_EMBED_MODEL = None

def get_embed_model(model_name: Optional[str] = None, trust_remote_code: bool = False):
    """
    Get or initialize the embedding model.
    Allows dynamic reloading if model_name is provided.

    Args:
        model_name: Optional model name to load
        trust_remote_code: Whether to trust remote code (security risk, use with caution)
    """
    global _EMBED_MODEL
    
    target_model = model_name if model_name else str(path_constants.EMBED_MODEL_PATH)
    # get cuda if available, otherwise fallback to cpu
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Reload if model changed or not initialized
    if _EMBED_MODEL is None or (model_name and _EMBED_MODEL.model_name != target_model):
        logger.info("Loading embedding model: %s", target_model)
        _EMBED_MODEL = HuggingFaceEmbedding(
            model_name=target_model,
            device=device,
            trust_remote_code=trust_remote_code  # Default to False for security
        )
        LlamaSettings.embed_model = _EMBED_MODEL
        
    return _EMBED_MODEL

def get_detailed_instruct(task_description: str, query: str) -> str:
    return f'Instruct: {task_description}\nQuery: {query}'

def get_rag_index() -> VectorStoreIndex:
    """Get the RAG index (must be initialized first)."""
    global _RAG_INDEX
    if _RAG_INDEX is None:
        raise RuntimeError("RAG Index not initialized. Check application startup.")
    return _RAG_INDEX

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
    """Initialize the RAG service by connecting to the vector database.

    This function should be called once during application startup.
    All connection parameters are passed explicitly from the composition
    root (``main.py``).
    """
    global _RAG_INDEX

    logger.info("Initializing RAG service...")

    embed_model = get_embed_model(model_name)

    # Probe embedding dimension from the model
    probe_vector = embed_model.get_text_embedding("probe")
    embed_dim = len(probe_vector)
    logger.info("Embedding dimension probed: %d", embed_dim)

    # Connect to PGVector store
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

    logger.info("RAG Service initialized on table: %s with model: %s", table_name, embed_model.model_name)

class RetrievalService:
    """High-level retrieval for templates/examples."""

    def retrieve_resources(self, *, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        """Retrieve closest resources (templates and exercises)."""
        index = get_rag_index()
        task = "Find relevant templates and exercises that best match the following query"
        e5_query = get_detailed_instruct(task, query)
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(e5_query)
        return self._to_chunks(nodes, default_kind=EmbeddingKind.EXERCICE)

    def retrieve_by_kind(self, *, query: str, kind: EmbeddingKind, top_k: int = 10) -> list[RetrievedChunk]:
        """Retrieve closest resources of a specific kind.

        Args:
            query: Search query
            kind: Type of resource to retrieve (TEMPLATE, EXERCICE, TEMPLATE_EXO)
            top_k: Number of results to retrieve

        Returns:
            List of RetrievedChunk objects of the specified kind
        """
        index = get_rag_index()
        task = f"Find relevant resources of kind '{kind.value}' that best match the following query"
        e5_query = get_detailed_instruct(task, query)
        filters = kind_filter(kind)
        retriever = index.as_retriever(similarity_top_k=top_k, filters=filters)
        nodes = retriever.retrieve(e5_query)
        return self._to_chunks(nodes, default_kind=kind)

    def retrieve_all_kinds_separately(self, *, query: str, top_k: int = 10) -> dict[str, list[RetrievedChunk]]:
        """Retrieve top K results for each kind separately.

        Returns:
            Dictionary with keys 'all', 'templates', 'exercises', 'template_exos'.
        """
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
        """Convert LlamaIndex nodes to RetrievedChunk objects."""
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
