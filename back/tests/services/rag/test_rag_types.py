"""
Tests for src.services.rag.embedding_types and src.services.rag.filters.

Covers:
- EmbeddingKind enum values and string representation
- kind_filter metadata filter construction
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.services.rag.embedding_types import EmbeddingKind


class TestEmbeddingKind:
    def test_all_values_present(self):
        values = {e.value for e in EmbeddingKind}
        assert "EXERCICE" in values
        assert "TEMPLATE" in values
        assert "TEMPLATE_EXO" in values

    def test_is_string_enum(self):
        assert isinstance(EmbeddingKind.EXERCICE, str)
        assert EmbeddingKind.EXERCICE == "EXERCICE"

    def test_value_equality_with_raw_string(self):
        assert EmbeddingKind.TEMPLATE == "TEMPLATE"

    def test_from_string(self):
        kind = EmbeddingKind("TEMPLATE_EXO")
        assert kind is EmbeddingKind.TEMPLATE_EXO

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            EmbeddingKind("INVALID_KIND")


class TestKindFilter:
    def test_filter_with_enum_value(self):
        # Import only if llama_index is available; skip gracefully otherwise.
        pytest.importorskip("llama_index")
        from src.services.rag.filters import kind_filter

        filters = kind_filter(EmbeddingKind.EXERCICE)
        assert filters is not None
        assert len(filters.filters) == 1
        f = filters.filters[0]
        assert f.key == "kind"
        assert f.value == "EXERCICE"

    def test_filter_with_raw_string(self):
        pytest.importorskip("llama_index")
        from src.services.rag.filters import kind_filter

        filters = kind_filter("TEMPLATE")
        assert filters.filters[0].value == "TEMPLATE"

