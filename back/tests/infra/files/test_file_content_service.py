"""
Tests for src.infra.files.file_content_service.FileContentService.

Covers:
- store: success path (text extracted, token-validated, stored, summarised)
- store: unsupported extension skipped when check enabled
- store: unsupported extension allowed when skip_extension_check=True
- store: extraction failure returns None (no crash)
- store: token overflow raises FileTokenLimitExceededError
- get: hit (bytes), hit (str), miss
- delete: correct keys deleted
- get_many: partial hits
- get_many_summaries: delegates to file_summarizer
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infra.files.file_content_service import (
    FileContentService,
    FileTokenLimitExceededError,
)
from src.infra.files.models import FileSummaryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(redis=None, ttl=3600, max_tokens=4000, summary_max_tokens=500) -> FileContentService:
    if redis is None:
        redis = AsyncMock()
        redis.setex = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.delete = AsyncMock()
    return FileContentService(
        redis=redis,
        ttl_seconds=ttl,
        max_tokens=max_tokens,
        summary_max_tokens=summary_max_tokens,
    )


def _fake_summary_result(file_id: str = "f1") -> FileSummaryResult:
    return FileSummaryResult(
        file_id=file_id,
        filename="doc.txt",
        extracted_text="text",
        summary="A summary.",
    )


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

class TestFileContentServiceStore:
    @pytest.mark.asyncio
    async def test_success_stores_text_in_redis(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello world", encoding="utf-8")
        redis = AsyncMock()

        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.summarize_file_content = AsyncMock(
                return_value=_fake_summary_result()
            )
            mock_summarizer.store_summary = AsyncMock()
            service = _make_service(redis=redis)
            result = await service.store("f1", f, "doc.txt")

        redis.setex.assert_awaited_once()
        key = redis.setex.call_args[0][0]
        assert "f1" in key

    @pytest.mark.asyncio
    async def test_success_returns_summary_result(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("content", encoding="utf-8")
        redis = AsyncMock()
        expected = _fake_summary_result("f1")

        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.summarize_file_content = AsyncMock(return_value=expected)
            mock_summarizer.store_summary = AsyncMock()
            service = _make_service(redis=redis)
            result = await service.store("f1", f, "doc.txt")

        assert result is expected

    @pytest.mark.asyncio
    async def test_known_binary_extension_returns_none_when_check_enabled(self, tmp_path):
        # .png is in _KNOWN_BINARY_EXTENSIONS — the check should reject it before
        # any extraction is attempted.
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        service = _make_service()
        result = await service.store("f1", f, "image.png", skip_extension_check=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_unsupported_extension_allowed_when_skip_check(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("content")
        redis = AsyncMock()

        with patch("src.infra.files.file_content_service.extract_text", return_value="extracted"):
            with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
                mock_summarizer.summarize_file_content = AsyncMock(
                    return_value=_fake_summary_result()
                )
                mock_summarizer.store_summary = AsyncMock()
                service = _make_service(redis=redis)
                result = await service.store("f1", f, "file.xyz", skip_extension_check=True)

        assert result is not None

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_none(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("content")

        with patch("src.infra.files.file_content_service.extract_text",
                   side_effect=RuntimeError("parse error")):
            service = _make_service()
            result = await service.store("f1", f, "doc.txt")

        assert result is None

    @pytest.mark.asyncio
    async def test_stores_summary_via_file_summarizer(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("content")
        redis = AsyncMock()

        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.summarize_file_content = AsyncMock(
                return_value=_fake_summary_result()
            )
            mock_summarizer.store_summary = AsyncMock()
            service = _make_service(redis=redis)
            await service.store("f1", f, "doc.txt")

        mock_summarizer.store_summary.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ttl_passed_to_redis_setex(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("content")
        redis = AsyncMock()

        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.summarize_file_content = AsyncMock(
                return_value=_fake_summary_result()
            )
            mock_summarizer.store_summary = AsyncMock()
            service = _make_service(redis=redis, ttl=9999)
            await service.store("f1", f, "doc.txt")

        ttl = redis.setex.call_args[0][1]
        assert ttl == 9999

    @pytest.mark.asyncio
    async def test_token_overflow_raises(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("content")
        service = _make_service(max_tokens=5)

        with patch("src.infra.files.file_content_service.extract_text", return_value="x" * 100):
            with patch("src.infra.files.file_content_service.count_tokens", return_value=42):
                with pytest.raises(FileTokenLimitExceededError) as exc_info:
                    await service.store("f1", f, "doc.txt")

        assert exc_info.value.token_count == 42
        assert exc_info.value.max_tokens == 5


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

class TestFileContentServiceGet:
    @pytest.mark.asyncio
    async def test_returns_none_when_key_missing(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        service = _make_service(redis=redis)
        result = await service.get("f1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_str_when_value_is_bytes(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"extracted text")
        service = _make_service(redis=redis)
        result = await service.get("f1")
        assert result == "extracted text"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_returns_str_when_value_is_str(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="extracted text")
        service = _make_service(redis=redis)
        result = await service.get("f1")
        assert result == "extracted text"

    @pytest.mark.asyncio
    async def test_correct_key_used(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        service = _make_service(redis=redis)
        await service.get("my-file-id")
        key = redis.get.call_args[0][0]
        assert "my-file-id" in key


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestFileContentServiceDelete:
    @pytest.mark.asyncio
    async def test_deletes_content_key(self):
        redis = AsyncMock()
        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.delete_summary = AsyncMock()
            service = _make_service(redis=redis)
            await service.delete("f1")

        redis.delete.assert_awaited_once()
        key = redis.delete.call_args[0][0]
        assert "f1" in key

    @pytest.mark.asyncio
    async def test_also_deletes_summary(self):
        redis = AsyncMock()
        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.delete_summary = AsyncMock()
            service = _make_service(redis=redis)
            await service.delete("f1")

        mock_summarizer.delete_summary.assert_awaited_once_with(redis, "f1")


# ---------------------------------------------------------------------------
# get_many
# ---------------------------------------------------------------------------

class TestFileContentServiceGetMany:
    @pytest.mark.asyncio
    async def test_returns_only_present_entries(self):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[b"text-1", None, b"text-3"])
        service = _make_service(redis=redis)
        result = await service.get_many(["f1", "f2", "f3"])
        assert result == {"f1": "text-1", "f3": "text-3"}

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self):
        service = _make_service()
        result = await service.get_many([])
        assert result == {}


# ---------------------------------------------------------------------------
# get_many_summaries
# ---------------------------------------------------------------------------

class TestFileContentServiceGetManySummaries:
    @pytest.mark.asyncio
    async def test_delegates_to_file_summarizer(self):
        redis = AsyncMock()
        with patch("src.infra.files.file_content_service.file_summarizer") as mock_summarizer:
            mock_summarizer.get_many_summaries = AsyncMock(
                return_value={"f1": "s1", "f2": "s2"}
            )
            service = _make_service(redis=redis)
            result = await service.get_many_summaries(["f1", "f2"])

        mock_summarizer.get_many_summaries.assert_awaited_once_with(redis, ["f1", "f2"])
        assert result == {"f1": "s1", "f2": "s2"}

