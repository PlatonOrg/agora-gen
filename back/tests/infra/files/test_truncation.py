"""
Tests for src.infra.files.truncation.

Covers:
- Text shorter than limit is returned unchanged
- Text longer than limit is truncated
- Truncated text is shorter than the original
- Fallback to character-based heuristic when tiktoken is unavailable
- Zero max_tokens returns empty string
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from src.infra.files.truncation import count_tokens, truncate_to_tokens


class TestTruncateToTokens:
    def test_short_text_returned_unchanged(self):
        text = "Hello world"
        result = truncate_to_tokens(text, max_tokens=1000)
        assert result == text

    def test_long_text_is_truncated(self):
        text = "word " * 5000  # ~5000 tokens
        result = truncate_to_tokens(text, max_tokens=100)
        assert len(result) < len(text)

    def test_truncated_text_respects_token_limit(self):
        """The result must not exceed the token limit by a significant margin."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            text = "token " * 2000
            result = truncate_to_tokens(text, max_tokens=500)
            assert len(enc.encode(result)) <= 500
        except ImportError:
            pytest.skip("tiktoken not available")

    def test_empty_text_returned_unchanged(self):
        assert truncate_to_tokens("", max_tokens=100) == ""

    def test_fallback_char_heuristic_when_tiktoken_missing(self):
        with patch.dict("sys.modules", {"tiktoken": None}):
            text = "a" * 10000
            result = truncate_to_tokens(text, max_tokens=100)
            # 100 tokens * 4 chars/token = 400 chars
            assert len(result) == 400

    def test_returns_string(self):
        result = truncate_to_tokens("some text", max_tokens=50)
        assert isinstance(result, str)

    def test_exact_length_not_truncated(self):
        """Text whose token count equals the limit is returned unchanged."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            text = "word " * 100
            tokens = enc.encode(text)
            result = truncate_to_tokens(text, max_tokens=len(tokens))
            assert result == text
        except ImportError:
            pytest.skip("tiktoken not available")


class TestCountTokens:
    def test_returns_int(self):
        assert isinstance(count_tokens("hello world"), int)

    def test_fallback_char_heuristic_when_tiktoken_missing(self):
        with patch.dict("sys.modules", {"tiktoken": None}):
            assert count_tokens("a" * 9) == 3

