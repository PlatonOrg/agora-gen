import logging

from fastapi import APIRouter, Request

from src.core.config_app import settings
from src.infra.db.redis import get_redis
from src.services.models.api import (
    PlatonDocsQuestionRequest,
    PlatonDocsQuestionResponse,
)
from src.services.rag.platon_docs_qa_service import (
    platon_docs_qa_service,
    get_platon_docs_init_error,
)
from src.services.auth_service import auth_service

router = APIRouter()
logger = logging.getLogger("uvicorn")


@router.post("/platon-docs", response_model=PlatonDocsQuestionResponse)
async def ask_platon_docs(request: PlatonDocsQuestionRequest, req: Request) -> PlatonDocsQuestionResponse:
    init_error = get_platon_docs_init_error()
    if init_error:
        return PlatonDocsQuestionResponse(error=init_error)

    session_id: str | None = req.cookies.get(settings.SESSION_COOKIE_NAME)

    username: str | None = None
    try:
        redis = await get_redis()
        if session_id and redis:
            session_data = await auth_service.get_session_user(redis, session_id)
            if session_data:
                username = session_data.get("username")
    except Exception:
        pass

    try:
        answer, sources = await platon_docs_qa_service.answer_question(
            question=request.question,
            top_k=request.top_k,
            session_id=session_id,
            conversation_id=request.conversation_id,
            username=username,
        )
        return PlatonDocsQuestionResponse(answer=answer, sources=sources)
    except Exception as exc:
        logger.exception("Platon docs QA request failed")
        return PlatonDocsQuestionResponse(error=str(exc))

