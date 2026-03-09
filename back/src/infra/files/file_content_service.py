from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.infra.files.models import FileSummaryResult
from src.infra.files.parsers import extract_text, is_extension_accepted
from src.infra.files.truncation import count_tokens
from src.infra.files import file_summarizer

logger = logging.getLogger(__name__)

_FILE_CONTENT_PREFIX = "file_content:"


class FileTokenLimitExceededError(ValueError):
    def __init__(self, filename: str, token_count: int, max_tokens: int) -> None:
        self.filename = filename
        self.token_count = token_count
        self.max_tokens = max_tokens
        super().__init__(
            f"File '{filename}' contains {token_count} tokens, exceeding max {max_tokens}"
        )


class FileContentService:
    """Stores extracted file text in Redis and retrieves it by file_id.

    At upload time (before the file is sent to the LLM provider or stored
    only as a remote id) the raw bytes are extracted into plain text and
    saved in Redis so any provider can later inject the content into the
    user prompt.
    """

    def __init__(self, redis, ttl_seconds: int, max_tokens: int, summary_max_tokens: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._max_tokens = max_tokens
        self._summary_max_tokens = summary_max_tokens

    async def store(self, file_id: str, file_path: Path, filename: str, skip_extension_check: bool = False) -> Optional[FileSummaryResult]:
        if skip_extension_check:
            # Ragustave owns the file and handles all formats natively.
            # Text extraction is best-effort: skip it entirely if the file
            # is binary so we avoid a spurious warning and a wasted read.
            from src.infra.files.parsers import _is_binary  # type: ignore[attr-defined]
            if _is_binary(file_path):
                logger.info(
                    "FileContentService: skipping text extraction for binary file '%s' (Ragustave path)",
                    filename,
                )
                return None
        else:
            suffix = Path(filename).suffix.lower()
            if not is_extension_accepted(suffix):
                logger.warning(
                    "FileContentService: known binary extension '%s' for file '%s' -- skipping text extraction",
                    suffix, filename,
                )
                return None

        try:
            raw_text = extract_text(file_path, filename)
            logger.info(f"FileContentService: extracted text from '{filename}' ({raw_text})")
        except Exception as exc:
            logger.warning(
                "FileContentService: failed to extract text from '%s': %s",
                filename, exc,
            )
            return None

        token_count = count_tokens(raw_text)
        if token_count > self._max_tokens:
            logger.info(
                "FileContentService: token limit exceeded for '%s' (%d > %d)",
                filename, token_count, self._max_tokens,
            )
            raise FileTokenLimitExceededError(
                filename=filename,
                token_count=token_count,
                max_tokens=self._max_tokens,
            )

        key = f"{_FILE_CONTENT_PREFIX}{file_id}"
        await self._redis.setex(key, self._ttl, raw_text)
        logger.info(
            "FileContentService: stored text for file_id=%s (%d chars, %d tokens)",
            file_id, len(raw_text), token_count,
        )

        result = await file_summarizer.summarize_file_content(
            file_id=file_id,
            filename=filename,
            extracted_text=raw_text,
            max_summary_tokens=self._summary_max_tokens,
        )
        await file_summarizer.store_summary(self._redis, file_id, result.summary, self._ttl)
        return result

    async def get(self, file_id: str) -> Optional[str]:
        key = f"{_FILE_CONTENT_PREFIX}{file_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode("utf-8")

    async def delete(self, file_id: str) -> None:
        key = f"{_FILE_CONTENT_PREFIX}{file_id}"
        await self._redis.delete(key)
        await file_summarizer.delete_summary(self._redis, file_id)
        logger.info("FileContentService: deleted text and summary for file_id=%s", file_id)

    async def get_many(self, file_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for fid in file_ids:
            content = await self.get(fid)
            if content:
                result[fid] = content
        return result

    async def get_many_summaries(self, file_ids: list[str]) -> dict[str, str]:
        return await file_summarizer.get_many_summaries(self._redis, file_ids)
