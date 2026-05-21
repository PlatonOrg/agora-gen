from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from src.api.v1.dependencies import require_session_id
from src.core.sqlalchemy import get_db_session
from src.infra.db.redis import get_redis
from src.services.admin_stats_service import get_admin_stats
from src.services.auth_service import auth_service
from src.services.models.admin_stats import (
    AdminStatsResponse,
    LLMOptionEntry,
    LLMOptionsResponse,
    SetLLMConfigRequest,
    SetLLMConfigResponse,
    RuntimeSettingEntry,
    RuntimeSettingsResponse,
    UpdateRuntimeSettingsRequest,
    UpdateRuntimeSettingsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class VectorRebuildResponse(BaseModel):
    status: str
    message: str


async def get_current_admin_user(
    session_id: str = Depends(require_session_id),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Reusable dependency that validates the caller is an authenticated admin."""

    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    role = (session_data.get("role") or "").lower()
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return session_data


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session_data: dict = Depends(get_current_admin_user),
    db=Depends(get_db_session),
):
    """Return aggregated admin statistics for the given date range."""
    if date_from is None:
        date_from_obj = date.today() - timedelta(days=7)
    else:
        try:
            date_from_obj = date.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date_from format. Use YYYY-MM-DD",
            )

    if date_to is None:
        date_to_obj = date.today()
    else:
        try:
            date_to_obj = date.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date_to format. Use YYYY-MM-DD",
            )

    return await get_admin_stats(db, date_from_obj, date_to_obj)


@router.get("/llm-options", response_model=LLMOptionsResponse)
async def list_llm_options(
    session_data: dict = Depends(get_current_admin_user),
) -> LLMOptionsResponse:
    """Return all registered LLM provider/model pairs and the current default.

    Admin-only. Used by the frontend configuration dropdown.
    For providers that support dynamic model discovery (e.g. Ragustave),
    the model list is refreshed from the remote API before responding.
    """
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider

    try:
        registry = get_llm_registry()

        for provider_name in registry.registered_names:
            provider = registry.get(provider_name)
            if isinstance(provider, RagustaveProvider):
                try:
                    remote_models = await provider.fetch_available_models()
                    if remote_models:
                        registry.update_models(provider_name, remote_models)
                except Exception as fetch_exc:
                    logger.warning(
                        "Failed to fetch dynamic models for '%s': %s",
                        provider_name,
                        fetch_exc,
                    )

        options = [
            LLMOptionEntry(provider=entry["provider"], model=entry["model"])
            for entry in registry.available_options()
        ]
        return LLMOptionsResponse(
            options=options,
            current_provider=registry.default_provider_name,
            current_model=registry.default_model_for(registry.default_provider_name),
        )
    except Exception as exc:
        logger.exception("Failed to list LLM options")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/llm-config", response_model=SetLLMConfigResponse)
async def set_llm_config(
    payload: SetLLMConfigRequest,
    session_data: dict = Depends(get_current_admin_user),
) -> SetLLMConfigResponse:
    """Switch the system-wide default LLM provider and model at runtime.

    Admin-only. For providers that support dynamic model discovery, the
    model list is refreshed before validation to ensure newly available
    models are accepted.
    """
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider

    try:
        registry = get_llm_registry()

        provider = registry.get(payload.provider)
        if isinstance(provider, RagustaveProvider):
            try:
                remote_models = await provider.fetch_available_models()
                if remote_models:
                    registry.update_models(payload.provider, remote_models)
            except Exception as fetch_exc:
                logger.warning(
                    "Failed to refresh dynamic models for '%s' before config update: %s",
                    payload.provider,
                    fetch_exc,
                )

        registry.set_default(payload.provider, payload.model)

        logger.info(
            "Admin '%s' switched LLM config to provider='%s', model='%s'",
            session_data.get("username", "unknown"),
            payload.provider,
            payload.model,
        )

        return SetLLMConfigResponse(
            provider=payload.provider,
            model=payload.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update LLM config")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# -- Runtime Settings (database-backed) -----------------------------------


@router.get("/settings", response_model=RuntimeSettingsResponse)
async def list_runtime_settings(
    session_data: dict = Depends(get_current_admin_user),
) -> RuntimeSettingsResponse:
    """Return all admin-tuneable runtime settings with metadata.

    The response includes value type, description, default, and
    validation constraints so the frontend can render an appropriate
    input control for each setting.
    """
    from src.services.runtime_config_service import runtime_config

    entries = runtime_config.get_all_with_metadata()
    return RuntimeSettingsResponse(
        settings=[RuntimeSettingEntry(**entry) for entry in entries],
    )


@router.put("/settings", response_model=UpdateRuntimeSettingsResponse)
async def update_runtime_settings(
    payload: UpdateRuntimeSettingsRequest,
    session_data: dict = Depends(get_current_admin_user),
    db=Depends(get_db_session),
) -> UpdateRuntimeSettingsResponse:
    """Update one or more runtime settings.

    Only keys declared in the server-side allowlist are accepted.
    Values are validated against type and range constraints before
    being persisted to the database and applied in-memory.
    """
    from src.services.runtime_config_service import runtime_config

    try:
        updated = await runtime_config.update_settings(
            updates=payload.settings,
            session=db,
            updated_by=session_data.get("username", "unknown"),
        )
        return UpdateRuntimeSettingsResponse(updated=updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update runtime settings")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# -- Vector store rebuild -------------------------------------------------------


@router.post("/vector/rebuild", response_model=VectorRebuildResponse)
async def trigger_vector_rebuild(
    session_data: dict = Depends(get_current_admin_user),
) -> VectorRebuildResponse:
    """Trigger a full vector store rebuild in the background.

    Drops all existing embeddings and re-embeds every resource from scratch,
    picking up the new metadata fields (levels, topics, cercle) added to nodes.
    The rebuild runs asynchronously — this endpoint returns immediately.
    Monitor progress in the container logs.
    """
    from src.core.sqlalchemy import engine as app_engine
    from src.infra.db.redis import get_redis as _get_redis
    from src.infra.platon import platon_admin_auth, PlatonCache, CachedPlatonClient
    from src.services.platon_service import platon_service
    from src.core.config_app import settings
    from src.infra.vector.exercise_vector_service import run_full_rebuild

    async def _do_rebuild() -> None:
        try:
            admin_token = await platon_admin_auth.authenticate()
        except Exception as exc:
            logger.error("Vector rebuild — Platon admin auth failed: %s", exc)
            return
        try:
            redis = await _get_redis()
            client = CachedPlatonClient(
                platon=platon_service,
                cache=PlatonCache(redis, ttl_seconds=settings.PLATON_CACHE_TTL_SECONDS),
            )
            await run_full_rebuild(app_engine, client, admin_token=admin_token)
            logger.info(
                "Vector rebuild completed. Triggered by admin '%s'.",
                session_data.get("username", "unknown"),
            )
        except Exception as exc:
            logger.error("Vector rebuild failed: %s", exc, exc_info=True)

    asyncio.ensure_future(_do_rebuild())
    logger.info(
        "Vector rebuild triggered by admin '%s'.",
        session_data.get("username", "unknown"),
    )
    return VectorRebuildResponse(
        status="rebuild_started",
        message="Full vector store rebuild started in background. Monitor progress in container logs.",
    )


