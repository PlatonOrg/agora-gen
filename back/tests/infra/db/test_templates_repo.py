"""
Tests for src.infra.db.templates_repo and src.infra.db.template_uses_repo.

All DB interaction is mocked via a fake AsyncSession — no live database required.
Covers:
- find_templates_by_component_tags: empty tags, no matching components, matching templates
- get_all_templates: returns all rows correctly
- list_exercises_using_template: SQL executed with correct parameters
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

from src.infra.db.templates_repo import find_templates_by_component_tags, get_all_templates
from src.infra.db.template_uses_repo import list_exercises_using_template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> AsyncMock:
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
    Each item in result_sets is a list of rows returned by .fetchall().
    """
    results = []
    for rows in result_sets:
        result = MagicMock()
        result.fetchall.return_value = rows
        results.append(result)
    session.execute = AsyncMock(side_effect=results)


# ---------------------------------------------------------------------------
# find_templates_by_component_tags
# ---------------------------------------------------------------------------

class TestFindTemplatesByComponentTags:
    @pytest.mark.asyncio
    async def test_empty_tags_returns_empty_list(self):
        session = _make_session()
        result = await find_templates_by_component_tags(session, [])
        assert result == []
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_matching_components_returns_empty_list(self):
        session = _make_session()
        # First query (component lookup) returns nothing
        _mock_execute(session, [])
        result = await find_templates_by_component_tags(session, ["tag-quiz"])
        assert result == []

    @pytest.mark.asyncio
    async def test_components_found_but_no_templates_returns_empty_list(self):
        session = _make_session()
        comp_row = _make_row(tag="tag-quiz", id=UUID("00000000-0000-0000-0000-000000000001"))
        # component query → one result; template_component_link query → none; never reaches template query
        _mock_execute(session, [comp_row], [])
        result = await find_templates_by_component_tags(session, ["tag-quiz"])
        assert result == []

    @pytest.mark.asyncio
    async def test_matching_templates_returned(self):
        session = _make_session()
        comp_row = _make_row(tag="tag-quiz", id=UUID("00000000-0000-0000-0000-000000000001"))
        tpl_link_row = _make_row(template_id=UUID("00000000-0000-0000-0000-000000000010"))
        tpl_row = _make_row(
            id=UUID("00000000-0000-0000-0000-000000000010"),
            platon_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            variables={"inputs": []},
        )
        _mock_execute(session, [comp_row], [tpl_link_row], [tpl_row])

        result = await find_templates_by_component_tags(session, ["tag-quiz"])

        assert len(result) == 1
        assert result[0]["platon_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert result[0]["variables"] == {"inputs": []}

    @pytest.mark.asyncio
    async def test_result_keys_are_correct(self):
        session = _make_session()
        comp_row = _make_row(tag="t1", id=UUID("00000000-0000-0000-0000-000000000001"))
        tpl_link_row = _make_row(template_id=UUID("00000000-0000-0000-0000-000000000010"))
        tpl_row = _make_row(
            id=UUID("00000000-0000-0000-0000-000000000010"),
            platon_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            variables=None,
        )
        _mock_execute(session, [comp_row], [tpl_link_row], [tpl_row])

        result = await find_templates_by_component_tags(session, ["t1"])

        assert set(result[0].keys()) == {"internal_id", "platon_id", "variables"}

    @pytest.mark.asyncio
    async def test_multiple_tags_multiple_templates(self):
        session = _make_session()
        comp_rows = [
            _make_row(tag="tag-a", id=UUID("00000000-0000-0000-0000-000000000001")),
            _make_row(tag="tag-b", id=UUID("00000000-0000-0000-0000-000000000002")),
        ]
        tpl_link_rows = [
            _make_row(template_id=UUID("00000000-0000-0000-0000-000000000010")),
            _make_row(template_id=UUID("00000000-0000-0000-0000-000000000011")),
        ]
        tpl_rows = [
            _make_row(id=UUID("00000000-0000-0000-0000-000000000010"),
                      platon_id=UUID("aaaaaaaa-0000-0000-0000-000000000000"), variables={}),
            _make_row(id=UUID("00000000-0000-0000-0000-000000000011"),
                      platon_id=UUID("bbbbbbbb-0000-0000-0000-000000000000"), variables={}),
        ]
        _mock_execute(session, comp_rows, tpl_link_rows, tpl_rows)

        result = await find_templates_by_component_tags(session, ["tag-a", "tag-b"])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# get_all_templates
# ---------------------------------------------------------------------------

class TestGetAllTemplates:
    @pytest.mark.asyncio
    async def test_returns_all_rows(self):
        session = _make_session()
        rows = [
            _make_row(id=UUID("00000000-0000-0000-0000-000000000001"),
                      platon_id=UUID("aaaaaaaa-0000-0000-0000-000000000000"), variables={}),
            _make_row(id=UUID("00000000-0000-0000-0000-000000000002"),
                      platon_id=UUID("bbbbbbbb-0000-0000-0000-000000000000"), variables={"x": 1}),
        ]
        _mock_execute(session, rows)

        result = await get_all_templates(session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty_list(self):
        session = _make_session()
        _mock_execute(session, [])
        result = await get_all_templates(session)
        assert result == []

    @pytest.mark.asyncio
    async def test_platon_id_is_stringified(self):
        session = _make_session()
        uid = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        _mock_execute(session, [_make_row(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            platon_id=uid,
            variables=None,
        )])
        result = await get_all_templates(session)
        assert result[0]["platon_id"] == str(uid)


# ---------------------------------------------------------------------------
# list_exercises_using_template
# ---------------------------------------------------------------------------

class TestListExercisesUsingTemplate:
    @pytest.mark.asyncio
    async def test_returns_exercise_rows(self):
        session = _make_session()
        rows = [
            _make_row(exercise_id="e1", exercise_platon_id="p1"),
            _make_row(exercise_id="e2", exercise_platon_id="p2"),
        ]
        _mock_execute(session, rows)

        result = await list_exercises_using_template(session, "tpl-platon-id")
        assert len(result) == 2
        assert result[0]["exercise_id"] == "e1"
        assert result[1]["exercise_platon_id"] == "p2"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        session = _make_session()
        _mock_execute(session, [])
        result = await list_exercises_using_template(session, "tpl-id")
        assert result == []

    @pytest.mark.asyncio
    async def test_sql_executed_with_correct_params(self):
        session = _make_session()
        _mock_execute(session, [])
        await list_exercises_using_template(session, "my-template-id", limit=5)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["tpl"] == "my-template-id"
        assert params["limit"] == 5

