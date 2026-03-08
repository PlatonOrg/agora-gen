"""
Tests for src.infra.db.components_repo.

Covers:
- list_component_docs: returns mapped rows, empty table
- list_component_for_form: returns mapped rows, empty table
- list_exercises_using_component: returns rows, respects limit, empty result
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.infra.db.components_repo import (
    list_component_docs,
    list_component_for_form,
    list_exercises_using_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> AsyncMock:
    return AsyncMock()


def _make_mapping_row(**kwargs):
    """Build a row mock whose _mapping attribute returns a dict."""
    row = MagicMock()
    row._mapping = kwargs
    return row


def _mock_execute(session: AsyncMock, rows: list):
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=result)


# ---------------------------------------------------------------------------
# list_component_docs
# ---------------------------------------------------------------------------

class TestListComponentDocs:
    @pytest.mark.asyncio
    async def test_returns_correct_fields(self):
        session = _make_session()
        _mock_execute(session, [
            _make_mapping_row(tag="tag-quiz", description="A quiz widget", usage="For MCQ"),
        ])
        result = await list_component_docs(session)
        assert len(result) == 1
        assert result[0]["tag"] == "tag-quiz"
        assert result[0]["description"] == "A quiz widget"

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty_list(self):
        session = _make_session()
        _mock_execute(session, [])
        result = await list_component_docs(session)
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_rows_returned(self):
        session = _make_session()
        _mock_execute(session, [
            _make_mapping_row(tag="tag-a", description="A", usage="UA"),
            _make_mapping_row(tag="tag-b", description="B", usage="UB"),
        ])
        result = await list_component_docs(session)
        assert len(result) == 2
        assert result[1]["tag"] == "tag-b"


# ---------------------------------------------------------------------------
# list_component_for_form
# ---------------------------------------------------------------------------

class TestListComponentForForm:
    @pytest.mark.asyncio
    async def test_returns_correct_fields(self):
        session = _make_session()
        _mock_execute(session, [
            _make_mapping_row(tag="tag-quiz", name="Quiz", description="D", usage="U", category="Widget"),
        ])
        result = await list_component_for_form(session)
        assert result[0]["tag"] == "tag-quiz"
        assert result[0]["name"] == "Quiz"

    @pytest.mark.asyncio
    async def test_empty_table(self):
        session = _make_session()
        _mock_execute(session, [])
        assert await list_component_for_form(session) == []


# ---------------------------------------------------------------------------
# list_exercises_using_component
# ---------------------------------------------------------------------------

class TestListExercisesUsingComponent:
    @pytest.mark.asyncio
    async def test_returns_exercise_rows(self):
        session = _make_session()
        row = MagicMock()
        row.exercise_id = "ex-1"
        row.exercise_platon_id = "platon-1"
        row.created_at = None
        row.component_tag = "tag-quiz"
        row.component_name = "Quiz"
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [row]
        session.execute = AsyncMock(return_value=result_mock)

        result = await list_exercises_using_component(session, "tag-quiz")
        assert len(result) == 1
        assert result[0]["exercise_platon_id"] == "platon-1"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)
        result = await list_exercises_using_component(session, "tag-missing")
        assert result == []

    @pytest.mark.asyncio
    async def test_sql_receives_correct_tag_and_limit(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        await list_exercises_using_component(session, "tag-quiz", limit=5)

        params = session.execute.call_args[0][1]
        assert params["component_tag"] == "tag-quiz"
        assert params["limit"] == 5

