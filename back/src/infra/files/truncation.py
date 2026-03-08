from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def count_tokens(text: str) -> int:
    """Count tokens in *text* using tiktoken, with a char heuristic fallback."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        logger.warning(
            "tiktoken not available -- using character-based token estimate (4 chars/token)"
        )
        return (len(text) + 3) // 4


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* to at most *max_tokens* tokens using tiktoken.

    Falls back to a character-based heuristic (4 chars ≈ 1 token) if
    tiktoken is unavailable.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated = enc.decode(tokens[:max_tokens])
        logger.debug(
            "truncate_to_tokens: reduced %d → %d tokens", len(tokens), max_tokens
        )
        return truncated
    except ImportError:
        logger.warning(
            "tiktoken not available -- using character-based truncation (4 chars/token)"
        )
        char_limit = max_tokens * 4
        if len(text) <= char_limit:
            return text
        return text[:char_limit]

