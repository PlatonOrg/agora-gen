"""
Generic retry handler for Platon sandbox compilation and runtime failures.

Encapsulates the retry-with-LLM-correction loop so that both pure
exercise generation and template-based generation can share the same
logic without duplication.

Two categories of failure trigger the correction loop:

1. **HTTP-level failures** (``SandboxError``): Platon returned a non-2xx
   response, indicating a parse or compilation error in the PLE file.

2. **Runtime-level failures** (``SandboxRuntimeError``): Platon returned
   HTTP 200, but the sandbox reported Python/JS runtime errors via
   ``platon_logs`` (entries with ``type == "error"``).  These are raised
   by :meth:`~src.services.platon_service.PlatonService.create_exercise_preview`
   so that this handler treats them identically to HTTP failures.

Design:
    - Fully async, cancellation-safe.
    - Uses ``asyncio.wait_for`` for a hard wall-clock timeout.
    - Accepts callables so callers stay decoupled from implementation.
    - Emits progress callbacks so the SSE layer can stream retry events.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional, Protocol

from src.services.models.platon import PreviewResult

logger = logging.getLogger(__name__)


@dataclass
class RetryResult:
    success: bool
    data: Optional[PreviewResult] = None
    error: Optional[str] = None
    attempts_used: int = 0
    errors_encountered: List[str] = field(default_factory=list)


class RetryProgressCallback(Protocol):
    def __call__(
        self,
        attempt: int,
        max_attempts: int,
        error_message: str,
    ) -> None: ...


async def attempt_with_retry(
    preview_fn: Callable[..., Awaitable[PreviewResult]],
    correction_fn: Callable[[str, int, int], Awaitable[None]],
    max_attempts: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
    on_retry: Optional[RetryProgressCallback] = None,
) -> RetryResult:
    if max_attempts is None or timeout_seconds is None:
        from src.services.runtime_config_service import runtime_config, SettingKey
        if max_attempts is None:
            max_attempts = runtime_config.get_int(SettingKey.SANDBOX_RETRY_MAX_ATTEMPTS)
        if timeout_seconds is None:
            timeout_seconds = runtime_config.get_float(SettingKey.SANDBOX_RETRY_TIMEOUT_SECONDS)

    errors: List[str] = []
    attempt = 0

    async def _loop() -> RetryResult:
        nonlocal attempt

        while attempt < max_attempts:
            attempt += 1
            logger.info("[RETRY LOOP] Starting attempt %d/%d.", attempt, max_attempts)
            try:
                result = await preview_fn()
                logger.info(
                    "[RETRY LOOP] Attempt %d/%d SUCCEEDED — all sandbox checks passed.",
                    attempt, max_attempts,
                )
                return RetryResult(
                    success=True,
                    data=result,
                    attempts_used=attempt,
                    errors_encountered=errors,
                )
            except Exception as exc:
                error_message = str(exc)
                errors.append(error_message)
                logger.warning(
                    "[RETRY LOOP] Attempt %d/%d FAILED: %s",
                    attempt,
                    max_attempts,
                    error_message,
                )

                if attempt >= max_attempts:
                    logger.error(
                        "[RETRY LOOP] Max attempts (%d) reached — giving up.",
                        max_attempts,
                    )
                    break

                if on_retry is not None:
                    on_retry(attempt, max_attempts, error_message)

                logger.info(
                    "[RETRY LOOP] Calling LLM correction before attempt %d/%d...",
                    attempt + 1, max_attempts,
                )
                try:
                    await correction_fn(error_message, attempt, max_attempts)
                    logger.info(
                        "[RETRY LOOP] LLM correction completed — retrying preview (attempt %d/%d).",
                        attempt + 1, max_attempts,
                    )
                except Exception as correction_exc:
                    logger.error(
                        "[RETRY LOOP] LLM correction itself failed (attempt %d/%d): %s",
                        attempt,
                        max_attempts,
                        correction_exc,
                    )
                    errors.append(f"Correction failed: {correction_exc}")
                    break

        logger.error(
            "[RETRY LOOP] All %d attempt(s) exhausted. Final error: %s",
            attempt,
            errors[-1] if errors else "Unknown error",
        )
        return RetryResult(
            success=False,
            error=errors[-1] if errors else "Unknown error",
            attempts_used=attempt,
            errors_encountered=errors,
        )

    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            "Sandbox retry timed out after %.1fs (%d attempts)",
            timeout_seconds,
            attempt,
        )
        errors.append(f"Timeout after {timeout_seconds}s")
        return RetryResult(
            success=False,
            error=f"Generation timed out after {timeout_seconds}s",
            attempts_used=attempt,
            errors_encountered=errors,
        )
