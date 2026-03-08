import json
import base64
import logging
import secrets
from typing import Optional, Dict, Any, List
from redis.asyncio import Redis
import jwt

logger = logging.getLogger("uvicorn")

class AuthService:

    PREFIX_STATE = "oauth_state:"
    PREFIX_SESSION = "session:"

    def __init__(
        self,
        oauth_state_ttl: int,
        session_ttl: int,
        platon_public_key: Optional[str] = None,
    ) -> None:
        self._oauth_state_ttl = oauth_state_ttl
        self._session_ttl = session_ttl
        self._platon_public_key = platon_public_key

    # --- 1. OAuth State (Redis) ---
    async def generate_oauth_state(self, redis: Redis) -> str:
        state = secrets.token_urlsafe(32)
        key = f"{AuthService.PREFIX_STATE}{state}"
        await redis.setex(key, self._oauth_state_ttl, "valid")
        return state

    @staticmethod
    async def validate_oauth_state(redis: Redis, state: str) -> bool:
        key = f"{AuthService.PREFIX_STATE}{state}"
        value = await redis.get(key)
        if not value: return False
        await redis.delete(key)
        return True

    # --- 2. Session Management (Redis Only) ---

    async def create_session(
            self,
            redis: Redis,
            user_profile: Dict[str, Any],
            platon_access: str,
            platon_refresh: Optional[str]
    ) -> str:
        """
        Creates an ephemeral session in Redis containing user info and tokens.
        No local DB persistence for users.
        """
        session_id = secrets.token_urlsafe(32)
        key = f"{AuthService.PREFIX_SESSION}{session_id}"

        session_data = {
            **user_profile,
            "platon_access": platon_access,
            "platon_refresh": platon_refresh
        }

        await redis.setex(key, self._session_ttl, json.dumps(session_data))
        return session_id

    @staticmethod
    async def get_session_user(redis: Redis, session_id: str) -> Optional[Dict[str, Any]]:
        key = f"{AuthService.PREFIX_SESSION}{session_id}"
        data_json = await redis.get(key)
        if not data_json: return None
        return json.loads(data_json)

    @staticmethod
    async def logout_session(redis: Redis, session_id: str):
        key = f"{AuthService.PREFIX_SESSION}{session_id}"
        await redis.delete(key)

    # --- 3. JWT Logic ---

    def decode_jwt_payload_secure(self, token: str) -> Optional[Dict[str, Any]]:
        public_key = self._platon_public_key
        if not public_key: return None
        try:
            return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_signature": True})
        except Exception: return None

    @staticmethod
    def decode_jwt_payload_unsafe(token: str) -> Optional[Dict[str, Any]]:
        try:
            parts = token.split('.')
            payload = parts[1] + '=' * (-len(parts[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
        except Exception: return None

    @staticmethod
    def determine_role(username: str) -> str:
        return 'ADMIN' # if (username.startswith('admin.') or 'admin' in username) else 'TEACHER'

    @staticmethod
    def get_permissions(role: str) -> List[str]:
        base = ['CREATE_EX', 'EDIT_EX', 'VIEW_DASHBOARD']
        return base + ['DELETE_EX', 'ADMIN_CONFIG'] if role == 'ADMIN' else base


def _create_auth_service() -> AuthService:
    """Build the module-level singleton from settings (composition boundary)."""
    from src.core.config_app import settings
    return AuthService(
        oauth_state_ttl=settings.OAUTH_STATE_TTL_SECONDS,
        session_ttl=settings.SESSION_TTL_SECONDS,
        platon_public_key=settings.PLATON_PUBLIC_KEY,
    )


auth_service = _create_auth_service()
