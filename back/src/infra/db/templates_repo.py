from __future__ import annotations

from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


async def find_templates_by_component_tags(
    session: AsyncSession,
    component_tags: List[str]
) -> List[dict]:
    """
    Find all templates that contain ALL specified component tags.

    Args:
        session: Database session
        component_tags: List of component tags that templates must have

    Returns:
        List of dicts with keys: internal_id (UUID), platon_id (UUID), variables (JSONB)
    """
    if not component_tags:
        return []

    comp_rows = await session.execute(
        text("SELECT id, tag FROM component WHERE tag = ANY(:tags)"),
        {"tags": component_tags}
    )
    comp_map = {r.tag: r.id for r in comp_rows.fetchall()}

    if not comp_map:
        logger.info("No matching components found in database")
        return []

    comp_ids = list(comp_map.values())
    tpl_rows = await session.execute(
        text("""
            SELECT template_id
            FROM template_component_link
            WHERE component_id = ANY(:comp_ids)
            GROUP BY template_id
            HAVING COUNT(DISTINCT component_id) >= :num
        """),
        {"comp_ids": comp_ids, "num": len(comp_ids)}
    )
    matching_template_ids = [r.template_id for r in tpl_rows.fetchall()]

    logger.info(f"Found {len(matching_template_ids)} templates with all requested components")

    if not matching_template_ids:
        return []

    rows = await session.execute(
        text("SELECT id, platon_id, variables FROM template WHERE id = ANY(:tpl_ids)"),
        {"tpl_ids": matching_template_ids}
    )

    return [
        {
            "internal_id": r.id,
            "platon_id": str(r.platon_id),
            "variables": r.variables
        }
        for r in rows.fetchall()
    ]


async def get_all_templates(session: AsyncSession) -> List[dict]:
    """
    Get all templates from the database.

    Returns:
        List of dicts with keys: internal_id (UUID), platon_id (UUID), variables (JSONB)
    """
    rows = await session.execute(
        text("SELECT id, platon_id, variables FROM template")
    )

    return [
        {
            "internal_id": r.id,
            "platon_id": str(r.platon_id),
            "variables": r.variables
        }
        for r in rows.fetchall()
    ]

