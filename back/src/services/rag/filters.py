from __future__ import annotations


# LlamaIndex filter types
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterCondition, FilterOperator
from src.services.rag.embedding_types import EmbeddingKind


def kind_filter(kind: EmbeddingKind | str) -> MetadataFilters:
    """Filter by embedding kind."""
    kind_value = kind.value if isinstance(kind, EmbeddingKind) else kind
    return MetadataFilters(filters=[MetadataFilter(key="kind", operator=FilterOperator.EQ, value=kind_value)])

