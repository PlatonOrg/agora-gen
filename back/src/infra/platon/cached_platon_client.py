"""
Cache-aware Platon client.

Wraps ``PlatonService`` with a read-through / write-through cache backed by
``PlatonCache``.  Every method first checks Redis; if the entry is present it
is returned immediately.  On a cache miss, the real Platon API is called and
the result is stored before returning.

Responsibilities
----------------
- Cache-hit / cache-miss logic for the three cacheable Platon calls.
- Retry logic for transient 5xx / network failures (never cached on error).
- Delegation to ``PlatonService`` on misses.
- Writing fresh results back to ``PlatonCache`` only on success.

This class does NOT own any business logic, sync algorithms, or embedding
concerns — those live in their respective services.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar

from src.infra.platon.platon_cache import PlatonCache
from src.services.platon_service import PlatonService

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0


async def _with_retry(
    call: Callable[[], Coroutine[Any, Any, _T]],
    label: str,
    attempts: int = _RETRY_ATTEMPTS,
    delay: float = _RETRY_DELAY_SECONDS,
) -> _T:
    """
    Execute *call* up to *attempts* times, retrying immediately on any exception.

    Only the last failure is re-raised.  This covers transient 5xx responses
    and network blips without masking permanent errors (4xx, auth failures).
    Results are never cached inside this helper — caching is the caller's
    responsibility and must only happen after a successful return.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                logger.warning(
                    "Platon call failed (attempt %d/%d) for %s: %s — retrying in %.1fs…",
                    attempt, attempts, label, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "Platon call failed (attempt %d/%d) for %s: %s — giving up.",
                    attempt, attempts, label, exc,
                )
    raise last_exc


