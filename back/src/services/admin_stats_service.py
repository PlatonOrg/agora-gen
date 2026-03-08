from datetime import date, timedelta
from typing import Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.log.models import ExoGenerationRequest, ExoGenerationResult, PublishEvent
from src.services.models.admin_stats import AdminStatsResponse, DailyMetrics, SummaryMetrics


async def get_admin_stats(db: AsyncSession, date_from: date, date_to: date) -> AdminStatsResponse:
    """Aggregate admin statistics over a date range with zero-filled daily breakdown."""
    date_to_exclusive = date_to + timedelta(days=1)

    # Query 1: Daily conversations (COUNT DISTINCT session_id from ExoGenerationRequest)
    conv_q = await db.execute(
        select(
            func.date(ExoGenerationRequest.created_at).label("day"),
            func.count(func.distinct(ExoGenerationRequest.session_id)).label("count"),
        )
        .where(
            ExoGenerationRequest.created_at >= date_from,
            ExoGenerationRequest.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGenerationRequest.created_at))
        .order_by(func.date(ExoGenerationRequest.created_at))
    )
    conv_by_day: Dict[date, int] = {row.day: row.count for row in conv_q.all()}

    # Query 2: Daily published exercises (COUNT from PublishEvent)
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

    # Query 3: Daily failures (COUNT from ExoGenerationResult WHERE retry_errors IS NOT NULL)
    fail_q = await db.execute(
        select(
            func.date(ExoGenerationResult.created_at).label("day"),
            func.count().label("count"),
        )
        .where(
            ExoGenerationResult.retry_errors.isnot(None),
            ExoGenerationResult.created_at >= date_from,
            ExoGenerationResult.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGenerationResult.created_at))
        .order_by(func.date(ExoGenerationResult.created_at))
    )
    fail_by_day: Dict[date, int] = {row.day: row.count for row in fail_q.all()}

    # Query 4: Daily avg response time (AVG of (created_at - request_received_at) in ms)
    time_q = await db.execute(
        select(
            func.date(ExoGenerationResult.created_at).label("day"),
            func.avg(
                func.extract("epoch", ExoGenerationResult.created_at - ExoGenerationResult.request_received_at) * 1000
            ).label("avg_ms"),
        )
        .where(
            ExoGenerationResult.request_received_at.isnot(None),
            ExoGenerationResult.created_at >= date_from,
            ExoGenerationResult.created_at < date_to_exclusive,
        )
        .group_by(func.date(ExoGenerationResult.created_at))
        .order_by(func.date(ExoGenerationResult.created_at))
    )
    time_by_day: Dict[date, Optional[float]] = {
        row.day: float(row.avg_ms) if row.avg_ms is not None else None for row in time_q.all()
    }

    # Zero-fill: generate all dates in range
    all_dates = []
    current = date_from
    while current <= date_to:
        all_dates.append(current)
        current += timedelta(days=1)

    # Build daily metrics
    daily = []
    for d in all_dates:
        daily.append(DailyMetrics(
            date=d.isoformat(),
            conversations=conv_by_day.get(d, 0),
            published_exercises=pub_by_day.get(d, 0),
            failures=fail_by_day.get(d, 0),
            avg_response_time_ms=time_by_day.get(d),
        ))

    # Build summary
    total_conversations = sum(m.conversations for m in daily)
    total_published = sum(m.published_exercises for m in daily)
    total_failures = sum(m.failures for m in daily)

    response_times = [m.avg_response_time_ms for m in daily if m.avg_response_time_ms is not None]
    avg_response_time = sum(response_times) / len(response_times) if response_times else None

    summary = SummaryMetrics(
        total_conversations=total_conversations,
        total_published_exercises=total_published,
        total_failures=total_failures,
        avg_response_time_ms=round(avg_response_time, 2) if avg_response_time is not None else None,
    )

    return AdminStatsResponse(
        summary=summary,
        daily=daily,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
    )
