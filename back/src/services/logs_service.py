from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.infra.log.models import (
    Prompt,
    ExoGeneration,
    DiscussionGeneration,
    ExoGenerationRequest,
    DiscussionRequest,
    ExoRagSearch,
    DiscussionRagSearch,
    ExoGenerationResult,
    DiscussionGenerationResult,
    LogComponentSelection,
    LogConversation,
)
from src.services.models.logs import (
    PromptEntry,
    SessionSummary,
    SessionDetail,
    ConversationSummary,
    ConversationDetail,
    ExoGenerationDetail,
    DiscussionGenerationDetail,
    ExoRequestInfo,
    DiscussionRequestInfo,
    RagSearchInfo,
    RagSearchResult,
    DocRagSearchInfo,
    DocChunkResult,
    LlmResultInfo,
    DiscussionLlmResultInfo,
    GenerationStats,
    GenerationStatsEntry,
    AppConfig,
    ComponentSelectionInfo,
    LlmCallRecord,
)

logger = logging.getLogger(__name__)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


async def get_all_prompts(session: AsyncSession) -> List[PromptEntry]:
    result = await session.execute(
        select(Prompt).order_by(Prompt.name)
    )
    rows = result.scalars().all()
    return [
        PromptEntry(
            id=str(row.id),
            name=row.name,
            content=row.content,
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
        )
        for row in rows
    ]


def _build_exo_detail(row) -> ExoGenerationDetail:
    req = row.request_row
    rag = row.rag_search
    res = row.generation_result

    request_info: Optional[ExoRequestInfo] = None
    if req:
        request_info = ExoRequestInfo(
            id=str(req.id),
            user_request=req.request,
            session_id=req.session_id,
            fields_to_modify=req.fields_to_modify,
            variables=req.variables,
            file_names=req.file_names,
            file_summaries=req.file_summaries,
            conversation_history=req.conversation_history,
            current_exercise_state=req.current_exercise_state,
            components=[link.component_tag for link in (req.component_links or [])],
            created_at=_iso(req.created_at),
        )

    rag_info: Optional[RagSearchInfo] = None
    if rag:
        rag_info = RagSearchInfo(
            query=rag.query,
            embedding_model=rag.embedding_model,
            vector_table=rag.vector_table,
            created_at=_iso(rag.created_at),
            results=[
                RagSearchResult(
                    rank=n.rank,
                    platon_id=n.platon_id,
                    resource_name=n.resource_name,
                    kind=n.kind,
                    score=n.score,
                )
                for n in sorted(rag.result_nodes or [], key=lambda x: x.rank)
            ],
        )

    llm_info: Optional[LlmResultInfo] = None
    if res:
        raw_calls = res.llm_calls or []
        parsed_calls = [
            LlmCallRecord(
                call_type=c.get("call_type", "unknown"),
                provider=c.get("provider", ""),
                model=c.get("model", ""),
                input_tokens=c.get("input_tokens"),
                output_tokens=c.get("output_tokens"),
                system_prompt_chars=c.get("system_prompt_chars"),
                user_prompt_chars=c.get("user_prompt_chars"),
            )
            for c in raw_calls
            if isinstance(c, dict)
        ]
        llm_info = LlmResultInfo(
            system_prompt_name=res.system_prompt_name,
            system_prompt_content=res.prompt.content if res.prompt else None,
            examples_used=res.examples_used,
            llm_output=res.llm_output,
            llm_provider=res.llm_provider,
            llm_model=res.llm_model,
            preview_url=res.preview_url,
            retry_count=res.retry_count,
            retry_errors=res.retry_errors,
            created_at=_iso(res.created_at),
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            llm_request_count=res.llm_request_count,
            llm_calls=parsed_calls if parsed_calls else None,
        )

    cs = row.component_selection
    component_selection_info = None
    if cs:
        component_selection_info = ComponentSelectionInfo(
            user_priority_tags=cs.user_priority_tags or [],
            selected_tags=cs.selected_tags or [],
            llm_provider=cs.llm_provider,
            llm_model=cs.llm_model,
            reasoning=cs.reasoning,
            input_tokens=cs.input_tokens,
            output_tokens=cs.output_tokens,
            created_at=_iso(cs.created_at),
        )

    return ExoGenerationDetail(
        id=str(row.id),
        kind="exercise",
        created_at=_iso(row.created_at),
        status=getattr(row, "status", None),
        username=getattr(row, "username", None),
        request=request_info,
        rag_search=rag_info,
        llm_result=llm_info,
        component_selection=component_selection_info,
    )


