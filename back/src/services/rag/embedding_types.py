from __future__ import annotations

from enum import Enum


class EmbeddingKind(str, Enum):
    """Types of resource embeddings in the exercise RAG vector store."""

    EXERCICE = "EXERCICE"
    TEMPLATE = "TEMPLATE"
    TEMPLATE_EXO = "TEMPLATE_EXO"

