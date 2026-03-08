from fastapi import APIRouter, HTTPException, Response, Request, Depends
from redis.asyncio import Redis

from src.api.v1.dependencies import get_settings, get_session_id
from src.api.v1.schemas import AuthInitResponse, AuthCallbackRequest, UserProfile
from src.core.config_app import Settings
from src.services.auth_service import auth_service
from src.infra.db.redis import get_redis

router = APIRouter()


@router.post("/platon/init", response_model=AuthInitResponse)
async def init_platon_auth(
    redis: Redis = Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
):
    state = await auth_service.generate_oauth_state(redis)
    from urllib.parse import quote_plus
    callback_url = quote_plus(app_settings.PLATON_CALLBACK_URL)
    callback_title = quote_plus(app_settings.PLATON_CALLBACK_TITLE)
    redirect_url = f"{app_settings.PLATON_LOGIN_BASE_URL}?callbackUrl={callback_url}&callbackTitle={callback_title}"
    return AuthInitResponse(redirectUrl=redirect_url, state=state)

@router.post("/platon/callback")
async def platon_callback(
        data: AuthCallbackRequest,
        response: Response,
        redis: Redis = Depends(get_redis),
        app_settings: Settings = Depends(get_settings),
):
    # 1. Validate State
    if not await auth_service.validate_oauth_state(redis, data.state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    # 2. Decode Token
    payload = auth_service.decode_jwt_payload_secure(data.platonAccessToken)
    if not payload and not app_settings.PLATON_PUBLIC_KEY:
        payload = auth_service.decode_jwt_payload_unsafe(data.platonAccessToken)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid Token")

    # 3. User Logic (No DB storage)
    username = payload.get('username', 'unknown')
    role = auth_service.determine_role(username)

    user_profile = {
        "id": payload.get('sub'),
        "username": username,
        "email": f"{username.replace('.', '')}@univ-eiffel.fr",
        "role": role
    }

    # 4. Create Session in Redis
    session_id = await auth_service.create_session(
        redis, user_profile, data.platonAccessToken, data.platonRefreshToken
    )

    # 5. Set Cookie
    response.set_cookie(
        key=app_settings.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        max_age=app_settings.SESSION_TTL_SECONDS,
        samesite=app_settings.SESSION_COOKIE_SAMESITE,
        secure=app_settings.SESSION_COOKIE_SECURE,
    )

    return {
        "success": True,
        "user": {
            "id": user_profile['id'],
            "username": user_profile['username'],
            "role": user_profile['role']
        }
    }

@router.get("/user", response_model=UserProfile)
async def get_current_user(
    request: Request,
    redis: Redis = Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
):
    session_id = request.cookies.get(app_settings.SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    return UserProfile(
        id=session_data['id'],
        email=session_data['email'],
        username=session_data['username'],
        role=session_data['role'],
        permissions=auth_service.get_permissions(session_data['role'])
    )

@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    redis: Redis = Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
):
    session_id = request.cookies.get(app_settings.SESSION_COOKIE_NAME)
    if session_id:
        await auth_service.logout_session(redis, session_id)

    response.delete_cookie(app_settings.SESSION_COOKIE_NAME)
    return {"success": True, "message": "Logged out"}