def _build_disc_detail(row) -> DiscussionGenerationDetail:
    req = row.request_row
    rag = row.rag_search
    res = row.generation_result

    request_info_d: Optional[DiscussionRequestInfo] = None
    if req:
        request_info_d = DiscussionRequestInfo(
            id=str(req.id),
            user_request=req.request,
            session_id=req.session_id,
            created_at=_iso(req.created_at),
        )

    doc_rag_info: Optional[DocRagSearchInfo] = None
    if rag:
        doc_rag_info = DocRagSearchInfo(
            query=rag.query,
            embedding_model=rag.embedding_model,
            vector_table=rag.vector_table,
            created_at=_iso(rag.created_at),
            chunks=[
                DocChunkResult(
                    rank=c.rank,
                    chunk_text=c.chunk_text,
                    source_path=c.source_path,
                    score=c.score,
                )
                for c in sorted(rag.chunk_links or [], key=lambda x: x.rank)
            ],
        )

    disc_llm_info: Optional[DiscussionLlmResultInfo] = None
    if res:
        disc_llm_info = DiscussionLlmResultInfo(
            system_prompt_name=res.system_prompt_name,
            system_prompt_content=res.prompt.content if res.prompt else None,
            chunks_used=res.chunks_used,
            llm_output=res.llm_output,
            llm_provider=res.llm_provider,
            llm_model=res.llm_model,
            created_at=_iso(res.created_at),
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
        )

    return DiscussionGenerationDetail(
        id=str(row.id),
        kind="discussion",
        created_at=_iso(row.created_at),
        status=getattr(row, "status", None),
        username=getattr(row, "username", None),
        request=request_info_d,
        rag_search=doc_rag_info,
        llm_result=disc_llm_info,
    )


def _exo_query_options():
    return [
        selectinload(ExoGeneration.request_row).selectinload(ExoGenerationRequest.component_links),
        selectinload(ExoGeneration.rag_search).selectinload(ExoRagSearch.result_nodes),
        selectinload(ExoGeneration.generation_result).selectinload(ExoGenerationResult.prompt),
        selectinload(ExoGeneration.component_selection),
    ]


def _disc_query_options():
    return [
        selectinload(DiscussionGeneration.request_row),
        selectinload(DiscussionGeneration.rag_search).selectinload(DiscussionRagSearch.chunk_links),
        selectinload(DiscussionGeneration.generation_result).selectinload(DiscussionGenerationResult.prompt),
    ]


async def get_conversation_summaries(db: AsyncSession) -> List[ConversationSummary]:
    result = await db.execute(
        select(
            LogConversation.conversation_id,
            LogConversation.session_id,
            LogConversation.username,
            LogConversation.created_at,
            func.count(func.distinct(ExoGeneration.id)).label("exo_count"),
            func.count(func.distinct(DiscussionGeneration.id)).label("disc_count"),
            func.max(ExoGeneration.created_at).label("last_exo_at"),
            func.max(DiscussionGeneration.created_at).label("last_disc_at"),
        )
        .outerjoin(ExoGeneration, ExoGeneration.conversation_fk == LogConversation.id)
        .outerjoin(DiscussionGeneration, DiscussionGeneration.conversation_fk == LogConversation.id)
        .group_by(LogConversation.id)
        .order_by(LogConversation.created_at.desc())
    )
    summaries: List[ConversationSummary] = []
    for row in result.all():
        exo_count = row.exo_count or 0
        disc_count = row.disc_count or 0
        dates = [d for d in [row.last_exo_at, row.last_disc_at] if d is not None]
        last_at = _iso(max(dates)) if dates else _iso(row.created_at)
        summaries.append(ConversationSummary(
            conversation_id=row.conversation_id,
            session_id=row.session_id,
            username=row.username,
            exo_generation_count=exo_count,
            discussion_generation_count=disc_count,
            total_generation_count=exo_count + disc_count,
            started_at=_iso(row.created_at),
            last_at=last_at,
        ))

    orphan_exo_q = await db.execute(
        select(
            ExoGeneration.username,
            ExoGeneration.created_at,
        )
        .where(ExoGeneration.conversation_fk.is_(None))
        .order_by(ExoGeneration.created_at.desc())
    )
    orphan_exo_rows = orphan_exo_q.all()

    orphan_disc_q = await db.execute(
        select(
            DiscussionGeneration.username,
            DiscussionGeneration.created_at,
        )
        .where(DiscussionGeneration.conversation_fk.is_(None))
        .order_by(DiscussionGeneration.created_at.desc())
    )
    orphan_disc_rows = orphan_disc_q.all()

    if orphan_exo_rows or orphan_disc_rows:
        earliest = min(
            [r.created_at for r in orphan_exo_rows if r.created_at] +
            [r.created_at for r in orphan_disc_rows if r.created_at],
            default=None,
        )
        latest = max(
            [r.created_at for r in orphan_exo_rows if r.created_at] +
            [r.created_at for r in orphan_disc_rows if r.created_at],
            default=None,
        )
        username = next(
            (r.username for r in orphan_exo_rows if r.username),
            next((r.username for r in orphan_disc_rows if r.username), None),
        )
        summaries.append(ConversationSummary(
            conversation_id="__orphan__",
            session_id=None,
            username=username,
            exo_generation_count=len(orphan_exo_rows),
            discussion_generation_count=len(orphan_disc_rows),
            total_generation_count=len(orphan_exo_rows) + len(orphan_disc_rows),
            started_at=_iso(earliest),
            last_at=_iso(latest),
        ))

    summaries.sort(key=lambda s: s.started_at or "", reverse=True)
    return summaries


