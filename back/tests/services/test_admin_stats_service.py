"""
Tests for src.services.admin_stats_service.get_admin_stats.

All DB interaction is mocked via a fake AsyncSession — no live database required.
Covers:
- Empty database → all metrics 0, daily empty array
- Single day with data → summary matches daily totals
- Multiple days → daily array has correct per-day breakdown
- Date range filtering → only rows within range counted
- Zero-filling → days with no data show 0 values in daily array
"""
from __future__ import annotations

from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.admin_stats_service import get_admin_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> AsyncMock:
    """Return a minimal async session mock."""
    return AsyncMock()


def _make_row(**kwargs):
    """Build a mock DB row whose attributes mirror the kwargs."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _mock_execute(session: AsyncMock, *result_sets):
    """
    Configure session.execute to return successive result sets.
    Each item in result_sets is a list of rows returned by .all().

    The admin_stats_service calls db.execute() 4 times (conv, pub, fail, time),
    and uses result.all() on each.
    """
    results = []
    for rows in result_sets:
        result = MagicMock()
        result.all.return_value = rows
        results.append(result)
    session.execute = AsyncMock(side_effect=results)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAdminStatsService:

    async def test_empty_database(self):
        """No data → summary all 0, daily is empty list."""
        session = _make_session()
        # 4 queries, all return empty
        _mock_execute(session, [], [], [], [])

        d_from = date(2026, 2, 20)
        d_to = date(2026, 2, 19)  # date_to < date_from → no dates in range
        result = await get_admin_stats(session, d_from, d_to)

        assert result.summary.total_conversations == 0
        assert result.summary.total_published_exercises == 0
        assert result.summary.total_failures == 0
        assert result.summary.avg_response_time_ms is None
        assert result.daily == []

    async def test_single_day_with_data(self):
        """One day with data → summary equals that single day's values."""
        session = _make_session()
        d = date(2026, 2, 20)

        conv_rows = [_make_row(day=d, count=5)]
        pub_rows = [_make_row(day=d, count=3)]
        fail_rows = [_make_row(day=d, count=1)]
        time_rows = [_make_row(day=d, avg_ms=1500.0)]

        _mock_execute(session, conv_rows, pub_rows, fail_rows, time_rows)

        result = await get_admin_stats(session, d, d)

        # Summary
        assert result.summary.total_conversations == 5
        assert result.summary.total_published_exercises == 3
        assert result.summary.total_failures == 1
        assert result.summary.avg_response_time_ms == 1500.0

        # Daily
        assert len(result.daily) == 1
        assert result.daily[0].date == d.isoformat()
        assert result.daily[0].conversations == 5
        assert result.daily[0].published_exercises == 3
        assert result.daily[0].failures == 1
        assert result.daily[0].avg_response_time_ms == 1500.0

    async def test_multiple_days(self):
        """Several days with data → daily array has correct per-day breakdown."""
        session = _make_session()
        d1 = date(2026, 2, 20)
        d2 = date(2026, 2, 21)
        d3 = date(2026, 2, 22)

        conv_rows = [
            _make_row(day=d1, count=2),
            _make_row(day=d2, count=4),
            _make_row(day=d3, count=6),
        ]
        pub_rows = [
            _make_row(day=d1, count=1),
            _make_row(day=d3, count=3),
        ]
        fail_rows = [
            _make_row(day=d2, count=2),
        ]
        time_rows = [
            _make_row(day=d1, avg_ms=1000.0),
            _make_row(day=d2, avg_ms=2000.0),
            _make_row(day=d3, avg_ms=3000.0),
        ]

        _mock_execute(session, conv_rows, pub_rows, fail_rows, time_rows)

        result = await get_admin_stats(session, d1, d3)

        assert len(result.daily) == 3

        # Day 1
        assert result.daily[0].conversations == 2
        assert result.daily[0].published_exercises == 1
        assert result.daily[0].failures == 0
        assert result.daily[0].avg_response_time_ms == 1000.0

        # Day 2
        assert result.daily[1].conversations == 4
        assert result.daily[1].published_exercises == 0
        assert result.daily[1].failures == 2
        assert result.daily[1].avg_response_time_ms == 2000.0

        # Day 3
        assert result.daily[2].conversations == 6
        assert result.daily[2].published_exercises == 3
        assert result.daily[2].failures == 0
        assert result.daily[2].avg_response_time_ms == 3000.0

        # Summary totals
        assert result.summary.total_conversations == 12
        assert result.summary.total_published_exercises == 4
        assert result.summary.total_failures == 2
        assert result.summary.avg_response_time_ms == 2000.0  # (1000+2000+3000)/3

    async def test_date_range_filtering(self):
        """Only rows in the queried range appear in results."""
        session = _make_session()
        d_from = date(2026, 2, 22)
        d_to = date(2026, 2, 23)

        # Mock returns data only for days within range
        conv_rows = [_make_row(day=date(2026, 2, 22), count=10)]
        pub_rows = [_make_row(day=date(2026, 2, 23), count=5)]
        fail_rows = []
        time_rows = []

        _mock_execute(session, conv_rows, pub_rows, fail_rows, time_rows)

        result = await get_admin_stats(session, d_from, d_to)

        assert result.date_from == "2026-02-22"
        assert result.date_to == "2026-02-23"
        assert len(result.daily) == 2
        assert result.summary.total_conversations == 10
        assert result.summary.total_published_exercises == 5

    async def test_zero_filling(self):
        """Sparse data → continuous daily array with 0 values for missing days."""
        session = _make_session()
        d_from = date(2026, 2, 19)
        d_to = date(2026, 2, 23)  # 5-day range

        # Data only on day 1 and day 5
        conv_rows = [_make_row(day=date(2026, 2, 19), count=3)]
        pub_rows = [_make_row(day=date(2026, 2, 23), count=7)]
        fail_rows = []
        time_rows = [_make_row(day=date(2026, 2, 19), avg_ms=500.0)]

        _mock_execute(session, conv_rows, pub_rows, fail_rows, time_rows)

        result = await get_admin_stats(session, d_from, d_to)

        # Should have exactly 5 days
        assert len(result.daily) == 5

        # Day 0 (Feb 19): has data
        assert result.daily[0].date == "2026-02-19"
        assert result.daily[0].conversations == 3
        assert result.daily[0].avg_response_time_ms == 500.0

        # Days 1-3 (Feb 20-22): zero-filled
        for i in range(1, 4):
            assert result.daily[i].conversations == 0
            assert result.daily[i].published_exercises == 0
            assert result.daily[i].failures == 0
            assert result.daily[i].avg_response_time_ms is None

        # Day 4 (Feb 23): has pub data
        assert result.daily[4].date == "2026-02-23"
        assert result.daily[4].published_exercises == 7
        assert result.daily[4].conversations == 0

        # Summary
        assert result.summary.total_conversations == 3
        assert result.summary.total_published_exercises == 7
        assert result.summary.total_failures == 0
        assert result.summary.avg_response_time_ms == 500.0  # only 1 day with time
