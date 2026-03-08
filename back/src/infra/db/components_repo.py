from __future__ import annotations

from typing import TypedDict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ComponentDoc(TypedDict):
    tag: str
    description: str | None
    usage: str | None

class ComponentForm(TypedDict):
    tag: str
    description: str | None
    usage: str | None
    type: str | None


async def list_component_docs(session: AsyncSession) -> list[ComponentDoc]:
    res = await session.execute(
        text("""
             SELECT
                 tag,
                 description,
                 usage
             FROM component
             ORDER BY tag
             """)
    )
    return [dict(r._mapping) for r in res.fetchall()]

async def list_component_for_form(session: AsyncSession) -> list[ComponentForm]:
    res = await session.execute(
        text("""
             SELECT
                 tag,
                 name,
                 description,
                 usage,
                 category AS type
             FROM component
             ORDER BY tag
             """)
    )
    return [dict(r._mapping) for r in res.fetchall()]


async def list_exercises_using_component(
    session: AsyncSession,
    component_tag: str,
    limit: int = 3
) -> list[dict[str, Any]]:
    """
    Given a component tag, return exercises that use this component.
    Returns up to 'limit' exercises (default 3).
    """
    sql = text("""
        SELECT
            e.id::text AS exercise_id,
            e.platon_id::text AS exercise_platon_id,
            e.created_at,
            c.tag AS component_tag,
            c.name AS component_name
        FROM exercise e
        JOIN exercise_component_link ecl ON ecl.exercise_id = e.id
        JOIN component c ON c.id = ecl.component_id
        WHERE c.tag = :component_tag
        AND e.template_id IS NULL  -- Only exercises not based on templates
        ORDER BY e.created_at DESC
        LIMIT :limit
    """)

    res = await session.execute(sql, {"component_tag": component_tag, "limit": limit})
    rows = res.fetchall()

    return [
        {
            "exercise_id": r.exercise_id,
            "exercise_platon_id": r.exercise_platon_id,
            "created_at": r.created_at,
            "component_tag": r.component_tag,
            "component_name": r.component_name,
        }
        for r in rows
    ]
9