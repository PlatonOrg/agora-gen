"""
Platon API response cache.

A thin Redis-backed key/value store dedicated exclusively to caching
Platon API responses.  This layer has a single responsibility: read and
write JSON payloads under deterministic keys.  It knows nothing about
business logic, sync algorithms, or embedding pipelines.

Key schema
----------
All keys are prefixed with ``platon_cache:`` and encode the endpoint and
the resource identifier so that different call types never collide:

    platon_cache:resource:{resource_id}         — get_resource()
    platon_cache:compile:{resource_id}           — compile_resource_json()
    platon_cache:file:{resource_id}:{filename}   — get_file_content()

TTL
---
Entries are written with a configurable TTL (default 24 hours).  On a
fresh server start the cache will be empty and all calls will hit Platon;
on subsequent restarts within the TTL window every call is served from
Redis — zero Platon requests for data that has not changed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "platon_cache"
_DEFAULT_TTL_SECONDS = 86_400  # 24 hours


def _resource_key(resource_id: str) -> str:
    return f"{_KEY_PREFIX}:resource:{resource_id}"


def _compile_key(resource_id: str) -> str:
    return f"{_KEY_PREFIX}:compile:{resource_id}"


def _file_key(resource_id: str, filename: str) -> str:
    return f"{_KEY_PREFIX}:file:{resource_id}:{filename}"


class PlatonCache:
    """
    Redis-backed cache for Platon API responses.

    All public methods follow the same contract:
    - ``get_*``  — returns the cached value or ``None`` on a miss.
    - ``set_*``  — stores the value, always overwriting any existing entry.
    - ``invalidate_resource`` — evicts all entries for one resource id.
    """

    def __init__(self, redis: aioredis.Redis, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------
    # Resource metadata  (get_resource)
    # ------------------------------------------------------------------

    async def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        raw = await self._redis.get(_resource_key(resource_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Corrupt cache entry for resource %s — evicting.", resource_id)
            await self._redis.delete(_resource_key(resource_id))
            return None

    async def set_resource(self, resource_id: str, data: Dict[str, Any]) -> None:
        await self._redis.set(
            _resource_key(resource_id),
            json.dumps(data),
            ex=self._ttl,
        )

    # ------------------------------------------------------------------
    # Compiled variables  (compile_resource_json)
    # ------------------------------------------------------------------

    async def get_compiled(self, resource_id: str) -> Optional[Dict[str, Any]]:
        raw = await self._redis.get(_compile_key(resource_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Corrupt compile cache for resource %s — evicting.", resource_id)
            await self._redis.delete(_compile_key(resource_id))
            return None

    async def set_compiled(self, resource_id: str, data: Dict[str, Any]) -> None:
        await self._redis.set(
            _compile_key(resource_id),
            json.dumps(data),
            ex=self._ttl,
        )

    # ------------------------------------------------------------------
    # File content  (get_file_content — main.plc / main.plo)
    # ------------------------------------------------------------------

    async def get_file(self, resource_id: str, filename: str) -> Optional[str]:
        raw = await self._redis.get(_file_key(resource_id, filename))
        return raw  # already a str (decode_responses=True on redis client)

    async def set_file(self, resource_id: str, filename: str, content: str) -> None:
        await self._redis.set(
            _file_key(resource_id, filename),
            content,
            ex=self._ttl,
        )

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    async def invalidate_resource(self, resource_id: str) -> None:
        """Remove all cache entries associated with *resource_id*."""
        keys = [
            _resource_key(resource_id),
            _compile_key(resource_id),
        ]
        file_pattern = _file_key(resource_id, "*")
        async for key in self._redis.scan_iter(match=file_pattern):
            keys.append(key)
        if keys:
            await self._redis.delete(*keys)
            logger.debug("Cache evicted %d key(s) for resource %s.", len(keys), resource_id)

