from datetime import date, timedelta
from typing import Dict, Optional

from sqlalchemy import func, select, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.log.models import (
    ExoGenerationResult,
    ExoGeneration,
    PublishEvent,
    LogConversation,
)
from src.services.models.admin_stats import AdminStatsResponse, DailyMetrics, SummaryMetrics


async def get_admin_stats(db: AsyncSession, date_from: date, date_to: date) -> AdminStatsResponse:
    """Aggregate admin statistics over a date range with zero-filled daily breakdown.

    All generation/token/response-time metrics are scoped to ExoGeneration rows
    that still belong to a live LogConversation.  This ensures that deleting
    conversations resets the corresponding counters in the dashboard.
    """
    date_to_exclusive = date_to + timedelta(days=1)

    # ── 1. Daily conversation counts ────────────────────────────────────────
    conv_q = await db.execute(
        select(
            func.date(LogConversation.created_at).label("day"),
            func.count(LogConversation.id).label("count"),
        )
        .where(
            LogConversation.created_at >= date_from,
            LogConversation.created_at < date_to_exclusive,
        )
        .group_by(func.date(LogConversation.created_at))
        .order_by(func.date(LogConversation.created_at))
    )
    conv_by_day: Dict[date, int] = {row.day: row.count for row in conv_q.all()}

    # ── 2. Daily published exercises ────────────────────────────────────────
    pub_q = await db.execute(
        select(
            func.date(PublishEvent.created_at).label("day"),
            func.count().label("count"),
        )
        .where(
            PublishEvent.created_at >= date_from,
            PublishEvent.created_at < date_to_exclusive,
        )
        .group_by(func.date(PublishEvent.created_at))
        .order_by(func.date(PublishEvent.created_at))
    )
    pub_by_day: Dict[date, int] = {row.day: row.count for row in pub_q.all()}

    # ── 3. Daily generation health (only for live conversations) ────────────
    # clean         : status='completed', retry_count IS NULL OR retry_count <= 1
    #                 retry_count is NULL or 1 when attempts_used == 1 (first attempt succeeded, no retry)
    # recovered     : status='completed', retry_count >= 2
    #                 retry_count >= 2 means at least one sandbox error triggered a correction+retry
    # fatal         : status='failed'    (sandbox errors exhausted all retries)
    # internal_error: status='error'     (unexpected non-sandbox error)
    health_q = await db.execute(
        select(
            func.date(ExoGeneration.created_at).label("day"),
            func.coalesce(func.count(case(
                (and_(
                    ExoGeneration.status == "completed",
                    or_(
                        ExoGenerationResult.retry_count.is_(None),
                        ExoGenerationResult.retry_count <= 1,
                    ),
                ), 1),
            )), 0).label("clean"),
            func.coalesce(func.count(case(
                (and_(
                    ExoGeneration.status == "completed",
                    ExoGenerationResult.retry_count.isnot(None),
                    ExoGenerationResult.retry_count >= 2,
                ), 1),
            )), 0).label("recovered"),
            func.coalesce(func.count(case(
                (ExoGeneration.status == "failed", 1),
            )), 0).label("fatal"),
            func.coalesce(func.count(case(
                (ExoGeneration.status == "error", 1),
            )), 0).label("internal_error"),
        )
        .outerjoin(ExoGenerationResult, ExoGeneration.generation_result_id == ExoGenerationResult.id)
        .join(LogConversation, ExoGeneration.conversation_fk == LogConversation.id)
        .where(
            ExoGeneration.created_at >= date_from,
            ExoGeneration.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGeneration.created_at))
        .order_by(func.date(ExoGeneration.created_at))
    )
    clean_by_day: Dict[date, int] = {}
    recovered_by_day: Dict[date, int] = {}
    fatal_by_day: Dict[date, int] = {}
    internal_error_by_day: Dict[date, int] = {}
    for row in health_q.all():
        clean_by_day[row.day] = row.clean
        recovered_by_day[row.day] = row.recovered
        fatal_by_day[row.day] = row.fatal
        internal_error_by_day[row.day] = row.internal_error

    # ── 4. Daily avg response time (only for live conversations) ────────────
    time_q = await db.execute(
        select(
            func.date(ExoGenerationResult.created_at).label("day"),
            func.avg(
                func.extract("epoch", ExoGenerationResult.created_at - ExoGenerationResult.request_received_at) * 1000
            ).label("avg_ms"),
        )
        .join(ExoGeneration, ExoGeneration.generation_result_id == ExoGenerationResult.id)
        .join(LogConversation, ExoGeneration.conversation_fk == LogConversation.id)
        .where(
            ExoGenerationResult.request_received_at.isnot(None),
            ExoGenerationResult.created_at >= date_from,
            ExoGenerationResult.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGenerationResult.created_at))
        .order_by(func.date(ExoGenerationResult.created_at))
    )
    time_by_day: Dict[date, Optional[float]] = {
        row.day: float(row.avg_ms) if row.avg_ms is not None else None
        for row in time_q.all()
    }

    # ── 5. Daily token stats (only for live conversations) ──────────────────
    token_q = await db.execute(
        select(
            func.date(ExoGenerationResult.created_at).label("day"),
            func.coalesce(func.sum(ExoGenerationResult.input_tokens), 0).label("total_in"),
            func.coalesce(func.sum(ExoGenerationResult.output_tokens), 0).label("total_out"),
        )
        .join(ExoGeneration, ExoGeneration.generation_result_id == ExoGenerationResult.id)
        .join(LogConversation, ExoGeneration.conversation_fk == LogConversation.id)
        .where(
            ExoGenerationResult.created_at >= date_from,
            ExoGenerationResult.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGenerationResult.created_at))
        .order_by(func.date(ExoGenerationResult.created_at))
    )
    input_tokens_by_day: Dict[date, int] = {}
    output_tokens_by_day: Dict[date, int] = {}
    for row in token_q.all():
        input_tokens_by_day[row.day] = int(row.total_in)
        output_tokens_by_day[row.day] = int(row.total_out)

    # ── Zero-fill all dates in the requested range ───────────────────────────
    all_dates = []
    current = date_from
    while current <= date_to:
        all_dates.append(current)
        current += timedelta(days=1)

    daily = [
        DailyMetrics(
            date=d.isoformat(),
            conversations=conv_by_day.get(d, 0),
            published_exercises=pub_by_day.get(d, 0),
            clean_generations=clean_by_day.get(d, 0),
            recovered_generations=recovered_by_day.get(d, 0),
            fatal_generations=fatal_by_day.get(d, 0),
            internal_error_generations=internal_error_by_day.get(d, 0),
            avg_response_time_ms=time_by_day.get(d),
            total_input_tokens=input_tokens_by_day.get(d, 0),
            total_output_tokens=output_tokens_by_day.get(d, 0),
        )
        for d in all_dates
    ]

    # ── Summary ──────────────────────────────────────────────────────────────
    total_conversations = sum(m.conversations for m in daily)
    total_published = sum(m.published_exercises for m in daily)
    total_clean = sum(m.clean_generations for m in daily)
    total_recovered = sum(m.recovered_generations for m in daily)
    total_fatal = sum(m.fatal_generations for m in daily)
    total_internal_error = sum(m.internal_error_generations for m in daily)
    total_input = sum(m.total_input_tokens for m in daily)
    total_output = sum(m.total_output_tokens for m in daily)

    total_generations = total_clean + total_recovered + total_fatal + total_internal_error
    avg_tokens_per_gen = (
        round((total_input + total_output) / total_generations, 2)
        if total_generations > 0 else None
    )

    response_times = [m.avg_response_time_ms for m in daily if m.avg_response_time_ms is not None]
    avg_response_time = sum(response_times) / len(response_times) if response_times else None

    summary = SummaryMetrics(
        total_conversations=total_conversations,
        total_published_exercises=total_published,
        clean_generations=total_clean,
        recovered_generations=total_recovered,
        fatal_generations=total_fatal,
        internal_error_generations=total_internal_error,
        avg_response_time_ms=round(avg_response_time, 2) if avg_response_time is not None else None,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        avg_tokens_per_generation=avg_tokens_per_gen,
    )

    return AdminStatsResponse(
        summary=summary,
        daily=daily,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
    )
