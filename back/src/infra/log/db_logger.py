from __future__ import annotations

import logging

from sqlalchemy import select

from src.core.sqlalchemy import AsyncSessionLocal
from src.infra.log.models import (
    DiscussionGeneration,
    DiscussionGenerationLog,
    DiscussionGenerationResult,
    DiscussionRagSearch,
    DiscussionRagSearchChunkLink,
    DiscussionRequest,
    ExoGeneration,
    ExoGenerationLog,
    ExoGenerationRequest,
    ExoGenerationRequestComponentLink,
    ExoGenerationResult,
    ExoRagSearch,
    ExoRagSearchResult,
    LogComponentSelection,
    LogConversation,
    Prompt,
    PublishEvent,
    PublishEventLog,
)

logger = logging.getLogger(__name__)


def _rag_log_top_k() -> int:
    """Return the current RAG log top-K from runtime config."""
    from src.services.runtime_config_service import runtime_config, SettingKey
    return runtime_config.get_int(SettingKey.RAG_LOG_TOP_K)


async def _resolve_prompt_id(session, prompt_name: str) -> str | None:
    result = await session.execute(
        select(Prompt.id).where(Prompt.name == prompt_name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("Prompt '%s' not found in log_prompt table", prompt_name)
        return None
    return str(row)


async def _resolve_or_create_conversation(session, conversation_id: str | None, session_id: str | None, username: str | None) -> str | None:
    if not conversation_id:
        return None
    result = await session.execute(
        select(LogConversation.id).where(LogConversation.conversation_id == conversation_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return str(row)
    conv = LogConversation(
        conversation_id=conversation_id,
        session_id=session_id,
        username=username,
    )
    session.add(conv)
    await session.flush()
    return str(conv.id)


async def log_exo_generation(payload: ExoGenerationLog) -> None:
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                conversation_history = None
                if payload.conversation_history:
                    conversation_history = [
                        m.model_dump() if hasattr(m, "model_dump") else m
                        for m in payload.conversation_history
                    ]

                request_row = ExoGenerationRequest(
                    request=payload.user_request,
                    session_id=payload.session_id,
                    fields_to_modify=payload.fields_to_modify or None,
                    variables=payload.variables or None,
                    file_names=payload.file_names or None,
                    file_summaries=payload.file_summaries or None,
                    conversation_history=conversation_history,
                    current_exercise_state=payload.current_exercise_state,
                )
                session.add(request_row)
                await session.flush()

                for tag in payload.components:
                    session.add(ExoGenerationRequestComponentLink(
                        request_id=request_row.id,
                        component_tag=tag,
                    ))

                top_k = _rag_log_top_k()
                rag_search_row = None
                if payload.retrieved_chunks:
                    rag_search_row = ExoRagSearch(
                        embedding_model=payload.embedding_model,
                        vector_table=payload.vector_table,
                        query=payload.rag_query,
                    )
                    session.add(rag_search_row)
                    await session.flush()

                    for rank, chunk in enumerate(payload.retrieved_chunks[:top_k], start=1):
                        md = chunk.metadata or {}
                        session.add(ExoRagSearchResult(
                            search_id=rag_search_row.id,
                            rank=rank,
                            vector_row_id=str(md.get("id") or md.get("db_id") or ""),
                            platon_id=str(md.get("platon_id") or md.get("resource_id") or ""),
                            resource_name=str(md.get("name") or md.get("title") or ""),
                            kind=str(chunk.doc_type or ""),
                            score=chunk.score,
                        ))

                prompt_id = await _resolve_prompt_id(session, payload.system_prompt_name)

                generation_result_row = ExoGenerationResult(
                    system_prompt_name=payload.system_prompt_name,
                    prompt_id=prompt_id,
                    examples_used=payload.examples_used or None,
                    llm_raw_output=payload.llm_raw_output or None,
                    llm_output=payload.llm_output,
                    llm_provider=payload.llm_provider,
                    llm_model=payload.llm_model,
                    preview_url=payload.preview_url or None,
                    retry_count=payload.retry_count or None,
                    retry_errors=payload.retry_errors or None,
                    request_received_at=payload.request_received_at,
                    input_tokens=payload.input_tokens,
                    output_tokens=payload.output_tokens,
                    llm_request_count=payload.llm_request_count,
                    llm_calls=payload.llm_calls or None,
                )
                session.add(generation_result_row)
                await session.flush()

                component_selection_row = None
                if payload.component_selection is not None:
                    cs = payload.component_selection
                    component_selection_row = LogComponentSelection(
                        user_request=cs.user_request,
                        user_priority_tags=cs.user_priority_tags or None,
                        selected_tags=cs.selected_tags or None,
                        llm_provider=cs.llm_provider,
                        llm_model=cs.llm_model,
                        reasoning=cs.reasoning,
                        input_tokens=cs.input_tokens,
                        output_tokens=cs.output_tokens,
                    )
                    session.add(component_selection_row)
                    await session.flush()

                conversation_fk = await _resolve_or_create_conversation(
                    session, payload.conversation_id, payload.session_id, payload.username,
                )

                session.add(ExoGeneration(
                    request_id=request_row.id,
                    rag_search_id=rag_search_row.id if rag_search_row else None,
                    generation_result_id=generation_result_row.id,
                    component_selection_id=component_selection_row.id if component_selection_row else None,
                    conversation_fk=conversation_fk,
                    status=payload.status,
                    username=payload.username,
                ))

    except Exception as exc:
        logger.error("DB log for exo generation failed: %s", exc)


async def log_discussion_generation(payload: DiscussionGenerationLog) -> None:
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                request_row = DiscussionRequest(
                    request=payload.user_request,
                    session_id=payload.session_id,
                )
                session.add(request_row)
                await session.flush()

                top_k = _rag_log_top_k()
                rag_search_row = DiscussionRagSearch(
                    embedding_model=payload.embedding_model,
                    vector_table=payload.vector_table,
                    query=payload.rag_query,
                )
                session.add(rag_search_row)
                await session.flush()

                for rank, chunk in enumerate(payload.retrieved_chunks[:top_k], start=1):
                    md = chunk.metadata or {}
                    session.add(DiscussionRagSearchChunkLink(
                        search_id=rag_search_row.id,
                        rank=rank,
                        vector_row_id=str(md.get("id") or md.get("db_id") or ""),
                        chunk_text=chunk.content,
                        source_path=str(md.get("source_path") or md.get("name") or ""),
                        score=chunk.score,
                    ))

                prompt_id = await _resolve_prompt_id(session, payload.system_prompt_name)

                generation_result_row = DiscussionGenerationResult(
                    system_prompt_name=payload.system_prompt_name,
                    prompt_id=prompt_id,
                    chunks_used=[
                        {
                            "source_path": str((c.metadata or {}).get("source_path", "")),
                            "chunk_index": (c.metadata or {}).get("chunk_index"),
                            "score": c.score,
                            "excerpt": (c.content or "")[:400],
                        }
                        for c in payload.retrieved_chunks[:top_k]
                    ],
                    llm_raw_output=payload.llm_raw_output or None,
                    llm_output=payload.llm_output,
                    llm_provider=payload.llm_provider,
                    llm_model=payload.llm_model,
                    input_tokens=payload.input_tokens,
                    output_tokens=payload.output_tokens,
                )
                session.add(generation_result_row)
                await session.flush()

                conversation_fk = await _resolve_or_create_conversation(
                    session, payload.conversation_id, payload.session_id, payload.username,
                )

                session.add(DiscussionGeneration(
                    request_id=request_row.id,
                    rag_search_id=rag_search_row.id,
                    generation_result_id=generation_result_row.id,
                    conversation_fk=conversation_fk,
                    status="completed",
                    username=payload.username,
                ))

    except Exception as exc:
        logger.error("DB log for discussion generation failed: %s", exc)


async def log_publish_event(payload: PublishEventLog) -> None:
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(PublishEvent(
                    exercise_id=payload.exercise_id,
                    platon_resource_id=payload.platon_resource_id,
                    session_id=payload.session_id,
                    conversation_id=payload.conversation_id,
                    username=payload.username,
                    template_id=payload.template_id,
                ))
    except Exception as exc:
        logger.error("DB log for publish event failed: %s", exc)
