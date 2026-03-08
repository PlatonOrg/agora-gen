"""
Tests for src.infra.files.file_summarizer.

Covers:
- summarize_file_content: success path, LLM failure fallback
- store_summary: correct Redis key and TTL
- get_summary: hit, miss, bytes decoded to str
- delete_summary: correct key deleted
- get_many_summaries: multiple ids, partial hits
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.infra.files.models import FileSummaryResult
from src.infra.files import file_summarizer


# ---------------------------------------------------------------------------
# summarize_file_content
# ---------------------------------------------------------------------------

class TestSummarizeFileContent:
    @pytest.mark.asyncio
    async def test_success_returns_result_with_summary(self):
        with patch("src.infra.llm.llm_wrapper.chat_text_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "A concise summary."
            result = await file_summarizer.summarize_file_content(
                file_id="f1",
                filename="doc.txt",
                extracted_text="Long text content here.",
                max_summary_tokens=200,
            )

        assert isinstance(result, FileSummaryResult)
        assert result.file_id == "f1"
        assert result.filename == "doc.txt"
        assert result.summary == "A concise summary."
        assert result.extracted_text == "Long text content here."

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback_summary(self):
        with patch("src.infra.llm.llm_wrapper.chat_text_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM is down")
            result = await file_summarizer.summarize_file_content(
                file_id="f1",
                filename="doc.txt",
                extracted_text="Some text.",
                max_summary_tokens=200,
            )

        assert "indisponible" in result.summary or "erreur" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_file_id_and_filename_preserved_on_failure(self):
        with patch("src.infra.llm.llm_wrapper.chat_text_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("error")
            result = await file_summarizer.summarize_file_content(
                file_id="f99",
                filename="report.pdf",
                extracted_text="text",
                max_summary_tokens=100,
            )
        assert result.file_id == "f99"
        assert result.filename == "report.pdf"

    @pytest.mark.asyncio
    async def test_extracted_text_truncated_before_llm_call(self):
        """Ensures we do not send unlimited text to the LLM."""
        with patch("src.infra.llm.llm_wrapper.chat_text_with_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary."
            long_text = "word " * 100_000
            await file_summarizer.summarize_file_content(
                file_id="f1",
                filename="big.txt",
                extracted_text=long_text,
                max_summary_tokens=100,
            )
        # The prompt sent to the LLM must be shorter than the original text
        user_prompt_sent = mock_llm.call_args[1]["user_request"]
        assert len(user_prompt_sent) < len(long_text)


# ---------------------------------------------------------------------------
# store_summary / get_summary / delete_summary
# ---------------------------------------------------------------------------

class TestStoreSummary:
    @pytest.mark.asyncio
    async def test_calls_redis_setex_with_correct_key(self):
        redis = AsyncMock()
        await file_summarizer.store_summary(redis, "f1", "my summary", ttl_seconds=3600)
        key = redis.setex.call_args[0][0]
        assert "f1" in key

    @pytest.mark.asyncio
    async def test_calls_redis_setex_with_correct_ttl(self):
        redis = AsyncMock()
        await file_summarizer.store_summary(redis, "f1", "summary", ttl_seconds=7200)
        ttl = redis.setex.call_args[0][1]
        assert ttl == 7200

    @pytest.mark.asyncio
    async def test_stores_summary_text(self):
        redis = AsyncMock()
        await file_summarizer.store_summary(redis, "f1", "my summary", ttl_seconds=3600)
        value = redis.setex.call_args[0][2]
        assert value == "my summary"


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_returns_none_when_key_missing(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        result = await file_summarizer.get_summary(redis, "f1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_str_when_key_is_bytes(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"summary text")
        result = await file_summarizer.get_summary(redis, "f1")
        assert result == "summary text"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_returns_str_when_key_is_str(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="summary text")
        result = await file_summarizer.get_summary(redis, "f1")
        assert result == "summary text"

    @pytest.mark.asyncio
    async def test_correct_key_used(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        await file_summarizer.get_summary(redis, "my-file-id")
        key = redis.get.call_args[0][0]
        assert "my-file-id" in key


class TestDeleteSummary:
    @pytest.mark.asyncio
    async def test_calls_redis_delete(self):
        redis = AsyncMock()
        await file_summarizer.delete_summary(redis, "f1")
        redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_correct_key_deleted(self):
        redis = AsyncMock()
        await file_summarizer.delete_summary(redis, "my-file-id")
        key = redis.delete.call_args[0][0]
        assert "my-file-id" in key


# ---------------------------------------------------------------------------
# get_many_summaries
# ---------------------------------------------------------------------------

class TestGetManySummaries:
    @pytest.mark.asyncio
    async def test_returns_only_present_summaries(self):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[b"summary-1", None, b"summary-3"])
        result = await file_summarizer.get_many_summaries(redis, ["f1", "f2", "f3"])
        assert result == {"f1": "summary-1", "f3": "summary-3"}

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self):
        redis = AsyncMock()
        result = await file_summarizer.get_many_summaries(redis, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_all_missing_returns_empty_dict(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        result = await file_summarizer.get_many_summaries(redis, ["f1", "f2"])
        assert result == {}

