"""
Tests for src.services.template_service.

Covers:
- filter_templates: routing strategies (DB-only, Platon, component post-filter)
- filter_templates: enrichment success, enrichment failure silently skipped
- filter_templates: empty results from DB and Platon
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.models.api import FilterTemplatesRequest, TemplateResponse
from src.services.template_service import filter_templates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> AsyncMock:
    return AsyncMock()


def _make_request(**overrides) -> FilterTemplatesRequest:
    defaults = dict(composants=[], sujets=[], niveaux=[], cercle="", search=None)
    defaults.update(overrides)
    return FilterTemplatesRequest(**defaults)


def _make_template_response(platon_id: str = "tpl-1") -> TemplateResponse:
    return TemplateResponse(
        id=platon_id,
        name="Template",
        description="A template",
        config_variables={"inputs": []},
        compil_variables={},
        components=[],
        component_instances=[],
    )


# ---------------------------------------------------------------------------
# Routing strategy
# ---------------------------------------------------------------------------

class TestFilterTemplatesRouting:
    @pytest.mark.asyncio
    async def test_only_components_filter_uses_db(self):
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = []
                mock_enrich.return_value = None

                await filter_templates(request, session)

        mock_db.assert_awaited_once_with(session, ["tag-quiz"])

    @pytest.mark.asyncio
    async def test_no_filters_uses_platon_api(self):
        session = _make_session()
        request = _make_request()

        with patch("src.services.template_service.platon_service") as mock_platon:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_platon.get_filtered_resources = AsyncMock(return_value=[])
                mock_enrich.return_value = None

                await filter_templates(request, session)

        mock_platon.get_filtered_resources.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_filter_uses_platon_api(self):
        session = _make_session()
        request = _make_request(search="math")

        with patch("src.services.template_service.platon_service") as mock_platon:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock):
                mock_platon.get_filtered_resources = AsyncMock(return_value=[])
                await filter_templates(request, session)

        mock_platon.get_filtered_resources.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_components_plus_other_filter_uses_both_platon_and_db(self):
        """When composants is set alongside other filters, both Platon API and DB component lookup are used."""
        session = _make_session()
        request = _make_request(composants=["tag-quiz"], sujets=["math"])

        with patch("src.services.template_service.platon_service") as mock_platon:
            with patch("src.services.template_service.find_templates_by_component_tags",
                       new_callable=AsyncMock) as mock_db:
                with patch("src.services.template_service._enrich_template_with_platon_data",
                           new_callable=AsyncMock) as mock_enrich:
                    mock_platon.get_filtered_resources = AsyncMock(return_value=[])
                    mock_db.return_value = []
                    mock_enrich.return_value = None

                    await filter_templates(request, session)

        mock_platon.get_filtered_resources.assert_awaited_once()
        mock_db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_components_plus_other_filter_intersects_results(self):
        """When composants + other filters, only templates matching both are returned."""
        session = _make_session()
        request = _make_request(composants=["tag-quiz"], sujets=["math"])
        enriched = _make_template_response("tpl-shared")

        with patch("src.services.template_service.platon_service") as mock_platon:
            with patch("src.services.template_service.find_templates_by_component_tags",
                       new_callable=AsyncMock) as mock_db:
                with patch("src.services.template_service._enrich_template_with_platon_data",
                           new_callable=AsyncMock) as mock_enrich:
                    # Platon returns two templates
                    mock_platon.get_filtered_resources = AsyncMock(
                        return_value=[{"id": "tpl-shared"}, {"id": "tpl-platon-only"}]
                    )
                    # DB returns two templates (one overlapping)
                    mock_db.return_value = [
                        {"platon_id": "tpl-shared"},
                        {"platon_id": "tpl-db-only"},
                    ]
                    mock_enrich.return_value = enriched

                    result = await filter_templates(request, session)

        # Only the intersecting template should be enriched
        assert len(result) == 1
        assert result[0].id == "tpl-shared"


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

class TestFilterTemplatesEnrichment:
    @pytest.mark.asyncio
    async def test_enriched_templates_returned(self):
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])
        enriched = _make_template_response("tpl-1")

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = [{"platon_id": "tpl-1"}]
                mock_enrich.return_value = enriched

                result = await filter_templates(request, session)

        assert len(result) == 1
        assert result[0].id == "tpl-1"

    @pytest.mark.asyncio
    async def test_none_enrichment_is_skipped(self):
        """Templates that fail enrichment (return None) are excluded from results."""
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = [{"platon_id": "tpl-1"}, {"platon_id": "tpl-2"}]
                mock_enrich.side_effect = [_make_template_response("tpl-1"), None]

                result = await filter_templates(request, session)

        assert len(result) == 1
        assert result[0].id == "tpl-1"

    @pytest.mark.asyncio
    async def test_enrichment_exception_is_silently_skipped(self):
        """An exception during enrichment logs an error but does not crash the service."""
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = [{"platon_id": "tpl-bad"}, {"platon_id": "tpl-ok"}]
                mock_enrich.side_effect = [
                    RuntimeError("Platon API down"),
                    _make_template_response("tpl-ok"),
                ]

                result = await filter_templates(request, session)

        assert len(result) == 1
        assert result[0].id == "tpl-ok"

    @pytest.mark.asyncio
    async def test_empty_db_result_returns_empty_list(self):
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            mock_db.return_value = []
            result = await filter_templates(request, session)

        assert result == []

    @pytest.mark.asyncio
    async def test_templates_without_platon_id_are_skipped(self):
        """Rows with empty platon_id must not be passed to enrichment."""
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = [{"platon_id": ""}, {"platon_id": None}]
                mock_enrich.return_value = _make_template_response()

                result = await filter_templates(request, session)

        mock_enrich.assert_not_awaited()
        assert result == []

    @pytest.mark.asyncio
    async def test_platon_results_converted_to_platon_id_dicts(self):
        """Results from Platon API are normalised into platon_id dicts before enrichment."""
        session = _make_session()
        request = _make_request()

        with patch("src.services.template_service.platon_service") as mock_platon:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_platon.get_filtered_resources = AsyncMock(
                    return_value=[{"id": "platon-uuid-1"}]
                )
                mock_enrich.return_value = _make_template_response("platon-uuid-1")

                result = await filter_templates(request, session)

        mock_enrich.assert_awaited_once()
        assert mock_enrich.call_args[1]["template_platon_id"] == "platon-uuid-1"

    @pytest.mark.asyncio
    async def test_user_token_forwarded_to_enrichment(self):
        session = _make_session()
        request = _make_request(composants=["tag-quiz"])

        with patch("src.services.template_service.find_templates_by_component_tags",
                   new_callable=AsyncMock) as mock_db:
            with patch("src.services.template_service._enrich_template_with_platon_data",
                       new_callable=AsyncMock) as mock_enrich:
                mock_db.return_value = [{"platon_id": "tpl-1"}]
                mock_enrich.return_value = _make_template_response("tpl-1")

                await filter_templates(request, session, user_token="my-token")

        assert mock_enrich.call_args[1]["user_token"] == "my-token"

