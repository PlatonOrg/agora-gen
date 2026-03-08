"""
Platon administrator authentication service.

Provides a valid access token for internal synchronisation requests
(resource sync, vector population).  This is completely separate from
user authentication: end-user sessions are handled by the regular OAuth
flow and are never touched here.

Lifecycle
---------
Call ``authenticate()`` once at server startup before any sync job runs.
The token is stored in-memory and reused for all subsequent sync requests.
If a sync request receives a 401, callers should call ``authenticate()``
again to refresh the token and retry.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.core.config_app import settings

logger = logging.getLogger(__name__)

_SIGNIN_PATH = "/auth/signin"


class PlatonAdminAuth:
    """Holds and refreshes the administrator access token."""

    def __init__(self, base_url: str, username: str, password: str, timeout: float) -> None:
        self._base_url = base_url
        self._username = username
        self._password = password
        self._timeout = timeout
        self._access_token: Optional[str] = None

    @property
    def token(self) -> Optional[str]:
        return self._access_token

    async def authenticate(self) -> str:
        """
        Sign in with admin credentials and store the resulting access token.

        Returns:
            The fresh access token.

        Raises:
            RuntimeError: If the sign-in request fails.
        """
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            try:
                response = await client.post(
                    _SIGNIN_PATH,
                    json={"username": self._username, "password": self._password},
                )
                response.raise_for_status()
                payload = response.json()
                token = payload["resource"]["accessToken"]
                self._access_token = token
                logger.info("Platon admin authentication successful.")
                return token
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Platon admin sign-in failed (HTTP {exc.response.status_code}): "
                    f"{exc.response.text}"
                ) from exc
            except Exception as exc:
                raise RuntimeError(f"Platon admin sign-in request failed: {exc}") from exc


def _build_admin_auth() -> PlatonAdminAuth:
    """Factory — reads credentials from settings (composition root)."""
    if not settings.PLATON_ADMIN_USERNAME or not settings.PLATON_ADMIN_PASSWORD:
        raise RuntimeError(
            "PLATON_ADMIN_USERNAME and PLATON_ADMIN_PASSWORD must be set in .env "
            "for background synchronisation to work."
        )
    return PlatonAdminAuth(
        base_url=settings.PLATON_BASE_URL,
        username=settings.PLATON_ADMIN_USERNAME,
        password=settings.PLATON_ADMIN_PASSWORD,
        timeout=settings.PLATON_TIMEOUT_SECONDS,
    )


platon_admin_auth: PlatonAdminAuth = _build_admin_auth()

