from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.core.sqlalchemy import get_db_session
from src.services.logs_service import (
    get_all_prompts,
    get_session_summaries,
    get_session_detail,
    get_generation_stats,
    get_app_config,
    get_conversation_summaries,
    get_conversation_detail,
    delete_conversation,
)
from src.services.models.logs import (
    PromptEntry,
    SessionSummary,
    SessionDetail,
    GenerationStats,
    AppConfig,
    ConversationSummary,
    ConversationDetail,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/prompts", response_model=List[PromptEntry])
async def list_prompts(session=Depends(get_db_session)) -> List[PromptEntry]:
    try:
        return await get_all_prompts(session)
    except Exception as exc:
        logger.exception("Failed to list prompts")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(session=Depends(get_db_session)) -> List[ConversationSummary]:
    try:
        return await get_conversation_summaries(session)
    except Exception as exc:
        logger.exception("Failed to list conversations")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, session=Depends(get_db_session)) -> ConversationDetail:
    try:
        detail = await get_conversation_detail(conversation_id, session)
        if detail is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get conversation detail for %s", conversation_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str, session=Depends(get_db_session)):
    try:
        deleted = await delete_conversation(conversation_id, session)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete conversation %s", conversation_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions(session=Depends(get_db_session)) -> List[SessionSummary]:
    try:
        return await get_session_summaries(session)
    except Exception as exc:
        logger.exception("Failed to list sessions")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, session=Depends(get_db_session)) -> SessionDetail:
    try:
        detail = await get_session_detail(session_id, session)
        if detail is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get session detail for %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats", response_model=GenerationStats)
async def generation_stats(session=Depends(get_db_session)) -> GenerationStats:
    try:
        return await get_generation_stats(session)
    except Exception as exc:
        logger.exception("Failed to get generation stats")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/config", response_model=AppConfig)
async def app_config() -> AppConfig:
    try:
        return get_app_config()
    except Exception as exc:
        logger.exception("Failed to get app config")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

