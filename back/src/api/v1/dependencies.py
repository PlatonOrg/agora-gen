"""
Shared FastAPI dependencies for the v1 API layer.

Centralizes ``Settings`` access and session resolution so that
endpoint modules never import ``settings`` directly.  This makes
every route handler testable by overriding dependencies.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis

from src.core.config_app import Settings, settings
from src.infra.db.redis import get_redis
from src.services.auth_service import auth_service


def get_settings() -> Settings:
    """Return the application-wide ``Settings`` singleton.

    Endpoints use ``Depends(get_settings)`` instead of a bare import.
    In tests, override this dependency to inject a custom ``Settings``.
    """
    return settings


async def get_session_id(
    request: Request,
    app_settings: Settings = Depends(get_settings),
) -> Optional[str]:
    """Extract the session id from the request cookie.

    Returns ``None`` when no session cookie is present (unauthenticated
    visitor).  Use ``require_session_id`` when authentication is mandatory.
    """
    return request.cookies.get(app_settings.SESSION_COOKIE_NAME)


async def require_session_id(
    session_id: Optional[str] = Depends(get_session_id),
) -> str:
    """Guarantee a non-``None`` session id or raise 401."""
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session_id


async def get_user_token(
    session_id: Optional[str] = Depends(get_session_id),
    redis: Redis = Depends(get_redis),
) -> Optional[str]:
    """Resolve the Platon access token from the session.

    Returns ``None`` when there is no session or no token stored.
    """
    if not session_id:
        return None
    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        return None
    return session_data.get("platon_access")


async def require_user_token(
    session_id: str = Depends(require_session_id),
    redis: Redis = Depends(get_redis),
) -> str:
    """Guarantee a valid Platon access token or raise 401."""
    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")
    token = session_data.get("platon_access")
    if not token:
        raise HTTPException(status_code=401, detail="No Platon access token")
    return token