async def get_conversation_detail(conversation_id: str, db: AsyncSession) -> Optional[ConversationDetail]:
    # Special synthetic conversation that aggregates orphaned generations.
    if conversation_id == "__orphan__":
        exo_q = await db.execute(
            select(ExoGeneration)
            .where(ExoGeneration.conversation_fk.is_(None))
            .options(*_exo_query_options())
            .order_by(ExoGeneration.created_at)
        )
        exo_rows = exo_q.scalars().all()

        disc_q = await db.execute(
            select(DiscussionGeneration)
            .where(DiscussionGeneration.conversation_fk.is_(None))
            .options(*_disc_query_options())
            .order_by(DiscussionGeneration.created_at)
        )
        disc_rows = disc_q.scalars().all()

        if not exo_rows and not disc_rows:
            return None

        exo_details = [_build_exo_detail(r) for r in exo_rows]
        disc_details = [_build_disc_detail(r) for r in disc_rows]
        all_dates = [d.created_at for d in exo_details + disc_details if d.created_at]
        username = next((r.username for r in exo_rows if r.username), None)
        return ConversationDetail(
            conversation_id="__orphan__",
            session_id=None,
            username=username,
            started_at=min(all_dates) if all_dates else None,
            last_at=max(all_dates) if all_dates else None,
            exo_generations=exo_details,
            discussion_generations=disc_details,
        )

    conv_result = await db.execute(
        select(LogConversation).where(LogConversation.conversation_id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        return None

    exo_q = await db.execute(
        select(ExoGeneration)
        .where(ExoGeneration.conversation_fk == conv.id)
        .options(*_exo_query_options())
        .order_by(ExoGeneration.created_at)
    )
    exo_rows = exo_q.scalars().all()

    disc_q = await db.execute(
        select(DiscussionGeneration)
        .where(DiscussionGeneration.conversation_fk == conv.id)
        .options(*_disc_query_options())
        .order_by(DiscussionGeneration.created_at)
    )
    disc_rows = disc_q.scalars().all()

    exo_details = [_build_exo_detail(r) for r in exo_rows]
    disc_details = [_build_disc_detail(r) for r in disc_rows]

    all_dates = []
    for d in exo_details + disc_details:
        if d.created_at:
            all_dates.append(d.created_at)

    return ConversationDetail(
        conversation_id=conv.conversation_id,
        session_id=conv.session_id,
        username=conv.username,
        started_at=min(all_dates) if all_dates else _iso(conv.created_at),
        last_at=max(all_dates) if all_dates else _iso(conv.created_at),
        exo_generations=exo_details,
        discussion_generations=disc_details,
    )


async def get_session_summaries(session: AsyncSession) -> List[SessionSummary]:
    exo_q = await session.execute(
        select(
            ExoGenerationRequest.session_id,
            func.count(ExoGeneration.id).label("exo_count"),
            func.min(ExoGenerationRequest.created_at).label("started_at"),
            func.max(ExoGenerationRequest.created_at).label("last_at"),
        )
        .join(ExoGeneration, ExoGeneration.request_id == ExoGenerationRequest.id, isouter=True)
        .where(ExoGenerationRequest.session_id.isnot(None))
        .group_by(ExoGenerationRequest.session_id)
    )
    exo_rows = {row.session_id: row for row in exo_q.all()}

    disc_q = await session.execute(
        select(
            DiscussionRequest.session_id,
            func.count(DiscussionGeneration.id).label("disc_count"),
            func.min(DiscussionRequest.created_at).label("started_at"),
            func.max(DiscussionRequest.created_at).label("last_at"),
        )
        .join(DiscussionGeneration, DiscussionGeneration.request_id == DiscussionRequest.id, isouter=True)
        .where(DiscussionRequest.session_id.isnot(None))
        .group_by(DiscussionRequest.session_id)
    )
    disc_rows = {row.session_id: row for row in disc_q.all()}

    all_session_ids = set(exo_rows.keys()) | set(disc_rows.keys())

    summaries: List[SessionSummary] = []
    for sid in all_session_ids:
        exo = exo_rows.get(sid)
        disc = disc_rows.get(sid)

        exo_count = exo.exo_count if exo else 0
        disc_count = disc.disc_count if disc else 0

        dates = []
        if exo and exo.started_at:
            dates.append(exo.started_at)
        if disc and disc.started_at:
            dates.append(disc.started_at)
        if exo and exo.last_at:
            dates.append(exo.last_at)
        if disc and disc.last_at:
            dates.append(disc.last_at)

        started_at = min(dates).isoformat() if dates else None
        last_at = max(dates).isoformat() if dates else None

        summaries.append(SessionSummary(
            session_id=str(sid),
            exo_generation_count=exo_count,
            discussion_generation_count=disc_count,
            total_generation_count=exo_count + disc_count,
            started_at=started_at,
            last_at=last_at,
        ))

    summaries.sort(key=lambda s: s.started_at or "", reverse=True)
    return summaries


async def get_session_detail(session_id: str, db: AsyncSession) -> Optional[SessionDetail]:
    exo_q = await db.execute(
        select(ExoGeneration)
        .join(ExoGenerationRequest, ExoGeneration.request_id == ExoGenerationRequest.id, isouter=True)
        .where(ExoGenerationRequest.session_id == session_id)
        .options(*_exo_query_options())
        .order_by(ExoGeneration.created_at)
    )
    exo_rows = exo_q.scalars().all()

    disc_q = await db.execute(
        select(DiscussionGeneration)
        .join(DiscussionRequest, DiscussionGeneration.request_id == DiscussionRequest.id, isouter=True)
        .where(DiscussionRequest.session_id == session_id)
        .options(*_disc_query_options())
        .order_by(DiscussionGeneration.created_at)
    )
    disc_rows = disc_q.scalars().all()

    if not exo_rows and not disc_rows:
        return None

    exo_details = [_build_exo_detail(r) for r in exo_rows]
    disc_details = [_build_disc_detail(r) for r in disc_rows]

    all_dates = []
    for d in exo_details + disc_details:
        if d.created_at:
            all_dates.append(d.created_at)

    return SessionDetail(
        session_id=session_id,
        started_at=min(all_dates) if all_dates else None,
        last_at=max(all_dates) if all_dates else None,
        exo_generations=exo_details,
        discussion_generations=disc_details,
    )


async def get_generation_stats(db: AsyncSession) -> GenerationStats:
    exo_q = await db.execute(
        select(
            ExoRagSearch.embedding_model,
            ExoGenerationResult.llm_provider,
            ExoGenerationResult.llm_model,
            func.count(ExoGenerationResult.id).label("count"),
        )
        .join(ExoGeneration, ExoGeneration.generation_result_id == ExoGenerationResult.id, isouter=True)
        .join(ExoRagSearch, ExoGeneration.rag_search_id == ExoRagSearch.id, isouter=True)
        .group_by(ExoRagSearch.embedding_model, ExoGenerationResult.llm_provider, ExoGenerationResult.llm_model)
    )

    disc_q = await db.execute(
        select(
            DiscussionRagSearch.embedding_model,
            DiscussionGenerationResult.llm_provider,
            DiscussionGenerationResult.llm_model,
            func.count(DiscussionGenerationResult.id).label("count"),
        )
        .join(DiscussionGeneration, DiscussionGeneration.generation_result_id == DiscussionGenerationResult.id, isouter=True)
        .join(DiscussionRagSearch, DiscussionGeneration.rag_search_id == DiscussionRagSearch.id, isouter=True)
        .group_by(DiscussionRagSearch.embedding_model, DiscussionGenerationResult.llm_provider, DiscussionGenerationResult.llm_model)
    )

    exo_entries = [
        GenerationStatsEntry(
            kind="exercise",
            embedding_model=row.embedding_model or "",
            llm_provider=row.llm_provider,
            llm_model=row.llm_model,
            count=row.count,
        )
        for row in exo_q.all()
    ]
    disc_entries = [
        GenerationStatsEntry(
            kind="discussion",
            embedding_model=row.embedding_model or "",
            llm_provider=row.llm_provider,
            llm_model=row.llm_model,
            count=row.count,
        )
        for row in disc_q.all()
    ]

    return GenerationStats(exo=exo_entries, discussion=disc_entries)


def get_app_config() -> AppConfig:
    from src.core.di import get_llm_registry
    from src.services.rag.retrieval_service import get_embed_model
    from src.core.config_app import settings
    from src.core import path_constants

    registry = get_llm_registry()
    provider_name = registry.default_provider_name
    llm_model = registry.default_model_for(provider_name)

    embed = get_embed_model()
    exo_embed_model = getattr(embed, "model_name", str(embed))

    return AppConfig(
        exo_embedding_model=exo_embed_model,
        exo_llm_provider=provider_name,
        exo_llm_model=llm_model,
        discussion_embedding_model=str(path_constants.PLATON_DOCS_EMBED_MODEL),
        discussion_llm_provider=provider_name,
        discussion_llm_model=llm_model,
    )
