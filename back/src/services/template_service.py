from __future__ import annotations

import json
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.platon_service import platon_service
from src.infra.db.templates_repo import find_templates_by_component_tags, get_all_templates
from src.services.workspace_service import workspace_service
from src.services.models.api import FilterTemplatesRequest, TemplateResponse
from src.services.models.platon import TemplateSummary

logger = logging.getLogger(__name__)


async def filter_templates(
    request: FilterTemplatesRequest,
    session: AsyncSession,
    user_token: Optional[str] = None
) -> List[TemplateResponse]:
    """
    Filter templates based on various criteria.

    Strategy:
    - If ONLY components filter is set: use local DB to avoid heavy Platon call
    - Otherwise: use Platon filtering API

    Args:
        request: Filter criteria
        session: Database session
        user_token: User's Platon token

    Returns:
        List of enriched template responses
    """
    # Check if only components filter is active
    only_components_filter = (
        request.composants and
        not request.sujets and
        not request.niveaux and
        not request.cercle and
        not request.search
    )

    raw_templates: List[dict]
    if only_components_filter:
        logger.info(f"Using DB-only filtering for components: {request.composants}")
        raw_templates = await find_templates_by_component_tags(session, request.composants)
    elif request.composants:
        logger.info("Using Platon filtering with component post-filtering")
        raw_templates = await find_templates_by_component_tags(session, request.composants)
    else:
        logger.info("Using Platon API for filtering")
        platon_results = await platon_service.get_filtered_resources(
            types="EXERCISE",
            status="READY",
            configurable=True,
            topics=request.sujets if request.sujets else None,
            levels=request.niveaux if request.niveaux else None,
            parents=[request.cercle] if request.cercle else None,
            search=request.search if request.search else None,
            token=user_token
        )
        raw_templates = [{"platon_id": str(t.get("id", ""))} for t in platon_results]

    templates: List[TemplateSummary] = [
        TemplateSummary(platon_id=t["platon_id"])
        for t in raw_templates
        if t.get("platon_id")
    ]

    logger.info(f"Found {len(templates)} templates after filtering")

    template_responses: List[TemplateResponse] = []
    for template in templates:
        try:
            enriched = await _enrich_template_with_platon_data(
                template_platon_id=template.platon_id,
                required_components=request.composants,
                user_token=user_token
            )
            if enriched:
                template_responses.append(enriched)
        except Exception as e:
            logger.error(f"Failed to enrich template {template.platon_id}: {e}")
            continue

    logger.info(f"Successfully enriched {len(template_responses)} templates")
    return template_responses


async def _enrich_template_with_platon_data(
    template_platon_id: str,
    required_components: Optional[List[str]] = None,
    user_token: Optional[str] = None
) -> Optional[TemplateResponse]:
    """
    Enrich a template with data from Platon API.

    Args:
        template_platon_id: Platon ID of the template
        required_components: If set, verify template has these components
        user_token: User's Platon token

    Returns:
        Enriched template response or None if it doesn't match requirements
    """
    # Get basic resource info
    data = await platon_service.get_resource(template_platon_id, user_token)
    name = data.get("name", "")
    description = data.get("desc", "")

    raw_levels = data.get("levels", [])
    raw_topics = data.get("topics", [])
    levels = [item.get("name", "") for item in raw_levels if isinstance(item, dict) and item.get("name")]
    topics = [item.get("name", "") for item in raw_topics if isinstance(item, dict) and item.get("name")]

    # Compile to get variables and components
    compiled_data = await platon_service.compile_resource_json(
        resource_id=template_platon_id,
        token=user_token
    )
    compil_variables = compiled_data.get("variables", {})

    # Extract components from compiled data
    template_components = await workspace_service.extract_template_components(
        template_platon_id,
        user_token,
        compiled_data
    )

    logger.info(f"Template {template_platon_id} has components: {template_components}")

    # If required components are specified, verify template has them
    if required_components:
        required_set = set(required_components)
        template_set = set(template_components)
        if not required_set.issubset(template_set):
            logger.info(
                f"Template {template_platon_id} skipped - missing components. "
                f"Required: {required_set}, Has: {template_set}"
            )
            return None

    # Get template configuration (main.plc)
    main_plc_text = await platon_service.get_file_content(
        resource_id=template_platon_id,
        filename="main.plc",
        version="latest",
        token=user_token
    )
    config_variables = json.loads(main_plc_text)

    # Parse component instances from compiled variables
    component_instances = workspace_service.parse_component_instances_from_sandbox(compil_variables)

    return TemplateResponse(
        id=template_platon_id,
        name=name,
        description=description,
        config_variables=config_variables,
        compil_variables=compil_variables,
        components=template_components,
        component_instances=component_instances,
        levels=levels,
        topics=topics,
    )