class CachedPlatonClient:
    """
    Read-through / write-through facade over PlatonService.

    Only the three calls that are expensive and repeatable across the sync
    and embedding pipelines are cached.  Mutating calls (publish, preview,
    evaluate) are always passed directly to the underlying service.

    On a cache miss, the call is retried up to ``_RETRY_ATTEMPTS`` times
    before raising.  The result is written to Redis only on success.
    """

    def __init__(self, platon: PlatonService, cache: PlatonCache) -> None:
        self._platon = platon
        self._cache = cache

    # ------------------------------------------------------------------
    # Cached reads
    # ------------------------------------------------------------------

    async def get_resource(
        self,
        resource_id: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        cached = await self._cache.get_resource(resource_id)
        if cached is not None:
            logger.debug("Cache HIT: resource %s", resource_id)
            return cached

        logger.debug("Cache MISS: resource %s — fetching from Platon.", resource_id)
        data = await _with_retry(
            lambda: self._platon.get_resource(resource_id, token=token),
            label=f"get_resource:{resource_id[:8]}",
        )
        await self._cache.set_resource(resource_id, data)
        return data

    async def compile_resource_json(
        self,
        resource_id: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        cached = await self._cache.get_compiled(resource_id)
        if cached is not None:
            logger.debug("Cache HIT: compile %s", resource_id)
            return cached

        logger.debug("Cache MISS: compile %s — fetching from Platon.", resource_id)
        data = await _with_retry(
            lambda: self._platon.compile_resource_json(resource_id, token=token),
            label=f"compile:{resource_id[:8]}",
        )
        await self._cache.set_compiled(resource_id, data)
        return data

    async def get_file_content(
        self,
        resource_id: str,
        filename: str,
        version: str = "latest",
        token: Optional[str] = None,
    ) -> str:
        cached = await self._cache.get_file(resource_id, filename)
        if cached is not None:
            logger.debug("Cache HIT: file %s/%s", resource_id, filename)
            return cached

        logger.debug("Cache MISS: file %s/%s — fetching from Platon.", resource_id, filename)
        content = await _with_retry(
            lambda: self._platon.get_file_content(resource_id, filename, version, token=token),
            label=f"file:{resource_id[:8]}/{filename}",
        )
        await self._cache.set_file(resource_id, filename, content)
        return content

    # ------------------------------------------------------------------
    # Pass-through calls (not cached)
    # ------------------------------------------------------------------

    async def get_ready_exercises(
        self,
        offset: int = 0,
        limit: Optional[int] = 50,
        configurable: Optional[bool] = None,
        token: Optional[str] = None,
        period: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return await self._platon.get_ready_exercises(
            offset=offset,
            limit=limit,
            configurable=configurable,
            token=token,
            period=period,
        )

    async def extract_exercise_components(
        self,
        exercise_id: str,
        token: Optional[str] = None,
        compiled_json: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        return await self._platon.extract_exercise_components(
            exercise_id=exercise_id,
            token=token,
            compiled_json=compiled_json,
        )

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    async def invalidate(self, resource_id: str) -> None:
        """Evict all cache entries for a resource (e.g. after it is updated)."""
        await self._cache.invalidate_resource(resource_id)



class CachedPlatonClient:
    """
    Read-through / write-through facade over PlatonService.

    Only the three calls that are expensive and repeatable across the sync
    and embedding pipelines are cached.  Mutating calls (publish, preview,
    evaluate) are always passed directly to the underlying service.
    """

    def __init__(self, platon: PlatonService, cache: PlatonCache) -> None:
        self._platon = platon
        self._cache = cache

    # ------------------------------------------------------------------
    # Cached reads
    # ------------------------------------------------------------------

    async def get_resource(
        self,
        resource_id: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch resource metadata, serving from cache when available.

        The cache key is ``platon_cache:resource:{resource_id}``.
        """
        cached = await self._cache.get_resource(resource_id)
        if cached is not None:
            logger.debug("Cache HIT: resource %s", resource_id)
            return cached

        logger.debug("Cache MISS: resource %s — fetching from Platon.", resource_id)
        data = await self._platon.get_resource(resource_id, token=token)
        await self._cache.set_resource(resource_id, data)
        return data

    async def compile_resource_json(
        self,
        resource_id: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch compiled resource variables, serving from cache when available.

        The cache key is ``platon_cache:compile:{resource_id}``.
        """
        cached = await self._cache.get_compiled(resource_id)
        if cached is not None:
            logger.debug("Cache HIT: compile %s", resource_id)
            return cached

        logger.debug("Cache MISS: compile %s — fetching from Platon.", resource_id)
        data = await self._platon.compile_resource_json(resource_id, token=token)
        await self._cache.set_compiled(resource_id, data)
        return data

    async def get_file_content(
        self,
        resource_id: str,
        filename: str,
        version: str = "latest",
        token: Optional[str] = None,
    ) -> str:
        """
        Fetch a resource file (main.plc / main.plo), serving from cache when available.

        The cache key is ``platon_cache:file:{resource_id}:{filename}``.
        The version parameter is intentionally excluded from the key because
        we always request ``latest`` in this pipeline.
        """
        cached = await self._cache.get_file(resource_id, filename)
        if cached is not None:
            logger.debug("Cache HIT: file %s/%s", resource_id, filename)
            return cached

        logger.debug("Cache MISS: file %s/%s — fetching from Platon.", resource_id, filename)
        content = await self._platon.get_file_content(resource_id, filename, version, token=token)
        await self._cache.set_file(resource_id, filename, content)
        return content

    # ------------------------------------------------------------------
    # Pass-through calls (not cached)
    # ------------------------------------------------------------------

    async def get_ready_exercises(
        self,
        offset: int = 0,
        limit: Optional[int] = 50,
        configurable: Optional[bool] = None,
        token: Optional[str] = None,
        period: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return await self._platon.get_ready_exercises(
            offset=offset,
            limit=limit,
            configurable=configurable,
            token=token,
            period=period,
        )

    async def extract_exercise_components(
        self,
        exercise_id: str,
        token: Optional[str] = None,
        compiled_json: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        return await self._platon.extract_exercise_components(
            exercise_id=exercise_id,
            token=token,
            compiled_json=compiled_json,
        )

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    async def invalidate(self, resource_id: str) -> None:
        """Evict all cache entries for a resource (e.g. after it is updated)."""
        await self._cache.invalidate_resource(resource_id)

