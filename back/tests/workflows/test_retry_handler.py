"""
Tests for src.workflows.retry_handler.attempt_with_retry.

Covers every documented behaviour of the generic retry loop:
- Immediate success
- Success after N failures
- All attempts exhausted
- Correction failure stops the loop
- on_retry callback invocation and arguments
- Timeout triggers correct RetryResult
- RetryResult dataclass fields
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.workflows.retry_handler import RetryResult, attempt_with_retry
from src.services.models.platon import SandboxError


# ---------------------------------------------------------------------------
# RetryResult dataclass
# ---------------------------------------------------------------------------

class TestRetryResultDefaults:
    def test_default_values(self):
        r = RetryResult(success=True)
        assert r.data is None
        assert r.error is None
        assert r.attempts_used == 0
        assert r.errors_encountered == []

    def test_errors_list_is_not_shared(self):
        r1 = RetryResult(success=False)
        r2 = RetryResult(success=False)
        r1.errors_encountered.append("err")
        assert r2.errors_encountered == []


# ---------------------------------------------------------------------------
# attempt_with_retry scenarios
# ---------------------------------------------------------------------------

class TestAttemptWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        sentinel = object()
        preview_fn = AsyncMock(return_value=sentinel)
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.data is sentinel
        assert result.attempts_used == 1
        assert result.errors_encountered == []
        correction_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_after_one_failure(self):
        sentinel = object()
        preview_fn = AsyncMock(side_effect=[SandboxError("err-1"), sentinel])
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.attempts_used == 2
        assert len(result.errors_encountered) == 1
        correction_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_after_two_failures(self):
        sentinel = object()
        preview_fn = AsyncMock(
            side_effect=[SandboxError("e1"), SandboxError("e2"), sentinel]
        )
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=5,
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.attempts_used == 3
        assert correction_fn.await_count == 2

    @pytest.mark.asyncio
    async def test_all_attempts_exhausted(self):
        preview_fn = AsyncMock(side_effect=SandboxError("always fails"))
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=30,
        )

        assert result.success is False
        assert result.attempts_used == 3
        assert len(result.errors_encountered) == 3
        # correction called between attempts: max_attempts-1 times
        assert correction_fn.await_count == 2

    @pytest.mark.asyncio
    async def test_one_max_attempt_no_correction_called(self):
        preview_fn = AsyncMock(side_effect=SandboxError("fail"))
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=1,
            timeout_seconds=10,
        )

        assert result.success is False
        assert result.attempts_used == 1
        correction_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_correction_failure_stops_loop(self):
        preview_fn = AsyncMock(side_effect=SandboxError("fail"))
        correction_fn = AsyncMock(side_effect=RuntimeError("LLM is down"))

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=5,
            timeout_seconds=10,
        )

        assert result.success is False
        assert result.attempts_used == 1
        assert any("Correction failed" in e for e in result.errors_encountered)
        # correction called exactly once before it breaks
        correction_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_retry_callback_called_with_correct_args(self):
        preview_fn = AsyncMock(side_effect=[SandboxError("err-msg"), object()])
        correction_fn = AsyncMock()
        on_retry = MagicMock()

        await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
            on_retry=on_retry,
        )

        on_retry.assert_called_once()
        attempt_arg, max_arg, error_arg = on_retry.call_args[0]
        assert attempt_arg == 1          # first failure = attempt 1
        assert max_arg == 3
        assert "err-msg" in error_arg

    @pytest.mark.asyncio
    async def test_on_retry_not_called_when_no_failures(self):
        preview_fn = AsyncMock(return_value=object())
        correction_fn = AsyncMock()
        on_retry = MagicMock()

        await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
            on_retry=on_retry,
        )

        on_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_retry_not_called_on_last_failure(self):
        """Callback must NOT fire on the last failed attempt (no more retries)."""
        preview_fn = AsyncMock(side_effect=SandboxError("fail"))
        correction_fn = AsyncMock()
        on_retry = MagicMock()

        await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=2,
            timeout_seconds=10,
            on_retry=on_retry,
        )

        # Only one callback (after attempt 1), not after attempt 2 (last)
        assert on_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_returns_failure_result(self):
        async def _slow():
            await asyncio.sleep(100)
            return object()

        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=_slow,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=0.1,
        )

        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error.lower() or "timeout" in result.error.lower()
        assert any("Timeout" in e for e in result.errors_encountered)

    @pytest.mark.asyncio
    async def test_timeout_error_message_includes_duration(self):
        async def _slow():
            await asyncio.sleep(100)

        result = await attempt_with_retry(
            preview_fn=_slow,
            correction_fn=AsyncMock(),
            max_attempts=3,
            timeout_seconds=0.1,
        )

        assert "0.1" in result.error

    @pytest.mark.asyncio
    async def test_error_list_accumulates_across_attempts(self):
        errors_emitted = ["err-1", "err-2", "err-3"]
        preview_fn = AsyncMock(side_effect=[SandboxError(e) for e in errors_emitted])
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
        )

        # SandboxError.__str__ appends " | Response: {}" to the message.
        assert len(result.errors_encountered) == 3
        for raw, stored in zip(errors_emitted, result.errors_encountered):
            assert raw in stored

    @pytest.mark.asyncio
    async def test_last_error_becomes_result_error(self):
        preview_fn = AsyncMock(side_effect=[SandboxError("e1"), SandboxError("e2")])
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=2,
            timeout_seconds=10,
        )

        assert "e2" in result.error

    @pytest.mark.asyncio
    async def test_correction_receives_error_message_and_attempt_numbers(self):
        preview_fn = AsyncMock(side_effect=[SandboxError("specific error"), object()])
        correction_fn = AsyncMock()

        await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
        )

        error_msg, attempt_num, max_num = correction_fn.call_args[0]
        assert "specific error" in error_msg
        assert attempt_num == 1
        assert max_num == 3

    @pytest.mark.asyncio
    async def test_non_sandbox_exception_also_triggers_retry(self):
        """Any exception from preview_fn should be treated as a failure."""
        preview_fn = AsyncMock(side_effect=[ValueError("unexpected"), object()])
        correction_fn = AsyncMock()

        result = await attempt_with_retry(
            preview_fn=preview_fn,
            correction_fn=correction_fn,
            max_attempts=3,
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.attempts_used == 2

